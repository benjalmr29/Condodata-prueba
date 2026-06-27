.PHONY: up down logs shell test lint dbt-run dbt-test dbt-docs fernet-key

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

shell:
	docker compose exec postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

test:
	python -m pytest tests/ -v --cov=ingestion --cov=api --cov-report=term-missing

lint:
	ruff check .
	mypy ingestion/ api/

dbt-run:
	cd dbt && dbt run

dbt-test:
	cd dbt && dbt test

dbt-docs:
	cd dbt && dbt docs generate && dbt docs serve

fernet-key:
	python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

setup:
	pip install -r requirements-dev.txt
	pre-commit install
	cp .env.example .env
	@echo "Edita .env con tus credenciales y corre 'make up'"
