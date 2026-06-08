.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup seed api ui eval docker clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv and install backend deps
	python3 -m venv $(VENV) && $(PIP) install -r requirements.txt

seed: ## Generate the demo SQLite DB and PDF corpus
	$(PY) scripts/seed_data.py && $(PY) scripts/make_pdfs.py

api: ## Run the FastAPI backend on :8000
	$(VENV)/bin/uvicorn app.main:app --reload --port 8000

ui: ## Install + run the Next.js frontend on :3000
	cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev

eval: ## Run the routing/retrieval eval across all demo questions
	$(PY) -m scripts.eval

docker: ## Build and run everything with docker compose
	docker compose up --build

clean: ## Remove caches and generated artifacts
	rm -rf data/cache __pycache__ app/__pycache__ ui/.next
