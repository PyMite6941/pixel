import json
from pathlib import Path

import anthropic
from google import genai as google_genai
from groq import Groq

from config import Config, save_prefs
from brain.domain_registry import DomainRegistry
from utils.logger import get_logger

logger = get_logger(__name__)

_HISTORY_FILE = Path(__file__).parent / "memory" / "history.json"

_SYSTEM_PROMPT = (
    "You are Pixel, a sharp and friendly AI assistant. "
    "You give concise, accurate answers. "
    "For coding questions, provide working code with brief explanations. "
    "For general questions, be direct and helpful. "
    "Keep responses focused and avoid unnecessary filler."
)

_DOMAIN_HINTS = {
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
        self.groq = Groq(api_key=Config.GROQ_API_KEY)
        self.gemini = google_genai.Client(api_key=Config.GOOGLE_API_KEY)
        self.claude = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.registry = DomainRegistry()
        self.history: list[dict] = _load_history()

    def _build_messages(self, prompt: str, system: str) -> list[dict]:
        messages = [{"role": "system", "content": system}]
        messages.extend(self.history[-Config.MAX_HISTORY:])
        messages.append({"role": "user", "content": prompt})
        return messages

    def use_groq(self, messages: list[dict], smart: bool = False) -> str:
        model = Config.SMART_MODEL if smart else Config.FAST_MODEL
        response = self.groq.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content

    def use_gemini(self, prompt: str, system: str = "") -> str:
        from google.genai import types as genai_types
        config = None
        if system:
            config = genai_types.GenerateContentConfig(system_instruction=system)
        response = self.gemini.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text

    def use_claude(self, prompt: str, system: str = "") -> str:
        response = self.claude.messages.create(
            model=Config.CLAUDE_MODEL,
            max_tokens=1024,
            system=system or _SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def ask(self, prompt: str) -> str:
        domain = self.registry.route(prompt)
        logger.debug("Routed to domain: %s", domain)
        hint = _DOMAIN_HINTS.get(domain, "")
        system = _SYSTEM_PROMPT + hint
        messages = self._build_messages(prompt, system)

        preferred = Config.PREFERRED_PROVIDER
        providers = ["groq", "gemini", "claude"]
        if preferred in providers:
            providers.remove(preferred)
            providers.insert(0, preferred)

        reply = None
        last_error = None
        for provider in providers:
            try:
                if provider == "groq":
                    reply = self.use_groq(messages, smart=Config.SMART_MODE)
                elif provider == "gemini":
                    reply = self.use_gemini(prompt, system=system)
                elif provider == "claude":
                    reply = self.use_claude(prompt, system=system)
                if reply:
                    break
            except Exception as e:
                logger.warning("%s failed (%s), trying next", provider, e)
                last_error = e

        if reply is None:
            return f"All providers failed. Last error: {last_error}"

        self.history.append({"role": "user", "content": prompt})
        self.history.append({"role": "assistant", "content": reply})
        _save_history(self.history)
        return reply

    def _handle_command(self, cmd: str) -> bool:
        parts = cmd.split(maxsplit=1)
        if parts[0] == "/set" and len(parts) == 2:
            kv = parts[1].split("=", maxsplit=1)
            if len(kv) == 2:
                key, value = kv[0].strip(), kv[1].strip()
                save_prefs({key: value})
                print(f"Set {key} = {value}")
                return True
            print("Usage: /set key=value")
            return True
        if parts[0] == "/clear":
            self.history.clear()
            _save_history(self.history)
            print("Conversation cleared.")
            return True
        if parts[0] == "/help":
            print("Commands: /set key=value  /clear  /help  exit/quit/bye")
            return True
        return False

    def run(self):
        print("Pixel AI Assistant — type 'exit' to quit, '/help' for commands\n")
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye.")
                break
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Goodbye.")
                break
            if user_input.startswith("/"):
                self._handle_command(user_input)
                continue
            response = self.ask(user_input)
            print(f"Pixel: {response}\n")


if __name__ == "__main__":
    Pixel().run()
