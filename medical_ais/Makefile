.PHONY: setup start stop restart logs migrate ingest test test-unit test-integration lint format clean

# ── Infrastructure ─────────────────────────────────────────────
setup:
	@echo "Starting infrastructure services..."
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	sleep 15
	@echo "Running database migrations..."
	$(MAKE) migrate
	@echo "Setup complete. Run 'make ingest SOURCE=./data/documents' to build the knowledge graph."

start:
	docker-compose up -d
	@echo "Starting MAIS API server..."
	python main.py

stop:
	docker-compose down
	@echo "Services stopped."

restart:
	docker-compose restart

logs:
	docker-compose logs -f

# ── Database ───────────────────────────────────────────────────
migrate:
	@echo "Applying graph schema migrations..."
	python -m medical_ais.pipeline.graph_builder.schema_migrator
	@echo "Applying PostgreSQL migrations..."
	python -m medical_ais.migrations.apply_migrations
	@echo "Migrations complete."

# ── Pipeline ──────────────────────────────────────────────────
ingest:
	@if [ -z "$(SOURCE)" ]; then echo "Usage: make ingest SOURCE=./data/documents"; exit 1; fi
	@echo "Running full ingestion pipeline on: $(SOURCE)"
	python -m medical_ais.pipeline.pipeline_runner --source $(SOURCE)

ingest-update:
	@if [ -z "$(SOURCE)" ]; then echo "Usage: make ingest-update SOURCE=./data/new_docs"; exit 1; fi
	@echo "Running incremental ingestion on: $(SOURCE)"
	python -m medical_ais.pipeline.pipeline_runner --source $(SOURCE) --incremental

pipeline-status:
	python -m medical_ais.pipeline.pipeline_runner --status

# ── Testing ───────────────────────────────────────────────────
test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short -m integration

test-coverage:
	pytest tests/ --cov=medical_ais --cov-report=html --cov-report=term-missing --cov-fail-under=75

# ── Code Quality ──────────────────────────────────────────────
lint:
	python -m ruff check medical_ais/ tests/

format:
	python -m ruff format medical_ais/ tests/

# ── Cleanup ───────────────────────────────────────────────────
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	rm -rf htmlcov/ .coverage

clean-data:
	@echo "WARNING: This will delete all vector store and pipeline data."
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	rm -rf ./data/lancedb ./data/pipeline_cache
