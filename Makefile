.PHONY: help up down test broker-up broker-init broker-restart test-broker bench-broker gateway-dev gateway-up test-gateway

COMPOSE = docker compose --env-file .env -f infrastructure/compose/compose.yaml
# Depuis la machine hôte, le broker est joint par le port publié sur 127.0.0.1.
WITH_ENV = set -a; . ./.env; set +a; BROKER_URL=nats://localhost:4222;
UV_TEST = uv run --with-editable shared/python-common --with nats-py==2.16.0 --with pytest \
          --with pytest-asyncio --with jsonschema --with rfc3339-validator

help:
	@echo "make up             : démarrer la pile (Docker Compose)"
	@echo "make down           : arrêter la pile"
	@echo "make test           : tests unitaires de chaque service et de shared/python-common"
	@echo "make broker-up      : démarrer le broker et appliquer la topologie"
	@echo "make broker-init    : réappliquer infrastructure/broker/topology.json"
	@echo "make broker-restart : redémarrer le broker (les données sont conservées)"
	@echo "make test-broker    : tests d'intégration du broker (C8)"
	@echo "make bench-broker   : mesure du débit de publication (ADR 0002)"
	@echo "make gateway-dev    : certificats et sources de développement (une fois)"
	@echo "make gateway-up     : broker + passerelle d'ingestion"
	@echo "make test-gateway   : tests unitaires et d'intégration de la passerelle (C6)"

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

test:
	@for s in services/*/; do (cd $$s && python -m pytest -q; r=$$?; [ $$r -eq 0 ] || [ $$r -eq 5 ]) || exit 1; done
	$(UV_TEST) pytest -q -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function shared/python-common/tests

broker-up:
	@grep -Eq '^BROKER_TOKEN=.+' .env || { echo "BROKER_TOKEN vide dans .env : voir infrastructure/broker/README.md"; exit 1; }
	$(COMPOSE) up -d --wait broker
	$(COMPOSE) run --rm --build broker-init

broker-init:
	$(COMPOSE) run --rm --build broker-init

broker-restart:
	$(COMPOSE) restart broker

test-broker:
	$(WITH_ENV) $(UV_TEST) pytest -v -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration/broker

bench-broker:
	$(WITH_ENV) uv run --with nats-py==2.16.0 scripts/testing/bench_broker.py

gateway-dev:
	bash scripts/development/init_dev_gateway.sh

gateway-up: broker-up
	@test -f infrastructure/tls/dev/sources.json || { echo "Lancer d'abord : make gateway-dev"; exit 1; }
	$(COMPOSE) up -d --build --wait ingestion-gateway

test-gateway:
	cd services/ingestion-gateway && uv run --extra dev pytest -q -o asyncio_default_fixture_loop_scope=function
	$(WITH_ENV) $(UV_TEST) --with-editable services/ingestion-gateway --with httpx==0.28.1 \
	  pytest -v -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration/gateway
