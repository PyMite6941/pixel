# =============================================================================
# Stage 1: base — Python environment with all dependencies
# =============================================================================
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -c "from utils.cleanup import clean; clean(max_age=0)"

ENV LOG_LEVEL=INFO
EXPOSE 8642

# Default: web UI server (works with external Ollama or cloud APIs)
CMD ["python", "main.py", "--web"]


# =============================================================================
# Stage 2: local-ai — includes Ollama with a local model for offline use
# =============================================================================
FROM base AS local-ai

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_PORT=11434
ENV OLLAMA_KEEP_ALIVE=24h
ENV OLLAMA_MODEL=llama3.2

EXPOSE 11434

COPY docker-entrypoint.sh /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
