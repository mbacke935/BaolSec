.PHONY: help up down test

help:
	@echo "make up    : démarrer la pile (Docker Compose)"
	@echo "make down  : arrêter la pile"
	@echo "make test  : lancer les tests unitaires de chaque service"

up:
	docker compose -f infrastructure/compose/compose.yaml up -d

down:
	docker compose -f infrastructure/compose/compose.yaml down

test:
	@for s in services/*/; do (cd $$s && python -m pytest -q; r=$$?; [ $$r -eq 0 ] || [ $$r -eq 5 ]) || exit 1; done
