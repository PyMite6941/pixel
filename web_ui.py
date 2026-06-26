import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

app = FastAPI(title="Pixel AI — AI as a Service", version="1.0.0")

# --- Rate Limiting ---
limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS (locked down for production) ---
ALLOWED_ORIGINS = [
    "https://pixel-ai.store",
    "https://www.pixel-ai.store",
    "https://store.pixel-ai.com",
    "http://localhost:8642",
    "http://localhost:8788",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
)

# --- Security Headers Middleware ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# --- Auth ---
from service import AuthManager, UsageTracker, TIER_LIMITS
from service.auth_jwt import verify_license_jwt, create_license_jwt
from service.license_server import add_license_routes
from codes import TrialCodeManager

auth = AuthManager()
usage_tracker = UsageTracker()
codes = TrialCodeManager()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

pixel_instance = None
smart_engine = None


def _get_pixel():
    global pixel_instance
    if pixel_instance is None:
        from main import Pixel
        pixel_instance = Pixel()
    return pixel_instance


def _get_engine():
    global smart_engine
    if smart_engine is None:
        from engine import SmartEngine
        p = _get_pixel()
        smart_engine = SmartEngine(pixel_instance=p, llm_ask=p.ask)
    return smart_engine


async def _resolve_user(api_key: str = Depends(api_key_header)):
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    # Try JWT license key first (finance-kit style)
    claims = verify_license_jwt(api_key)
    if claims:
        user_id = f"jwt_{claims.get('jti', 'unknown')}"
        tier = claims.get("tier", "free")
        features = claims.get("features", [])
        user = auth._users.get(user_id)
        if not user:
            from service import User
            user = User(user_id=user_id, name=claims["sub"], email=claims["sub"], tier=tier)
            auth._users[user_id] = user
        return user, api_key

    # Fall back to legacy px_* API key
    user = auth.validate_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user, api_key


def _check_tier(user):
    limits = usage_tracker.check_limits(user)
    if not limits["within_limits"]:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded. Tier: {user.tier}. Tokens used: {limits['tokens_used']}/{limits['tokens_limit']}")
    return limits


# Register license endpoints (finance-kit style: /api/license/issue, /redeem, /validate)
add_license_routes(app)

# --- Web UI ---

_UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pixel AI</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; height: 100vh; display: flex; flex-direction: column; }
  header { background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }
  header h1 { color: #58a6ff; font-size: 18px; }
  #status { font-size: 12px; color: #8b949e; }
  #status span { color: #3fb950; }
  #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .msg { max-width: 80%; padding: 12px 16px; border-radius: 8px; line-height: 1.6; font-size: 14px; }
  .msg.user { background: #1f6feb; align-self: flex-end; color: #fff; }
  .msg.assistant { background: #21262d; border: 1px solid #30363d; align-self: flex-start; }
  .msg.system { background: #1c2128; border: 1px solid #d29922; align-self: center; font-size: 12px; color: #d29922; }
  .msg.error { background: #3d1f1f; border: 1px solid #f85149; align-self: center; }
  .msg pre { background: #0d1117; padding: 12px; border-radius: 6px; overflow-x: auto; font-size: 13px; margin: 8px 0; }
  .msg code { background: #161b22; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
  .msg pre code { background: none; padding: 0; }
  .msg p { margin: 4px 0; }
  .msg ul, .msg ol { margin: 4px 0; padding-left: 20px; }
  .msg li { margin: 2px 0; }
  .msg h1, .msg h2, .msg h3 { margin: 12px 0 4px 0; color: #58a6ff; }
  .msg h1 { font-size: 18px; }
  .msg h2 { font-size: 16px; }
  .msg h3 { font-size: 14px; }
  .msg strong { color: #f0f6fc; }
  .msg em { color: #8b949e; }
  .msg blockquote { border-left: 3px solid #30363d; padding-left: 12px; color: #8b949e; margin: 8px 0; }
  #input-row { border-top: 1px solid #30363d; padding: 12px 20px; display: flex; gap: 8px; background: #161b22; }
  #input { flex: 1; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px 12px; color: #c9d1d9; font-size: 14px; outline: none; }
  #input:focus { border-color: #58a6ff; }
  #send { background: #238636; color: #fff; border: none; border-radius: 6px; padding: 8px 20px; cursor: pointer; font-size: 14px; }
  #send:hover { background: #2ea043; }
  #send:disabled { opacity: 0.5; cursor: not-allowed; }
  .loading { color: #8b949e; font-style: italic; align-self: center; }
</style>
</head>
<body>
<header>
  <h1>Pixel AI</h1>
  <div id="status">Engine: <span id="engine-status">ready</span></div>
</header>
<div id="chat"></div>
<div id="input-row">
  <input id="input" type="text" placeholder="Type a message..." autofocus />
  <button id="send" onclick="send()">Send</button>
</div>
<script>
let apiKey = localStorage.getItem('pixel_api_key') || '';
let loading = false;
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function renderMarkdown(text) {
  let t = escapeHtml(text);
  t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  t = t.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  t = t.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  t = t.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  t = t.replace(/\*\*(\S.*?\S)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\*(\S.*?\S)\*/g, '<em>$1</em>');
  t = t.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  t = t.replace(/^- (.+)$/gm, '<li>$1</li>');
  t = t.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
  t = t.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');
  t = t.replace(/((?:<li>.*<\/li>\n?)+)<\/ul>/g, '<ol>$1</ol>');
  t = t.replace(/\n\n/g, '</p><p>');
  t = '<p>' + t + '</p>';
  t = t.replace(/<p><\/p>/g, '');
  t = t.replace(/<\/ul>\n?<ul>/g, '');
  t = t.replace(/<\/ol>\n?<ol>/g, '');
  return t;
}

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  if (role === 'assistant') {
    div.innerHTML = renderMarkdown(content);
  } else {
    div.textContent = content;
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

let streamAccumulator = '';
let streamMsgDiv = null;

function updateStream(content) {
  streamAccumulator = content;
  if (streamMsgDiv) {
    streamMsgDiv.innerHTML = renderMarkdown(content);
    chat.scrollTop = chat.scrollHeight;
  }
}

async function send() {
  const text = input.value.trim();
  if (!text || loading) return;
  input.value = '';

  if (!apiKey) {
    const key = prompt('Enter your Pixel API key:');
    if (!key) return;
    apiKey = key;
    localStorage.setItem('pixel_api_key', key);
  }

  addMessage('user', text);
  loading = true;
  sendBtn.disabled = true;

  const loadDiv = document.createElement('div');
  loadDiv.className = 'loading';
  loadDiv.textContent = 'Pixel is thinking...';
  chat.appendChild(loadDiv);

  streamAccumulator = '';
  streamMsgDiv = null;

  try {
    const res = await fetch('/api/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
      body: JSON.stringify({ prompt: text, mode: 'auto' })
    });
    if (!res.ok) {
      const err = await res.json();
      loadDiv.remove();
      addMessage('error', 'Error: ' + (err.detail || res.statusText));
      return;
    }

    loadDiv.remove();
    streamMsgDiv = addMessage('assistant', '');
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line);
          if (data.done) { streamAccumulator = ''; streamMsgDiv = null; break; }
          if (data.token) updateStream(streamAccumulator + data.token);
        } catch {}
      }
    }
  } catch (e) {
    loadDiv.remove();
    addMessage('error', 'Network error: ' + e.message);
  } finally {
    loading = false;
    sendBtn.disabled = false;
    input.focus();
    streamAccumulator = '';
    streamMsgDiv = null;
  }
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!loading) send();
  }
});
</script>
</body>
</html>
"""


@app.get("/")
async def root():
    return HTMLResponse(_UI_HTML)


# --- Auth Endpoints ---

@app.post("/api/auth/signup")
@limiter.limit("10/minute")
async def signup(req: Request):
    body = await req.json()
    name = body.get("name", "User")
    email = body.get("email", f"user_{int(time.time())}@pixel.ai")
    tier = body.get("tier", "free")
    if tier not in TIER_LIMITS:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}. Options: {', '.join(TIER_LIMITS.keys())}")
    user = auth.create_user(name, email, tier)

    # Issue JWT license key (finance-kit style)
    jwt_key = create_license_jwt(email, tier=tier)

    return JSONResponse({
        "user_id": user.user_id,
        "tier": user.tier,
        "api_key": jwt_key,
        "token_type": "bearer",
        "limits": TIER_LIMITS[tier],
    })


@app.post("/api/auth/redeem")
async def redeem_code(req: Request, auth_user=Depends(_resolve_user)):
    user, api_key = auth_user
    body = await req.json()
    code_str = body.get("code", "").upper().strip()
    if not code_str:
        raise HTTPException(status_code=400, detail="code required")
    result = codes.redeem_code(code_str, user.user_id, api_key)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return JSONResponse(result)


@app.post("/api/auth/redeem-with-signup")
async def redeem_with_signup(req: Request):
    """Sign up using a trial code — website users don't need an API key upfront."""
    body = await req.json()
    code_str = body.get("code", "").upper().strip()
    name = body.get("name", "Trial User")
    if not code_str:
        raise HTTPException(status_code=400, detail="code required")

    validation = codes.validate_code(code_str)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["reason"])

    tier = validation.get("tier", "pro")
    user = auth.create_user(name, f"trial_{int(time.time())}@pixel.ai", tier)
    api_key = auth.create_api_key(user.user_id, "trial")
    redeem_result = codes.redeem_code(code_str, user.user_id, api_key.key)

    return JSONResponse({
        "user_id": user.user_id,
        "tier": tier,
        "api_key": api_key.key,
        "trial_days": redeem_result.get("days", 30),
        "expires_at": redeem_result.get("expires_at"),
    })


# --- Trial Code Endpoints (for websites) ---

@app.post("/api/codes/generate")
async def generate_code(req: Request):
    """Websites call this with their website key to generate trial codes."""
    body = await req.json()
    ws_key = body.get("website_key", "")
    count = body.get("count", 1)
    tier = body.get("tier", "pro")
    days = body.get("days", 30)

    website = codes.validate_website_key(ws_key)
    if not website:
        raise HTTPException(status_code=401, detail="Invalid website key")

    if count > 100:
        raise HTTPException(status_code=400, detail="Max 100 codes per request")
    if days > 90:
        raise HTTPException(status_code=400, detail="Max 90 days")
    if tier not in TIER_LIMITS:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")

    codes_list = codes.generate_batch(count, created_by=website.name, tier=tier, days_valid=days)
    return JSONResponse({
        "success": True,
        "generated": len(codes_list),
        "codes": [c.code for c in codes_list],
        "tier": tier,
        "days_valid": days,
    })


@app.post("/api/codes/validate")
async def validate_code_api(req: Request):
    """Public endpoint to check if a code is valid (no auth needed)."""
    body = await req.json()
    code_str = body.get("code", "").upper().strip()
    if not code_str:
        raise HTTPException(status_code=400, detail="code required")
    result = codes.validate_code(code_str)
    return JSONResponse(result)


@app.get("/api/codes/stats")
async def codes_stats(auth_user=Depends(_resolve_user)):
    return JSONResponse(codes.get_stats())


@app.post("/api/auth/keys")
async def create_key(req: Request, auth_user=Depends(_resolve_user)):
    user, api_key = auth_user
    body = await req.json()
    name = body.get("name", f"key_{int(time.time())}")

    tier = body.get("tier", user.tier)
    if tier not in TIER_LIMITS:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")

    # Issue JWT license key (finance-kit style)
    jwt_key = create_license_jwt(user.email, tier=tier)
    return JSONResponse({"api_key": jwt_key, "token_type": "bearer", "name": name, "tier": tier})


# --- Smart Engine API (requires API key) ---

@app.post("/api/ask")
async def api_ask(req: Request, auth_user=Depends(_resolve_user)):
    user, api_key = auth_user
    _check_tier(user)
    body = await req.json()
    prompt = body.get("prompt", "")
    mode = body.get("mode", "auto")  # auto, smart, direct

    p = _get_pixel()

    if mode == "smart":
        engine = _get_engine()
        reply = engine.execute(prompt)
    elif mode == "auto":
        engine = _get_engine()
        tools = engine.find_tools_for(prompt)
        if tools:
            reply = engine.execute(prompt)
        else:
            reply = p.ask(prompt)
    else:
        reply = p.ask(prompt)

    total_tokens = len(prompt.split()) * 1.5 + len(reply.split()) * 1.5
    cost = (total_tokens / 1000) * TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])["cost_per_1k_tokens"]
    usage_tracker.track(user.user_id, api_key, input_tokens=int(len(prompt.split()) * 1.5),
                        output_tokens=int(len(reply.split()) * 1.5), cost=cost)

    return JSONResponse({"reply": reply, "mode": mode})


@app.post("/api/ask/stream")
async def api_ask_stream(req: Request, auth_user=Depends(_resolve_user)):
    user, api_key = auth_user
    _check_tier(user)
    body = await req.json()
    prompt = body.get("prompt", "")
    mode = body.get("mode", "auto")

    p = _get_pixel()

    collected_reply = ""

    if mode == "smart":
        engine = _get_engine()
        collected_reply = engine.execute(prompt)
        chunks = [collected_reply]
    else:
        chunks = list(p.ask_stream(prompt, ""))
        collected_reply = "".join(chunks)

    async def generate():
        for chunk in chunks:
            yield json.dumps({"token": chunk}) + "\n"
        yield json.dumps({"done": True}) + "\n"

        total_prompt_tokens = int(len(prompt.split()) * 1.5)
        total_output_tokens = int(len(collected_reply.split()) * 1.5)
        usage_tracker.track(user.user_id, api_key,
                            input_tokens=total_prompt_tokens,
                            output_tokens=total_output_tokens)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


# --- Engine Endpoints ---

@app.get("/api/engine/tools")
async def api_engine_tools(auth_user=Depends(_resolve_user)):
    engine = _get_engine()
    tools = engine.registry.list_tools()
    return JSONResponse([
        {"name": t.name, "description": t.description, "source": t.source, "parameters": t.parameters}
        for t in tools
    ])


@app.post("/api/engine/compose")
async def api_engine_compose(req: Request, auth_user=Depends(_resolve_user)):
    user, api_key = auth_user
    _check_tier(user)
    body = await req.json()
    name = body.get("name")
    description = body.get("description")
    pipeline = body.get("pipeline", [])
    if not all([name, description, pipeline]):
        raise HTTPException(status_code=400, detail="name, description, and pipeline required")
    engine = _get_engine()
    tool = engine.compose_tool(name, description, pipeline)
    return JSONResponse({"name": tool.name, "description": tool.description, "source": "composed"})


@app.post("/api/engine/generate")
async def api_engine_generate(req: Request, auth_user=Depends(_resolve_user)):
    user, api_key = auth_user
    _check_tier(user)
    body = await req.json()
    description = body.get("description")
    if not description:
        raise HTTPException(status_code=400, detail="description required")
    engine = _get_engine()
    tool = engine.suggest_new_tool(description, body.get("parameters"))
    return JSONResponse({"name": tool.name, "description": tool.description, "source": "generated", "code": tool.code})


@app.post("/api/engine/plan")
async def api_engine_plan(req: Request, auth_user=Depends(_resolve_user)):
    body = await req.json()
    task = body.get("task", "")
    engine = _get_engine()
    steps = engine.planner.plan(task, engine.registry.list_tools())
    return JSONResponse([
        {"step": s.step_id, "tool": s.tool, "action": s.action,
         "params": s.params, "description": s.description, "depends_on": s.depends_on}
        for s in steps
    ])


@app.get("/api/engine/stats")
async def api_engine_stats(auth_user=Depends(_resolve_user)):
    engine = _get_engine()
    return JSONResponse(engine.get_stats())


# --- Legacy / Existing Endpoints ---

@app.get("/api/status")
async def api_status(auth_user=Depends(_resolve_user)):
    p = _get_pixel()
    from memory.token_tracker import summary
    s = summary()
    return JSONResponse({
        "providers": p._providers(),
        "skills": p.skills.skill_names,
        "engine_tools": len(_get_engine().registry.list_tools()),
        "history_turns": len(p.history),
        "total_cost": s.get("cost", 0),
        "total_tokens": s.get("input_tokens", 0) + s.get("output_tokens", 0),
    })


@app.get("/api/sessions")
async def api_sessions(auth_user=Depends(_resolve_user)):
    from memory.session_manager import list_sessions
    return JSONResponse(list_sessions())


@app.get("/api/skills")
async def api_skills(auth_user=Depends(_resolve_user)):
    p = _get_pixel()
    return JSONResponse([
        {"name": name, "description": skill.description}
        for name, skill in p.skills.skills.items()
    ])


@app.post("/api/command")
async def api_command(req: Request, auth_user=Depends(_resolve_user)):
    body = await req.json()
    cmd = body.get("command", "")
    p = _get_pixel()
    handled = p._handle_command(cmd)
    if handled:
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "unknown_command", "command": cmd})


# --- Admin endpoints (no auth for local dev) ---

@app.get("/api/admin/users")
async def admin_users():
    return JSONResponse([
        {"user_id": u.user_id, "name": u.name, "email": u.email, "tier": u.tier, "active": u.active}
        for u in auth.list_users()
    ])


@app.get("/api/admin/usage")
async def admin_usage():
    records = {}
    for u in auth.list_users():
        rec = usage_tracker.get_usage(u.user_id)
        if rec:
            records[u.user_id] = {"tokens": rec.input_tokens + rec.output_tokens, "requests": rec.requests, "cost": rec.cost}
    return JSONResponse(records)


# --- Evals / Training (legacy) ---

@app.post("/api/evals/run")
async def api_evals_run(req: Request, auth_user=Depends(_resolve_user)):
    body = await req.json()
    domain = body.get("domain")
    p = _get_pixel()
    from evals.harness import EvalHarness
    from evals.datasets import get_all_prompts, get_domain_names
    from evals.reporter import save_report
    harness = EvalHarness(p)
    providers = p._providers()
    try:
        if domain and domain in get_domain_names():
            run = harness.run_domain_benchmark(domain, providers, count=5)
        else:
            run = harness.run_benchmark(get_all_prompts(), providers)
        saved = save_report({
            "timestamp": run.timestamp, "providers_tested": run.providers_tested,
            "domains_tested": run.domains_tested, "total_prompts": run.total_prompts,
            "total_cost": run.total_cost, "avg_quality_score": run.avg_quality_score,
            "avg_response_time_ms": run.avg_response_time_ms,
            "by_provider": run.by_provider, "by_domain": run.by_domain, "results": run.results,
        })
        return JSONResponse({
            "status": "complete", "total_prompts": run.total_prompts,
            "avg_quality": run.avg_quality_score, "total_cost": run.total_cost,
            "by_provider": run.by_provider, "by_domain": run.by_domain, "reports_saved": saved,
        })
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/api/evals/runs")
async def api_evals_runs():
    from evals.harness import EvalHarness
    harness = EvalHarness()
    return JSONResponse(harness.list_runs())


@app.get("/api/training/stats")
async def api_training_stats(auth_user=Depends(_resolve_user)):
    from training.collector import TrainingCollector
    collector = TrainingCollector()
    return JSONResponse(collector.get_stats())


@app.get("/api/training/export")
async def api_training_export(fmt: str = "json", auth_user=Depends(_resolve_user)):
    from training.collector import TrainingCollector
    from training.export import export_jsonl, export_json, export_csv
    collector = TrainingCollector()
    exporters = {"jsonl": export_jsonl, "json": export_json, "csv": export_csv}
    exporter = exporters.get(fmt, export_json)
    path = exporter(collector)
    return JSONResponse({"exported": True, "format": fmt, "path": path, "count": len(collector.examples)})


def run():
    import uvicorn
    print("Pixel AI — AI as a Service")
    print("=" * 40)
    print(f"  Web UI:    http://localhost:8642")
    print(f"  API:       http://localhost:8642/api")
    print(f"  Docs:      http://localhost:8642/docs")
    print(f"  License:   http://localhost:8642/api/license")
    print(f"")
    print(f"Quick start:")
    print(f"  1. Sign up:   POST /api/auth/signup  {{\"name\":\"you\",\"tier\":\"free\"}}")
    print(f"     → Returns JWT license key (finance-kit style)")
    print(f"  2. Chat:      POST /api/ask  with X-API-Key: <jwt>")
    print(f"  3. Tiers:     {', '.join(TIER_LIMITS.keys())}")
    print(f"  4. Redeem:    POST /api/license/redeem  with tx_hash (on-chain USDC)")
    print(f"  5. Validate:  POST /api/license/validate")
    print(f"")
    uvicorn.run(app, host="0.0.0.0", port=8642, log_level="info")


if __name__ == "__main__":
    run()
