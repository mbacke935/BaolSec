.PHONY: help up down test broker-up broker-init broker-restart test-broker bench-broker gateway-dev gateway-up test-gateway agents-up agents-check test-agents

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
	@echo "make agents-up      : passerelle + agent Fluent Bit de test + relais Syslog"
	@echo "make agents-check   : syntaxe des configurations des agents et du relais"
	@echo "make test-agents    : coupure réseau puis reconnexion, comptage avant/après (C7)"

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

COMPOSE_AGENTS = $(COMPOSE) --profile agents-test
FB_IMAGE = fluent/fluent-bit:5.1.5
FB_CHECK_ENV = -e BAOLSEC_GATEWAY_HOST=passerelle -e BAOLSEC_GATEWAY_PORT=8443 -e BAOLSEC_SOURCE_TOKEN=x \
  -e BAOLSEC_CA_FILE=/agents/README.md -e BAOLSEC_STATE_DIR=/tmp -e BAOLSEC_BUFFER_LIMIT=1G \
  -e BAOLSEC_WEBAPP_ACCESS_LOG=/tmp/a.log -e BAOLSEC_WEBAPP_APP_LOG=/tmp/b.log -e BAOLSEC_TEST_LOG=/tmp/t.log

agents-up: gateway-up
	@test -f infrastructure/tls/dev/agent-test.env || bash scripts/development/init_dev_gateway.sh
	mkdir -p test-data/runtime/agent && touch test-data/runtime/agent/auth-test.log
	$(COMPOSE_AGENTS) up -d --build agent-test syslog-relay

agents-check:
	@for c in linux/fluent-bit.yaml linux/fluent-bit-journald.yaml webapp/fluent-bit.yaml test/fluent-bit-test.yaml; do \
	  echo "Fluent Bit : $$c"; \
	  docker run --rm $(FB_CHECK_ENV) -v $(CURDIR)/agents/fluent-bit:/agents:ro $(FB_IMAGE) \
	    /fluent-bit/bin/fluent-bit --dry-run -c /agents/$$c || exit 1; done
	@echo "Windows : vérifiée par un agent Windows réel (l'entrée winevtlog n'existe pas sous Linux)"
	docker build -q -t baolsec-syslog-relay agents/syslog-relay >/dev/null
	@test -f infrastructure/tls/dev/syslog-relay.crt || { echo "Lancer d'abord : make gateway-dev"; exit 1; }
	docker run --rm -e BAOLSEC_GATEWAY_HOST=passerelle -v $(CURDIR)/infrastructure/tls/dev:/etc/baolsec-relay:ro \
	  baolsec-syslog-relay rsyslogd -N1 -f /etc/rsyslog-baolsec.conf

test-agents:
	$(WITH_ENV) $(UV_TEST) pytest -v -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration/agents
