.PHONY: up down logs test bench verify rebuild shell

## Bring the whole thing up (downloads + builds the index on first run).
up:
	docker compose up --build

down:
	docker compose down

## Wipe the cached dataset and index as well.
clean:
	docker compose down -v

logs:
	docker compose logs -f api

## Unit + integration tests on the synthetic fixture (no dataset needed).
test:
	python -m pytest -q

## Latency numbers for endpoint 2, run against the container.
bench:
	docker compose exec api python -m bench.bench \
		--url http://127.0.0.1:8000 --index-dir /data/index \
		--raw-dir /data/raw --requests 2000

## Independent re-derivation of the endpoint-1 total + endpoint-2 spot checks.
verify:
	docker compose exec api python -m scripts.verify \
		--raw-dir /data/raw --index-dir /data/index --url http://127.0.0.1:8000

rebuild:
	docker compose exec -e IMDB_REBUILD=1 api python -m app.build_index

shell:
	docker compose exec api bash
