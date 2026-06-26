# PixelCode — Docker convenience commands
# Usage: make build  or  make run  or  make run-local

.PHONY: build run run-local stop clean

build:
	docker compose build pixel

build-local:
	docker compose build pixel-standalone

run:
	docker compose up pixel

run-local:
	docker compose up pixel-standalone

run-detached:
	docker compose up -d pixel

run-local-detached:
	docker compose up -d pixel-standalone

stop:
	docker compose down

clean:
	docker compose down -v
	docker system prune -f

logs:
	docker compose logs -f pixel

shell:
	docker compose exec pixel bash

pull-model:
	docker compose exec ollama ollama pull llama3.2

list-models:
	docker compose exec ollama ollama list
