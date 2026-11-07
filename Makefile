.PHONY: up down logs shell migrate makemigrations test test-unit test-integration test-api test-e2e coverage lint check
up:
	docker compose up --build
down:
	docker compose down
logs:
	docker compose logs -f web
shell:
	docker compose exec web python manage.py shell
migrate:
	docker compose exec web python manage.py migrate
makemigrations:
	docker compose exec web python manage.py makemigrations
test:
	docker compose --profile test run --rm tests
test-unit:
	docker compose --profile test run --rm tests pytest -m unit
test-integration:
	docker compose --profile test run --rm tests pytest -m integration
test-api:
	docker compose --profile test run --rm tests pytest -m api
test-e2e:
	docker compose --profile e2e run --rm e2e
coverage:
	docker compose --profile test run --rm tests pytest --cov=apps --cov-report=term-missing --cov-report=html
lint:
	docker compose --profile test run --rm tests ruff check .
check: lint test
