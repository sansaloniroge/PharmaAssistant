.PHONY: build up down logs test test-unit test-service test-docker fmt lint

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest -q

test-unit:
	pytest -q tests/app

test-service:
	pytest -q tests/integatrion/test_service_fastapi.py

test-docker:
	pytest -q -m docker tests/integatrion/test_container_api.py

fmt:
	poetry run ruff format .

lint:
	poetry run ruff check .
