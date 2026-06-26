#!/bin/bash
set -e

echo "[Pixel] Starting local AI image..."
echo "[Pixel] Python: $(python --version)"
echo "[Pixel] Platform: $(uname -m)"

# Start Ollama in background
if command -v ollama &> /dev/null; then
    echo "[Pixel] Starting Ollama server..."
    ollama serve &
    OLLAMA_PID=$!

    # Wait for Ollama to be ready
    for i in $(seq 1 30); do
        if curl -s http://${OLLAMA_HOST:-0.0.0.0}:${OLLAMA_PORT:-11434}/api/tags > /dev/null 2>&1; then
            echo "[Pixel] Ollama ready"
            break
        fi
        echo "[Pixel] Waiting for Ollama... ($i/30)"
        sleep 2
    done

    # Pull model if not present
    MODEL=${OLLAMA_MODEL:-llama3.2}
    if ! curl -s http://${OLLAMA_HOST:-0.0.0.0}:${OLLAMA_PORT:-11434}/api/tags | grep -q "\"name\":\"$MODEL\""; then
        echo "[Pixel] Pulling model: $MODEL (this may take a while on first run)..."
        ollama pull "$MODEL"
        echo "[Pixel] Model $MODEL ready"
    else
        echo "[Pixel] Model $MODEL already cached"
    fi
else
    echo "[Pixel] Ollama not installed — running in cloud-only mode"
fi

# Clean caches
python -c "from utils.cleanup import clean; clean(max_age=0)"

echo "[Pixel] Starting Pixel AI..."
echo "[Pixel] Web UI: http://localhost:8642"
echo "[Pixel] Ollama: http://localhost:11434"

# Launch Pixel (TUI if TTY available, otherwise web server)
if [ -t 0 ]; then
    exec python main.py --tui
else
    exec python main.py --web
fi
