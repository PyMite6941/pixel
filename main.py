import importlib
import json
import sys
import argparse
from pathlib import Path

import anthropic
from google import genai as google_genai
from groq import Groq

from config import Config, save_prefs, mark_rate_limited, mark_provider_ok, update_rate_limits_from_headers, get_rate_limit_state
from brain.domain_registry import DomainRegistry
from utils.logger import get_logger
from utils.secretscanner import scan as scan_secrets, redact as redact_secrets, save_secrets_ref
from utils.terminal import (
    banner, user_message, assistant_message, info, success, warn, error,
    status_enter, status_done, command_table, skill_table, memory_table,
    secrets_table, goodbye, _RICH,
)
from skills.registry import SkillRegistry
from memory.token_tracker import record as track_usage, summary as usage_summary, estimate_tokens
from memory.session_manager import save as save_session, load as load_session, list_sessions, delete as delete_session
from memory.context_manager import compress as compress_context
from models.registry import ModelRegistry, ModelImage
from models.provider import LocalModelProvider
from models.source import AgentSource, get_default_sources, resolve_agent_source
from engine.engine import SmartEngine

logger = get_logger(__name__)

_HISTORY_FILE = Path(__file__).parent / "memory" / "history.json"
_MEMORY_FILE = Path(__file__).parent / "memory" / "learned.json"

_SYSTEM_PROMPT = (
    "You are Pixel, a security-first, self-aware AI assistant. "
    "You give concise, accurate answers. "
    "For coding questions, provide working code with brief explanations. "
    "For general questions, be direct and helpful. "
    "Keep responses focused and avoid unnecessary filler. "
    "You never ask for API keys, tokens, or passwords. "
    "If a user sends sensitive data, it gets redacted before reaching you. "
    "You can introspect, audit, and modify your own source code. "
    "You can generate new skills and domains for yourself. "
    "You support hot-reloading to pick up changes without restarting. "
    "You can run locally via Ollama when no cloud API keys are available. "
    "You can learn facts and recall them later. "
    "Always validate and security-scan any code you generate before applying it. "
    "You have a persistent memory. When the user tells you something to remember, "
    "respond with [LEARN key=value] on its own line to save it. "
    "You can recall memories by saying [RECALL key]. "
    "Relevant memories are automatically injected into your context. "
     "You have access to tools (skills). To invoke a tool, respond with "
     "[TOOL tool_name param=value ...] on its own line. "
     "For values with spaces, wrap them in quotes: param=\"value with spaces\". "
     "Available tools: search, run_code, file_ops, system_info, think, validator, "
     "shell (run powershell/cmd/python commands), web_fetch (fetch URLs), "
     "clipboard (read/write clipboard), process (list/kill/start processes), "
     "screenshot (capture screen), browser (open URLs in default browser), "
     "network (IP, connectivity, DNS, ports). "
     "You can control this laptop: run commands, browse the web, manage files and processes, "
     "read/write clipboard, take screenshots, and check network status."
)

_DOMAIN_HINTS = {
    "SelfDomain": (
        " The user is asking about your own capabilities, self-check, self-update, or skill generation. "
        "Be honest about your abilities and limitations. Offer to run a self-check or generate a new skill."
    ),
    "SecurityDomain": (
        " The user is asking about security, credentials, or encryption. "
        "Never request sensitive data. Provide secure best practices."
    ),
    "CodingDomain": (
        " The user is asking a coding or programming question. "
        "Prioritize working code examples."
    ),
    "GameDomain": (
        " The user is asking about a game. "
        "Give strategic, practical advice."
    ),
}


def _load_history() -> list[dict]:
    if _HISTORY_FILE.exists():
        try:
            with open(_HISTORY_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load history: %s", e)
    return []


def _save_history(history: list[dict]):
    _HISTORY_FILE.parent.mkdir(exist_ok=True)
    with open(_HISTORY_FILE, "w") as f:
        json.dump(history[-Config.MAX_HISTORY:], f, indent=2)


class Pixel:
    def __init__(self):
        self.groq = Groq(api_key=Config.GROQ_API_KEY) if Config.GROQ_API_KEY else None
        self.gemini = google_genai.Client(api_key=Config.GOOGLE_API_KEY) if Config.GOOGLE_API_KEY else None
        self.claude = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.ollama_client = None
        self.model_registry = ModelRegistry()
        self._local_providers: dict[str, LocalModelProvider] = {}
        self._agent_sources: list[AgentSource] = get_default_sources()
        self.engine = SmartEngine(pixel_instance=self, llm_ask=self.ask)
        self.registry = DomainRegistry()
        self.skills = SkillRegistry()
        self.history: list[dict] = _load_history()

    def _build_messages(self, prompt: str, system: str) -> list[dict]:
        messages = [{"role": "system", "content": system}]
        messages.extend(self.history[-Config.MAX_HISTORY:])
        messages.append({"role": "user", "content": prompt})
        return messages

    def _ollama_available(self) -> bool:
        if self.ollama_client is not None:
            return True
        try:
            import ollama
            ollama.list()
            self.ollama_client = ollama
            return True
        except Exception:
            return False

    def _count_tokens(self, *texts: str) -> int:
        return sum(estimate_tokens(t) for t in texts)

    def _track(self, provider: str, input_texts: list[str], output: str) -> None:
        inp = self._count_tokens(*input_texts)
        out = self._count_tokens(output)
        track_usage(provider, inp, out)

    def use_groq(self, messages: list[dict], smart: bool = False) -> str:
        model = Config.SMART_MODEL if smart else Config.FAST_MODEL
        response = self.groq.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            stream=False,
        )
        reply = response.choices[0].message.content
        self._track("groq", [str(messages)], reply)
        if hasattr(response, "headers"):
            update_rate_limits_from_headers("groq", dict(response.headers))
        mark_provider_ok("groq")
        return reply

    def use_groq_stream(self, messages: list[dict], smart: bool = False):
        model = Config.SMART_MODEL if smart else Config.FAST_MODEL
        stream = self.groq.chat.completions.create(
            model=model, messages=messages, temperature=0.7, stream=True,
        )
        full = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full += delta
                yield delta
        self._track("groq", [str(messages)], full)
        mark_provider_ok("groq")

    def use_gemini(self, prompt: str, system: str = "") -> str:
        from google.genai import types as genai_types
        config = None
        if system:
            config = genai_types.GenerateContentConfig(system_instruction=system)
        response = self.gemini.models.generate_content(
            model=Config.GEMINI_MODEL, contents=prompt, config=config,
        )
        reply = response.text
        self._track("gemini", [system, prompt], reply)
        if hasattr(response, "_response") and hasattr(response._response, "headers"):
            update_rate_limits_from_headers("gemini", dict(response._response.headers))
        mark_provider_ok("gemini")
        return reply

    def use_claude(self, prompt: str, system: str = "") -> str:
        response = self.claude.messages.create(
            model=Config.CLAUDE_MODEL, max_tokens=2048,
            system=system or _SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        reply = response.content[0].text
        self._track("claude", [system, prompt], reply)
        if hasattr(response, "_response") and hasattr(response._response, "headers"):
            update_rate_limits_from_headers("claude", dict(response._response.headers))
        mark_provider_ok("claude")
        return reply

    def use_claude_stream(self, prompt: str, system: str = ""):
        with self.claude.messages.stream(
            model=Config.CLAUDE_MODEL, max_tokens=2048,
            system=system or _SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            full = ""
            for text in stream.text_stream:
                full += text
                yield text
        self._track("claude", [system, prompt], full)
        mark_provider_ok("claude")

    def use_ollama(self, prompt: str, system: str = "") -> str:
        import ollama
        model = Config.OLLAMA_MODEL
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        response = ollama.chat(model=model, messages=msgs)
        reply = response["message"]["content"]
        self._track("ollama", [system, prompt], reply)
        return reply

    def use_ollama_stream(self, prompt: str, system: str = ""):
        import ollama
        model = Config.OLLAMA_MODEL
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        stream = ollama.chat(model=model, messages=msgs, stream=True)
        full = ""
        for chunk in stream:
            delta = chunk["message"]["content"]
            if delta:
                full += delta
                yield delta
        self._track("ollama", [system, prompt], full)

    def use_local_model(self, prompt: str, system: str = "", model_name: str = "") -> str:
        provider = self._local_providers.get(model_name)
        if not provider:
            raise RuntimeError(f"Local model provider not loaded: {model_name}")
        reply = provider.ask(prompt, system=system)
        self._track(model_name, [system, prompt], reply)
        mark_provider_ok(model_name)
        return reply

    def use_local_model_stream(self, prompt: str, system: str = "", model_name: str = ""):
        provider = self._local_providers.get(model_name)
        if not provider:
            raise RuntimeError(f"Local model provider not loaded: {model_name}")
        full = ""
        for chunk in provider.ask_stream(prompt, system=system):
            full += chunk
            yield chunk
        self._track(model_name, [system, prompt], full)
        mark_provider_ok(model_name)

    def _sanitize(self, text: str, context: str = "user_input") -> str:
        secrets = scan_secrets(text)
        if secrets:
            ref_file = save_secrets_ref(secrets, source=context)
            logger.warning(
                "Secrets detected in %s! Saved references to %s. Redacting before sending to LLM.",
                context, ref_file,
            )
            for s in secrets:
                warn(f"Blocked {s.name} — saved locally to {ref_file}")
            return redact_secrets(text)
        return text

    def _load_local_provider(self, image_name: str):
        if image_name not in self._local_providers:
            img = self.model_registry.get_image(image_name)
            if img and img.path:
                path = Path(img.path)
                if path.exists():
                    self._local_providers[image_name] = LocalModelProvider(path, model_name=img.name)

    def _local_provider_names(self) -> list[str]:
        names = []
        for img in self.model_registry.list_images():
            if img.source_type in ("gguf_file", "huggingface") and img.path:
                path = Path(img.path)
                if path.exists():
                    names.append(img.provider_name or img.name)
        return names

    def _providers(self) -> list[str]:
        preferred = Config.PREFERRED_PROVIDER
        base_providers = ["groq", "gemini", "claude", "ollama"]
        local_names = self._local_provider_names()
        all_providers = base_providers + local_names
        available = []
        rate_state = get_rate_limit_state()
        for p in all_providers:
            if rate_state.get(p, {}).get("rate_limited", False):
                continue
            if p == "ollama" and self._ollama_available():
                available.append(p)
            elif p == "groq" and self.groq:
                available.append(p)
            elif p == "gemini" and self.gemini:
                available.append(p)
            elif p == "claude" and self.claude:
                available.append(p)
            elif p in local_names:
                self._load_local_provider(p)
                available.append(p)
        if not available:
            for p in all_providers:
                if p == "ollama" and self._ollama_available():
                    available.append(p)
                elif p == "groq" and self.groq:
                    available.append(p)
                elif p == "gemini" and self.gemini:
                    available.append(p)
                elif p == "claude" and self.claude:
                    available.append(p)
                elif p in local_names:
                    self._load_local_provider(p)
                    available.append(p)
        if preferred in available:
            available.remove(preferred)
            available.insert(0, preferred)
        return available

    def _load_memory(self) -> dict:
        if _MEMORY_FILE.exists():
            try:
                return json.loads(_MEMORY_FILE.read_text())
            except Exception:
                return {}
        return {}

    def _save_memory(self, memory: dict) -> None:
        _MEMORY_FILE.parent.mkdir(exist_ok=True)
        _MEMORY_FILE.write_text(json.dumps(memory, indent=2))

    def _inject_memory_context(self, prompt: str, memory: dict) -> str:
        matches = []
        prompt_lower = prompt.lower()
        for key, value in memory.items():
            if key.lower() in prompt_lower:
                matches.append(f"  {key}: {value}")
        if matches:
            return "Relevant memories:\n" + "\n".join(matches) + "\n"
        return ""

    def _process_learn_tags(self, reply: str) -> str:
        import re
        memory = self._load_memory()
        lines = reply.split("\n")
        kept = []
        for line in lines:
            m = re.match(r'\[LEARN\s+(.+?)\s*=\s*(.+?)\]', line)
            if m:
                key, value = m.group(1).strip(), m.group(2).strip()
                memory[key] = value
                kept.append(f"[Remembered: {key}]")
            else:
                kept.append(line)
        if memory != self._load_memory():
            self._save_memory(memory)
        return "\n".join(kept)

    def _process_tool_calls(self, reply: str) -> tuple[list[dict], str]:
        import re
        tool_results = []
        cleaned_lines = []
        for line in reply.split("\n"):
            m = re.match(r'\[TOOL\s+(\w+)(.*)\]', line)
            if m:
                tool_name = m.group(1)
                args_str = m.group(2).strip()
                args = {}
                for kv in re.findall(r'(\w+)=(?:"([^"]*)"|\'([^\']*)\'|(\S+))', args_str):
                    val = kv[1] or kv[2] or kv[3]
                    args[kv[0]] = val
                skill = self.skills.get(tool_name)
                if skill:
                    try:
                        if getattr(skill, 'requires_subprocess', False):
                            result = f"[Skill {tool_name} executed in subprocess]"
                        else:
                            result = skill.execute(**args)
                        tool_results.append({"tool": tool_name, "result": result})
                        cleaned_lines.append(f"[Pixel used {tool_name}]")
                    except Exception as e:
                        tool_results.append({"tool": tool_name, "result": f"Error: {e}"})
                        cleaned_lines.append(f"[Pixel tried {tool_name} but it failed]")
                else:
                    cleaned_lines.append(line)
            else:
                cleaned_lines.append(line)
        return tool_results, "\n".join(cleaned_lines)

    def ask_stream(self, prompt: str, system: str) -> str:
        for provider in self._providers():
            try:
                collected = ""
                if provider == "groq":
                    for chunk in self.use_groq_stream(self._build_messages(prompt, system), smart=Config.SMART_MODE):
                        collected += chunk
                        yield chunk
                elif provider == "claude":
                    for chunk in self.use_claude_stream(prompt, system=system):
                        collected += chunk
                        yield chunk
                elif provider == "ollama":
                    for chunk in self.use_ollama_stream(prompt, system=system):
                        collected += chunk
                        yield chunk
                elif provider == "gemini":
                    result = self.use_gemini(prompt, system=system)
                    collected = result
                    yield result
                elif provider in self._local_providers:
                    for chunk in self.use_local_model_stream(prompt, system=system, model_name=provider):
                        collected += chunk
                        yield chunk
                return
            except Exception as e:
                err_str = str(e)
                logger.warning("%s stream failed (%s), trying next", provider, err_str)
                if "429" in err_str or "rate limit" in err_str.lower() or "too many requests" in err_str.lower():
                    mark_rate_limited(provider)
                continue
        yield "All providers failed."

    def _auto_invoke_skills(self, prompt: str) -> str:
        results = []
        for name in self.skills.skill_names:
            skill = self.skills.get(name)
            triggers = skill.auto_triggers if hasattr(skill, 'auto_triggers') else []
            if triggers and any(t in prompt.lower() for t in triggers):
                logger.debug("Auto-invoking skill: %s", name)
                try:
                    if hasattr(skill, 'requires_subprocess') and skill.requires_subprocess:
                        import subprocess
                        import inspect
                        src = inspect.getsource(skill.execute)
                        result = subprocess.run(
                            [sys.executable, "-c", f"import sys; sys.path.insert(0, '.'); {src}; print('done')"],
                            capture_output=True, text=True, timeout=10,
                        )
                        results.append(f"[Skill: {name}] Auto-executed (subprocess) — see you later for details")
                    else:
                        result = skill.execute(task=prompt)
                        results.append(f"[Skill: {name}] Result: {result}")
                except Exception as e:
                    logger.warning("Skill %s auto-invoke failed: %s", name, e)
        return "\n".join(results)

    def ask(self, prompt: str) -> str:
        safe_prompt = self._sanitize(prompt, "user_input")
        domain = self.registry.route(safe_prompt)
        logger.debug("Routed to domain: %s", domain)
        hint = _DOMAIN_HINTS.get(domain, "")
        system = _SYSTEM_PROMPT + hint
        safe_system = self._sanitize(system, "system_prompt")

        memory = self._load_memory()
        memory_context = self._inject_memory_context(safe_prompt, memory)
        if memory_context:
            safe_system = safe_system + "\n" + memory_context

        self.history = compress_context(self.history)

        messages = self._build_messages(safe_prompt, safe_system)
        current_prompt = safe_prompt
        current_system = safe_system
        max_agent_loops = 3
        final_reply = None

        for loop in range(max_agent_loops):
            reply = None
            last_error = None
            for provider in self._providers():
                try:
                    if provider == "groq":
                        reply = self.use_groq(self._build_messages(current_prompt, current_system), smart=Config.SMART_MODE)
                    elif provider == "gemini":
                        reply = self.use_gemini(current_prompt, system=current_system)
                    elif provider == "claude":
                        reply = self.use_claude(current_prompt, system=current_system)
                    elif provider == "ollama":
                        reply = self.use_ollama(current_prompt, system=current_system)
                    elif provider in self._local_providers:
                        reply = self.use_local_model(current_prompt, system=current_system, model_name=provider)
                    if reply:
                        break
                except Exception as e:
                    err_str = str(e)
                    logger.warning("%s failed (%s), trying next", provider, err_str)
                    if "429" in err_str or "rate limit" in err_str.lower() or "too many requests" in err_str.lower():
                        mark_rate_limited(provider)
                    last_error = e

            if reply is None:
                return f"All providers failed. Last error: {last_error}"

            reply = self._process_learn_tags(reply)
            tool_results, clean_reply = self._process_tool_calls(reply)

            if not tool_results:
                final_reply = clean_reply
                break

            tool_context = "\n".join(f"[{r['tool']}] Result: {r['result']}" for r in tool_results)
            current_prompt = (
                f"I used tools to answer your question. Here are the results:\n{tool_context}\n\n"
                f"Please provide a final answer based on these results."
            )
            current_system = safe_system
            final_reply = None

        if final_reply is None:
            final_reply = clean_reply if 'clean_reply' in dir() else reply

        self.history.append({"role": "user", "content": safe_prompt})
        self.history.append({"role": "assistant", "content": final_reply})
        _save_history(self.history)

        try:
            from training.collector import TrainingCollector
            collector = TrainingCollector()
            collector.record_from_ask(
                prompt=safe_prompt,
                response=final_reply,
                domain=domain,
                provider=self._providers()[0] if self._providers() else "unknown",
                tool_calls=tool_results if 'tool_results' in dir() and tool_results else None,
            )
        except Exception:
            pass

        return final_reply

    def reload_skills(self) -> int:
        importlib.invalidate_caches()
        self.skills = SkillRegistry()
        return len(self.skills.skill_names)

    def reload_domains(self) -> int:
        importlib.invalidate_caches()
        import brain.domains
        import brain.domain_registry
        for mod in list(sys.modules.keys()):
            if mod.startswith("brain.domains.") or mod == "brain.domain_registry":
                importlib.reload(sys.modules[mod])
        self.registry = DomainRegistry()
        return len(self.registry.route.__self__._DOMAINS) if hasattr(self.registry, 'route') else 0

    def reload_config(self) -> None:
        importlib.invalidate_caches()
        import config
        importlib.reload(config)
        from config import Config, save_prefs
        self.groq = Groq(api_key=Config.GROQ_API_KEY) if Config.GROQ_API_KEY else None
        self.gemini = google_genai.Client(api_key=Config.GOOGLE_API_KEY) if Config.GOOGLE_API_KEY else None
        self.claude = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY) if Config.ANTHROPIC_API_KEY else None
        self.model_registry = ModelRegistry()

    def _handle_command(self, cmd: str) -> bool:
        parts = cmd.split(maxsplit=1)
        if parts[0] == "/save" and len(parts) == 2:
            name = parts[1].strip()
            result = save_session(name, self.history)
            success(f"Session '{result['name']}' saved ({result['turns']} turns)")
            return True
        if parts[0] == "/load" and len(parts) == 2:
            name = parts[1].strip()
            history = load_session(name)
            if history is not None:
                self.history = history
                success(f"Session '{name}' loaded ({len(history)} turns)")
            else:
                warn(f"Session '{name}' not found")
            return True
        if parts[0] == "/sessions":
            sessions = list_sessions()
            if sessions:
                if _RICH:
                    from rich.table import Table
                    from rich.console import Console
                    table = Table(box=None, border_style="cyan")
                    table.add_column("Name", style="bold cyan")
                    table.add_column("Turns", style="white")
                    table.add_column("Saved", style="dim")
                    for s in sessions:
                        table.add_row(s["name"], str(s["turns"]), s.get("saved_at", "?")[:16])
                    Console().print(table)
                else:
                    for s in sessions:
                        print(f"  \033[1;33m{s['name']}\033[0m ({s['turns']} turns, {s.get('saved_at','?')[:16]})")
            else:
                info("No saved sessions")
            return True
        if parts[0] == "/usage":
            s = usage_summary()
            cost_str = f"${s['cost']:.4f}" if s['cost'] > 0 else "free (local)"
            success(f"Tokens: {s['input_tokens']} in / {s['output_tokens']} out | Cost: {cost_str}")
            return True
        if parts[0] == "/web":
            try:
                import web_ui
                import threading
                t = threading.Thread(target=web_ui.run, daemon=True)
                t.start()
                success("API server started at http://localhost:8642")
                ui_dir = Path(__file__).parent / "ui"
                if (ui_dir / "dist" / "index.html").exists():
                    success("React UI is available at http://localhost:8642")
                elif (ui_dir / "node_modules").exists():
                    info("React dev server: run 'cd ui && npm run dev' for hot-reload UI on :5173")
                else:
                    info("React UI not built. Run: cd ui && npm install && npm run build")
            except Exception as e:
                error(f"Web API failed: {e}")
            return True
        if parts[0] == "/set" and len(parts) == 2:
            kv = parts[1].split("=", maxsplit=1)
            if len(kv) == 2:
                key, value = kv[0].strip(), kv[1].strip()
                save_prefs({key: value})
                success(f"Set {key} = {value}")
                return True
            info("Usage: /set key=value")
            return True
        if parts[0] == "/clear":
            self.history.clear()
            _save_history(self.history)
            success("Conversation cleared")
            return True
        if parts[0] == "/scan" and len(parts) == 2:
            from utils.secretscanner import scan as scan_text
            found = scan_text(parts[1])
            if found:
                warn(f"Found {len(found)} potential secrets:")
                for s in found:
                    preview = s.full_match[:40] + "..." if len(s.full_match) > 40 else s.full_match
                    info(f"  [{s.name}] {preview}")
            else:
                success("No secrets detected")
            return True
        if parts[0] == "/secrets":
            from utils.secretscanner import load_secrets_ref
            data = load_secrets_ref()
            if data["secrets"]:
                warn("Locally saved secret references:")
                secrets_table(data["secrets"])
            else:
                info("No secrets have been detected this session")
            return True
        if parts[0] == "/status":
            from self.self_check import full_report
            info(full_report())
            return True
        if parts[0] == "/check" and len(parts) == 2:
            from self.self_check import health, security_audit, deps_status
            sub = parts[1].lower()
            if sub == "health":
                r = health()
                success(f"Status: {r['status']}")
                for i in r["issues"]:
                    warn(i)
            elif sub == "security":
                r = security_audit()
                if r["clean"]:
                    success("Security audit: CLEAN")
                else:
                    warn(f"Security audit: {len(r['findings'])} issue(s)")
                    secrets_table(r["findings"])
            elif sub == "deps":
                for d in deps_status():
                    if d["status"] == "installed":
                        success(f"{d['package']}")
                    else:
                        error(f"{d['package']} — missing")
            else:
                info(f"Unknown check: {sub}. Use: health, security, deps")
            return True
        if parts[0] == "/skills":
            if self.skills.skill_names:
                skill_table(self.skills.skills)
            else:
                info("No skills loaded")
            return True
        if parts[0] == "/reload":
            target = parts[1].lower() if len(parts) == 2 else "all"
            if target in ("skills", "all"):
                n = self.reload_skills()
                success(f"Reloaded {n} skills")
            if target in ("domains", "all"):
                self.reload_domains()
                success("Reloaded domains")
            if target in ("config", "all"):
                self.reload_config()
                success("Reloaded config and providers")
            if target not in ("skills", "domains", "config", "all"):
                info(f"Unknown: {target}. Use: skills, domains, config, all")
            return True
        if parts[0] == "/learn" and len(parts) == 2:
            kv = parts[1].split("=", maxsplit=1)
            if len(kv) == 2:
                key, value = kv[0].strip(), kv[1].strip()
                memory = {}
                if _MEMORY_FILE.exists():
                    memory = json.loads(_MEMORY_FILE.read_text())
                memory[key] = value
                _MEMORY_FILE.parent.mkdir(exist_ok=True)
                _MEMORY_FILE.write_text(json.dumps(memory, indent=2))
                success(f"Learned: {key} = {value}")
            else:
                info("Usage: /learn key = value")
            return True
        if parts[0] == "/recall" and len(parts) == 2:
            key = parts[1].strip()
            if _MEMORY_FILE.exists():
                memory = json.loads(_MEMORY_FILE.read_text())
                if key in memory:
                    success(f"{key}: {memory[key]}")
                elif key == "*":
                    if memory:
                        memory_table(memory)
                    else:
                        info("No memories yet")
                else:
                    matches = {k: v for k, v in memory.items() if key.lower() in k.lower()}
                    if matches:
                        memory_table(matches)
                    else:
                        info(f"No memory found for '{key}'")
            else:
                info("No learned memories yet")
            return True
        if parts[0] == "/forget" and len(parts) == 2:
            key = parts[1].strip()
            if _MEMORY_FILE.exists():
                memory = json.loads(_MEMORY_FILE.read_text())
                if key in memory:
                    del memory[key]
                    _MEMORY_FILE.write_text(json.dumps(memory, indent=2))
                    success(f"Forgot: {key}")
                else:
                    warn(f"No memory '{key}' to forget")
            else:
                info("No learned memories yet")
            return True
        if parts[0] == "/cleanup":
            from utils.cleanup import clean, format_size
            result = clean(dry_run=False)
            success(f"Cleaned {result['removed_dirs']} cache dirs, {result['removed_files']} files ({result['freed_human']})")
            return True

        if parts[0] == "/model":
            from config import get_provider_usage_state
            from memory.token_tracker import summary
            state = get_provider_usage_state()
            tokens = summary()
            providers = self._providers()

            if _RICH and False:
                pass
            else:
                lines = []
                lines.append("")
                success("Available providers:")
                for p in ("groq", "gemini", "claude", "ollama"):
                    s = state.get(p, {})
                    has_key = bool(getattr(self, p, None)) or (p == "ollama" and self._ollama_available())
                    if not has_key:
                        continue
                    active = "✓" if not s.get("rate_limited", False) else "⚠ RATE LIMITED"
                    remaining = s.get("remaining", "—")
                    limit = s.get("limit", "—")
                    cooldown = s.get("cooldown_remaining", 0)
                    reset_str = f" ({cooldown}s cooldown)" if cooldown > 0 else ""
                    current = "◀ ACTIVE" if providers and p == providers[0] else ""
                    lines.append(f"  [{active}] {p}  {current}")
                    lines.append(f"       Remaining: {remaining} / {limit}  {reset_str}")
                for img in self.model_registry.list_images():
                    if img.source_type in ("gguf_file", "url", "huggingface"):
                        local_active = "✓" if img.provider_name in providers else "✗"
                        size_str = f"{img.size_bytes / 1024 / 1024:.0f}MB" if img.size_bytes else "?"
                        current = "◀ ACTIVE" if providers and img.provider_name == providers[0] else ""
                        lines.append(f"  [{local_active}] {img.name} (local GGUF, {size_str})  {current}")
                        lines.append(f"       File: {img.path}")
                for img in self.model_registry.list_images():
                    if img.source_type in ("ollama_pull",):
                        local_active = "✓" if img.provider_name in providers else "✗"
                        current = "◀ ACTIVE" if providers and img.provider_name == providers[0] else ""
                        lines.append(f"  [{local_active}] {img.name} (Ollama)  {current}")
                        if img.description:
                            lines.append(f"       {img.description}")
                lines.append("")
                lines.append(f"  Tokens: {tokens['input_tokens']} in / {tokens['output_tokens']} out")
                lines.append(f"  Cost: ${tokens['cost']:.4f}" if tokens['cost'] > 0 else "  Cost: free (local)")
                lines.append("")
                lines.append("  Switch: type the provider name (groq / gemini / claude / ollama / <local_name>)")
                lines.append("  Or press Enter to cancel")
                info("\n".join(lines))

                try:
                    choice = input("  \033[1;36mSelect provider:\033[0m ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    choice = ""
                local_names = [img.name for img in self.model_registry.list_images() if img.source_type in ("gguf_file", "url", "huggingface")]
                all_choices = ("groq", "gemini", "claude", "ollama") + tuple(local_names)
                if choice in all_choices:
                    if choice == "ollama" and not self._ollama_available():
                        warn("Ollama is not available")
                    else:
                        from config import save_prefs
                        save_prefs({"preferred_provider": choice})
                        success(f"Switched to {choice}")
                elif choice:
                    info(f"Unknown provider: {choice}")
                else:
                    info("No change")
            return True

        if parts[0] == "/models":
            from models.registry import get_catalog, find_in_catalog
            sub = parts[1].lower().strip() if len(parts) == 2 else "list"
            sub_parts = parts[1].split(maxsplit=1) if len(parts) >= 2 else [""]

            if sub == "list":
                images = self.model_registry.list_images()
                registered_count = len(images)
                catalog = get_catalog()
                if not images:
                    info("No local model images registered.")
                    info("")
                else:
                    success(f"Registered images ({registered_count}) — {self.model_registry.total_size_str()}:")
                    for img in images:
                        size_str = f"{img.size_bytes / 1024 / 1024:.0f} MB" if img.size_bytes else "?"
                        status = "✓" if (img.path and Path(img.path).exists()) or img.source_type in ("ollama_pull", "ollama") else "✗ missing"
                        provider_status = "loaded" if img.provider_name in self._local_providers else "cached"
                        src_label = {"gguf_file": "local file", "url": "downloaded", "ollama_pull": "ollama pull", "ollama": "ollama"}.get(img.source_type, img.source_type)
                        info(f"  [{status}] {img.name} ({src_label}, {size_str}) — {provider_status}")
                        if img.description:
                            info(f"       {img.description}")
                        if img.path:
                            info(f"       Path: {img.path}")
                    info("")

                info(f"Available in catalog ({len(catalog)}):")
                for entry in catalog:
                    info(f"  {entry['name']:20s}  {entry['description']:50s}  {entry['size']}")
                info("")
                info("Commands:")
                info("  /models download <name>        — Download a catalog model by name")
                info("  /models url <url> [name]        — Download from any direct URL")
                info("  /models ollama <model> [name]   — Pull a model via Ollama")
                info("  /models add <path> <name>       — Register a local GGUF file")
                info("  /models remove <name>           — Remove a model")
                info("  /models source                  — Show agent source assignments")
                return True

            if sub == "download" and len(parts) >= 3:
                catalog_name = parts[1].split(maxsplit=1)[1] if " " in parts[1] else ""
                if not catalog_name:
                    info("Usage: /models download <catalog_name>")
                    return True
                entry = find_in_catalog(catalog_name)
                if not entry:
                    warn(f"Model '{catalog_name}' not in catalog")
                    info(f"Use /models list to see available catalog entries")
                    return True
                status_enter(f"Downloading {entry['name']} from URL...")
                try:
                    img = self.model_registry.pull_from_url(
                        entry["url"],
                        name=catalog_name if catalog_name != entry["name"] else None,
                        description=entry["description"],
                        tags=entry.get("tags"),
                    )
                    status_done(f"Downloaded {img.name} ({img.size_bytes / 1024 / 1024:.0f} MB)")
                except Exception as e:
                    error(f"Download failed: {e}")
                return True

            if sub == "url" and len(parts) >= 3:
                rest = parts[1].split(maxsplit=2)
                url = rest[1] if len(rest) >= 2 else ""
                name = rest[2] if len(rest) >= 3 else None
                if not url:
                    info("Usage: /models url <download_url> [name]")
                    return True
                status_enter(f"Downloading from URL...")
                try:
                    img = self.model_registry.pull_from_url(url, name=name)
                    status_done(f"Downloaded {img.name} ({img.size_bytes / 1024 / 1024:.0f} MB)")
                except Exception as e:
                    error(f"Download failed: {e}")
                return True

            if sub == "ollama" and len(parts) >= 3:
                rest = parts[1].split(maxsplit=2)
                ollama_model = rest[1] if len(rest) >= 2 else ""
                custom_name = rest[2] if len(rest) >= 3 else None
                if not ollama_model:
                    info("Usage: /models ollama <model_name> [custom_name]")
                    return True
                if not self._ollama_available():
                    error("Ollama is not available. Start Ollama first.")
                    return True
                status_enter(f"Pulling Ollama model: {ollama_model}...")
                try:
                    img = self.model_registry.pull_from_ollama(ollama_model, name=custom_name)
                    status_done(f"Ollama model '{ollama_model}' ready")
                except Exception as e:
                    error(f"Ollama pull failed: {e}")
                return True

            if sub == "add" and len(parts) >= 3:
                rest = parts[1].split(maxsplit=2)
                if len(rest) >= 3:
                    file_path = rest[1]
                    name = rest[2]
                else:
                    info("Usage: /models add <file_path> <name>")
                    return True
                path = Path(file_path).expanduser().resolve()
                if not path.exists():
                    error(f"File not found: {path}")
                    return True
                try:
                    img = self.model_registry.add_local_file(path, name)
                    success(f"Registered {img.name} ({img.size_bytes / 1024 / 1024:.0f} MB)")
                except Exception as e:
                    error(f"Failed to register: {e}")
                return True

            if sub == "remove" and len(parts) >= 3:
                name = parts[1].split(maxsplit=1)[1] if " " in parts[1] else ""
                if not name:
                    info("Usage: /models remove <name>")
                    return True
                if self.model_registry.remove_image(name):
                    self._local_providers.pop(name, None)
                    success(f"Removed model: {name}")
                else:
                    warn(f"Model not found: {name}")
                return True

            if sub == "source":
                info("Agent AI sources:")
                for src in self._agent_sources:
                    resolved = resolve_agent_source(
                        src.name, self._agent_sources,
                        self._providers(),
                        [i.name for i in self.model_registry.list_images()],
                    )
                    info(f"  {src.name}: primary={src.primary_api or 'auto'} fallback={src.fallback_images} → {resolved}")
                info("")
                info("To set agent source: /models source set <agent> <api> [fallback...]")
                return True

            if sub == "source" and len(parts) >= 3 and "set" in parts[1].split():
                rest = parts[1].split(maxsplit=2)[2] if len(parts[1].split()) >= 3 else ""
                args = rest.split()
                if len(args) < 2:
                    info("Usage: /models source set <agent_name> <primary_api> [fallback_images...]")
                    return True
                agent_name = args[0]
                primary = args[1]
                fallbacks = args[2:]
                for src in self._agent_sources:
                    if src.name == agent_name:
                        src.primary_api = primary
                        src.fallback_images = fallbacks
                        break
                else:
                    self._agent_sources.append(AgentSource(
                        name=agent_name, primary_api=primary, fallback_images=fallbacks
                    ))
                success(f"Agent '{agent_name}' source: primary={primary}, fallback={fallbacks}")
                return True

            info("Usage:")
            info("  /models list                         — List models + catalog")
            info("  /models download <name>               — Download a catalog model")
            info("  /models url <url> [name]              — Download from any URL")
            info("  /models ollama <model> [name]         — Pull model via Ollama")
            info("  /models add <path> <name>             — Register a local GGUF file")
            info("  /models remove <name>                 — Remove a model")
            info("  /models source                       — Show agent AI source assignments")
            info("  /models source set <a> <api> [fb...]  — Set agent AI source")
            return True

        if parts[0] == "/evals":
            try:
                from evals.harness import EvalHarness
                from evals.datasets import get_all_prompts, get_domain_names
                from evals.reporter import save_report
                harness = EvalHarness(self)
                providers = self._providers()
                sub = parts[1].lower().strip() if len(parts) == 2 else "full"
                if sub == "list":
                    runs = harness.list_runs()
                    if runs:
                        success(f"Evaluation runs ({len(runs)}):")
                        for r in runs[:10]:
                            info(f"  {r['timestamp'][:19]} — quality: {r.get('avg_quality', 0):.1f} cost: ${r.get('total_cost', 0):.6f}")
                    else:
                        info("No eval runs yet. Use /evals full or /evals <domain>")
                    return True
                if sub in get_domain_names():
                    status_enter(f"Benchmarking domain: {sub}")
                    run = harness.run_domain_benchmark(sub, providers, count=5)
                else:
                    status_enter("Running full benchmark across all providers and domains")
                    run = harness.run_benchmark(get_all_prompts(), providers)
                saved = save_report({
                    "timestamp": run.timestamp, "providers_tested": run.providers_tested,
                    "domains_tested": run.domains_tested, "total_prompts": run.total_prompts,
                    "total_cost": run.total_cost, "avg_quality_score": run.avg_quality_score,
                    "avg_response_time_ms": run.avg_response_time_ms,
                    "by_provider": run.by_provider, "by_domain": run.by_domain, "results": run.results,
                })
                status_done(f"Benchmark complete: {run.total_prompts} prompts, quality {run.avg_quality_score:.1f}/100, cost ${run.total_cost:.6f}")
                for fmt, path in saved.items():
                    info(f"Report saved: {path} ({fmt})")
                info("Providers ranked:")
                for p in sorted(run.by_provider.items(), key=lambda x: x[1].get("avg_quality", 0), reverse=True):
                    info(f"  {p[0]}: {p[1].get('avg_quality', 0):.1f}/100  |  {p[1].get('avg_time_ms', 0):.0f}ms  |  errors: {p[1].get('errors', 0)}")
            except Exception as e:
                error(f"Eval failed: {e}")
            return True

        if parts[0] == "/train":
            from training.collector import TrainingCollector
            from training.export import export_all
            collector = TrainingCollector()
            sub = parts[1].lower().strip() if len(parts) >= 2 else "stats"
            sub_parts = parts[1].split(maxsplit=1) if len(parts) >= 2 else ["stats"]
            sub = sub_parts[0].lower() if sub_parts else "stats"

            if sub == "engine":
                status_enter("Training Smart Engine on all tools...")
                try:
                    result = self.engine.trainer.train_on_all_tools()
                    status_done(f"Engine trained: {result['trained']} tools, {result['errors']} errors")
                    info(self.engine.trainer.generate_tool_catalog())
                except Exception as e:
                    error(f"Engine training failed: {e}")
                return True

            if sub == "engine":
                status_enter("Training Smart Engine on all tools...")
                try:
                    result = self.engine.trainer.train_on_all_tools()
                    status_done(f"Engine trained: {result['trained']} tools, {result['errors']} errors")
                    info(self.engine.trainer.generate_tool_catalog())
                except Exception as e:
                    error(f"Engine training failed: {e}")
                return True
            if sub == "clear":
                collector.clear()
                success("Training data cleared")
                return True
            if sub == "export":
                paths = export_all(collector)
                success("Training data exported:")
                for fmt, path in paths.items():
                    info(f"  {fmt}: {path}")
                return True
            if sub in ("stats", ""):
                stats = collector.get_stats()
                engine_stats = self.engine.get_stats()
                success(f"Training data: {stats['total_examples']} examples ({stats['successful']} successful, {stats['success_rate']}%)")
                if stats['by_domain']:
                    info("By domain: " + ", ".join(f"{d}={c}" for d, c in sorted(stats['by_domain'].items())))
                if stats['by_provider']:
                    info("By provider: " + ", ".join(f"{p}={c}" for p, c in sorted(stats['by_provider'].items())))
                if stats['by_tool']:
                    info("By tool: " + ", ".join(f"{t}={c}" for t, c in sorted(stats['by_tool'].items())))
                info(f"Engine: {engine_stats['tools_trained']} tools trained, {engine_stats['execution_patterns']} patterns learned")
                return True
            info("Usage: /train stats | engine | export | clear")
            return True

        if parts[0] == "/enhance":
            try:
                from self.enhancer import auto_enhance
                status_enter("Running full self-enhancement cycle (benchmark + analysis + plan)")
                result = auto_enhance(self)
                status_done("Self-enhancement cycle complete")
                success(f"Quality: {result['avg_quality']:.1f}/100  |  Health: {result['overall_health']}  |  {result['recommendations']} recommendations")
                if result.get("reports"):
                    for fmt, path in result["reports"].items():
                        info(f"Report: {path} ({fmt})")
                plan = result.get("plan", {})
                if plan.get("immediate_actions"):
                    info("Immediate actions:")
                    for a in plan["immediate_actions"]:
                        info(f"  [{a['effort']}] {a['details']}")
                if plan.get("short_term_actions"):
                    info("Short-term actions:")
                    for a in plan["short_term_actions"]:
                        info(f"  [{a['effort']}] {a['details']}")
            except Exception as e:
                error(f"Self-enhancement failed: {e}")
            return True

        if parts[0] == "/tools":
            sub_parts = parts[1].strip().split(maxsplit=1) if len(parts) >= 2 else ["list"]
            sub = sub_parts[0].lower() if sub_parts else "list"
            if sub == "list":
                tools = self.engine.registry.list_tools()
                success(f"Smart Engine — {len(tools)} tools:")
                info(self.engine.registry.get_tool_descriptions())
                return True
            if sub == "search" and len(sub_parts) >= 2:
                query = sub_parts[1]
                tools = self.engine.registry.search_tools(query)
                if tools:
                    success(f"Tools matching '{query}':")
                    for t in tools:
                        info(f"  {t.name}: {t.description} ({t.source})")
                else:
                    info(f"No tools matching '{query}'")
                return True
            if sub == "stats":
                stats = self.engine.get_stats()
                success(f"Engine stats:")
                info(f"  Total tools: {stats['total_tools']}")
                for source, count in stats['by_source'].items():
                    info(f"  {source}: {count}")
                info(f"  Executions: {stats['executions']}")
                return True
            info("Usage: /tools list | search <query> | stats")
            return True

        if parts[0] == "/plan":
            if len(parts) < 2 or not parts[1].strip():
                info("Usage: /plan <task description>")
                return True
            task = parts[1].strip()
            status_enter(f"Planning: {task[:60]}...")
            steps = self.engine.planner.plan(task, self.engine.registry.list_tools())
            success(f"Plan — {len(steps)} steps:")
            for s in steps:
                deps = f" (after step {s.depends_on})" if s.depends_on else ""
                info(f"  Step {s.step_id}: [{s.tool}] {s.description}{deps}")
            return True

        if parts[0] == "/run":
            if len(parts) < 2 or not parts[1].strip():
                info("Usage: /run <task>")
                return True
            task = parts[1].strip()
            status_enter(f"Smart Engine executing: {task[:60]}...")
            try:
                result = self.engine.execute(task)
                status_done("Execution complete")
                assistant_message(result)
            except Exception as e:
                error(f"Execution failed: {e}")
            return True

        if parts[0] == "/compose":
            if len(parts) < 3:
                info("Usage: /compose <name> <desc> --pipes tool1 tool2 ...")
                return True
            rest = parts[1]
            args = rest.split(" --pipes ")
            if len(args) < 2:
                info("Usage: /compose <name> <desc> --pipes tool1 tool2 ...")
                return True
            name_desc = args[0].split(maxsplit=1)
            if len(name_desc) < 2:
                info("Usage: /compose <name> <desc> --pipes tool1 tool2 ...")
                return True
            name = name_desc[0]
            description = name_desc[1]
            pipeline = [t.strip() for t in args[1].split() if t.strip()]
            if not pipeline:
                info("Usage: /compose <name> <desc> --pipes tool1 tool2 ...")
                return True
            try:
                tool = self.engine.compose_tool(name, description, pipeline)
                success(f"Composed tool '{tool.name}': {tool.description}")
            except Exception as e:
                error(f"Composition failed: {e}")
            return True

        if parts[0] == "/generate":
            if len(parts) < 2 or not parts[1].strip():
                info("Usage: /generate <description of what the tool should do>")
                return True
            desc = parts[1].strip()
            status_enter(f"Generating tool for: {desc[:60]}...")
            try:
                tool = self.engine.suggest_new_tool(desc)
                status_done(f"Generated tool '{tool.name}'")
                info(f"  Description: {tool.description}")
                info(f"  Code preview ({len(tool.code or '')} chars):")
                for line in (tool.code or "# No code generated").split("\n")[:8]:
                    info(f"    {line}")
            except Exception as e:
                error(f"Generation failed: {e}")
            return True

        if parts[0] == "/help":
            command_table([
                ("/set key=value", "Update preferences"),
                ("/clear", "Clear conversation history"),
                ("/save <name>", "Save current session"),
                ("/load <name>", "Load a saved session"),
                ("/sessions", "List saved sessions"),
                ("/scan <text>", "Check text for leaked secrets"),
                ("/secrets", "Show saved secret references"),
                ("/usage", "Show token/cost usage"),
                ("/status", "Full self-check report"),
                ("/check <area>", "health | security | deps"),
                ("/skills", "List loaded skills"),
                ("/reload <area>", "skills | domains | config | all"),
                ("/learn k = v", "Save a fact into memory"),
                ("/recall <key>", "Retrieve a learned fact"),
                ("/forget <key>", "Remove a learned fact"),
                ("/evals [domain]", "Benchmark providers across domains"),
                ("/train stats", "Training data + Smart Engine training status"),
                ("/train engine", "Train Smart Engine on all tools (analyze + catalog)"),
                ("/train export", "Export training data (JSONL/JSON/CSV)"),
                ("/train clear", "Clear training data"),
                ("/enhance", "Full self-enhancement: benchmark → analyze → plan"),
                ("/model", "Show provider limits & switch models"),
                ("/models", "Manage local AI images (download/url/ollama/add/source)"),
                ("/tools", "Smart Engine: list/search tools"),
                ("/plan <task>", "Plan how to solve a task using tools"),
                ("/run <task>", "Execute a task with the Smart Engine"),
                ("/compose <n> <d> --pipes t1 t2", "Compose a new tool from existing ones"),
                ("/generate <desc>", "Generate a new tool via AI"),
                ("/cleanup", "Purge __pycache__ and other cached files"),
                ("/web", "Start web UI on :8642"),
                ("!command", "Run a shell command and show output"),
                ("exit / quit / bye", "Exit Pixel"),
            ], title="Commands")
            info("Tip: Run 'python main.py --tui' for the full-screen TUI (Ctrl+T=provider  Ctrl+D=usage  Ctrl+E=evals)")
            return True
        return False

    def _run_shell(self, command: str) -> None:
        import subprocess
        import shlex
        try:
            from utils.secretscanner import redact as redact_secrets
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout or result.stderr
            if not output:
                success(f"Command completed (exit code {result.returncode}) with no output")
                return
            if len(output) > 20000:
                output = output[:20000] + f"\n... (truncated, {len(output)} total chars)"

            safe = redact_secrets(output)
            assistant_message(f"```\n{safe.strip()}\n```")
            if result.returncode != 0:
                warn(f"Exit code: {result.returncode}")

        except subprocess.TimeoutExpired:
            error("Command timed out after 60 seconds")
        except FileNotFoundError as e:
            error(f"Command not found: {e}")
        except Exception as e:
            error(f"Shell command failed: {e}")

    def run(self):
        banner()
        info("Type your message or /help for commands")
        while True:
            try:
                if _RICH:
                    from rich.prompt import Prompt
                    user_input = Prompt.ask("[bold yellow]You[/bold yellow]").strip()
                else:
                    user_input = input("\033[1;33m  You\033[0m ").strip()
            except (KeyboardInterrupt, EOFError):
                goodbye()
                break
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                goodbye()
                break
            if user_input.startswith("/"):
                self._handle_command(user_input)
                continue
            if user_input.startswith("!"):
                self._run_shell(user_input[1:])
                continue
            user_message(user_input)
            status_enter("Pixel is thinking")
            response = self.ask(user_input)
            assistant_message(response)


def _startup_cleanup():
    try:
        from utils.cleanup import clean_on_startup
        clean_on_startup()
    except Exception:
        pass


def main():
    _startup_cleanup()

    parser = argparse.ArgumentParser(description="Pixel AI Assistant")
    parser.add_argument("--tui", action="store_true", help="Launch full-screen TUI mode")
    parser.add_argument("--web", action="store_true", help="Launch web UI server")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--cleanup", action="store_true", help="Purge caches and exit")
    args = parser.parse_args()

    if args.cleanup:
        from utils.cleanup import clean, format_size
        result = clean(dry_run=False)
        print(f"Cleaned {result['removed_dirs']} cache dirs, {result['removed_files']} files ({result['freed_human']})")
        return

    if args.debug:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    if args.web:
        import web_ui
        web_ui.run()
        return

    if args.tui:
        from tui.app import run_tui
        run_tui()
        return

    Pixel().run()


if __name__ == "__main__":
    main()
