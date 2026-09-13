.PHONY: up test lint burst down
up:
	docker compose up --build -d --wait
test:
	pytest -q
lint:
	ruff check .
	ruff format --check .
burst:
	sh scripts/burst.sh
down:
	docker compose down
