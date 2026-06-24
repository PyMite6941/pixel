# Ideas — Pixel (AI Assistant)

- Populate `skills/`: implement at least two pluggable skill modules (e.g., weather lookup, calendar query) to prove out the architecture
- Conversation memory: persist the last N turns to a file so context survives restarts
- User preference file: let users set preferred domain, verbosity level, and default model via `config.py`
- Reminder skill: set a timed reminder that fires a desktop notification
- Wikipedia / web search skill inside `brain/search.py` — currently a stub
- Streaming responses: print tokens as they arrive instead of waiting for the full response
- CLI history: up-arrow to recall previous queries (readline integration)
- `--debug` flag that shows which domain was selected and why (from `q_arbiter.py` routing)
- Unit tests for `domain_registry.py` routing logic
- Plugin discovery: auto-load any `.py` file dropped into `skills/` without editing `domain_registry.py`
