.PHONY: help up down test broker-up broker-init broker-restart broker-reset test-broker bench-broker gateway-dev gateway-up test-gateway agents-up agents-check test-agents normalizer-up test-normalizer fetch-datasets bench-normalizer \
        dlq-list dlq-show dlq-replay dlq-purge dlq-monitor-up test-resilience \
        db-up db-migrate db-seed db-psql db-reset test-db rules-load detection-up test-detection bench-detection

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
	@echo "make broker-reset   : supprimer les données du broker et recréer les flux (développement)"
	@echo "make test-broker    : tests d'intégration du broker (C8)"
	@echo "make bench-broker   : mesure du débit de publication (ADR 0002)"
	@echo "make gateway-dev    : certificats et sources de développement (une fois)"
	@echo "make gateway-up     : broker + passerelle d'ingestion"
	@echo "make test-gateway   : tests unitaires et d'intégration de la passerelle (C6)"
	@echo "make agents-up      : passerelle + agent Fluent Bit de test + collecteur Syslog"
	@echo "make agents-check   : syntaxe des configurations des agents et du collecteur"
	@echo "make test-agents    : coupure réseau puis reconnexion, comptage avant/après (C7)"
	@echo "make normalizer-up  : passerelle + normalisation et enrichissement (C9, C10)"
	@echo "make fetch-datasets : télécharger les journaux publics de test (test-data/public)"
	@echo "make test-normalizer: tests unitaires, jeux publics et intégration de la normalisation"
	@echo "make bench-normalizer : débit de la normalisation (ENF-02)"
	@echo "make dlq-list       : contenu de la file de rejet par service et par motif (ARGS=\"-v --service ...\")"
	@echo "make dlq-show SEQ=n : un message de la file de rejet"
	@echo "make dlq-replay     : reprise depuis la file de rejet (ARGS=\"--reason ... --dry-run\")"
	@echo "make dlq-purge      : suppression dans la file de rejet (ARGS=\"--service ... --yes\")"
	@echo "make dlq-monitor-up : métriques Prometheus de la file de rejet (service dlq-monitor)"
	@echo "make test-resilience: scénarios S1 et S2, reprise depuis la file de rejet (C11)"
	@echo "make db-up          : PostgreSQL + migrations et mots de passe des comptes de service"
	@echo "make db-migrate     : réappliquer les migrations (infrastructure/database)"
	@echo "make db-seed        : copier les sources de développement dans config.sources"
	@echo "make db-psql        : console psql sur la base baolsec"
	@echo "make db-reset       : supprimer les données PostgreSQL et recréer le schéma (développement)"
	@echo "make test-db        : tests du schéma, des droits et des référentiels PostgreSQL"
	@echo "make rules-load     : charger les règles YAML de rules/ dans config.rules (nouvelle version si modifiée)"
	@echo "make detection-up   : passerelle + normalisation + PostgreSQL + détection (C12, C14)"
	@echo "make test-detection : tests unitaires et d'intégration de la détection"
	@echo "make bench-detection: débit de la détection (ENF-02)"

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

test:
	@for s in services/*/; do (cd $$s && uv run --quiet --extra dev pytest -q; r=$$?; [ $$r -eq 0 ] || [ $$r -eq 5 ]) || exit 1; done
	$(UV_TEST) pytest -q -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function shared/python-common/tests infrastructure/broker/tests

broker-up:
	@grep -Eq '^BROKER_TOKEN=.+' .env || { echo "BROKER_TOKEN vide dans .env : voir infrastructure/broker/README.md"; exit 1; }
	$(COMPOSE) up -d --wait broker
	$(COMPOSE) run --rm --build broker-init

broker-init:
	$(COMPOSE) run --rm --build broker-init

broker-restart:
	$(COMPOSE) restart broker

broker-reset:
	@echo "Supprime toutes les données du broker (flux, KV) puis recrée la topologie. Développement uniquement."
	$(COMPOSE) rm -sf broker
	docker volume rm -f baolsec_broker-data
	$(MAKE) broker-up

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
  -e BAOLSEC_WEBAPP_ACCESS_LOG=/tmp/a.log -e BAOLSEC_WEBAPP_APP_LOG=/tmp/b.log -e BAOLSEC_TEST_LOG=/tmp/t.log \
  -e BAOLSEC_LISTEN_PORT=514

agents-up: gateway-up
	@test -f infrastructure/tls/dev/collector.env || bash scripts/development/init_dev_gateway.sh
	mkdir -p test-data/runtime/agent && touch test-data/runtime/agent/auth-test.log
	$(COMPOSE_AGENTS) up -d agent-test syslog-collector

agents-check:
	@for c in linux/fluent-bit.yaml linux/fluent-bit-journald.yaml webapp/fluent-bit.yaml syslog-collector/fluent-bit.yaml test/fluent-bit-test.yaml; do \
	  echo "Fluent Bit : $$c"; \
	  docker run --rm $(FB_CHECK_ENV) -v $(CURDIR)/agents/fluent-bit:/agents:ro $(FB_IMAGE) \
	    /fluent-bit/bin/fluent-bit --dry-run -c /agents/$$c || exit 1; done
	@echo "Windows : vérifiée par un agent Windows réel (l'entrée winevtlog n'existe pas sous Linux)"

test-agents:
	$(WITH_ENV) $(UV_TEST) pytest -v -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration/agents

normalizer-up: gateway-up
	$(COMPOSE) up -d --build --wait normalization-worker

fetch-datasets:
	bash scripts/testing/fetch_public_datasets.sh

test-normalizer:
	cd services/normalization-worker && uv run --extra dev pytest -q -s -o asyncio_default_fixture_loop_scope=function
	$(WITH_ENV) $(UV_TEST) --with-editable services/normalization-worker --with httpx==0.28.1 \
	  pytest -v -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration/normalizer

bench-normalizer:
	$(WITH_ENV) uv run --with nats-py==2.16.0 scripts/testing/bench_normalizer.py 20000

DLQ_ADMIN = $(WITH_ENV) uv run --quiet --with nats-py==2.16.0 infrastructure/broker/dlq_admin.py

dlq-list:
	$(DLQ_ADMIN) list $(ARGS)

dlq-show:
	@test -n "$(SEQ)" || { echo "Usage : make dlq-show SEQ=<séquence>"; exit 1; }
	$(DLQ_ADMIN) show $(SEQ)

dlq-replay:
	$(DLQ_ADMIN) replay $(ARGS)

dlq-purge:
	$(DLQ_ADMIN) purge $(ARGS)

dlq-monitor-up: broker-up
	$(COMPOSE) up -d --build --wait dlq-monitor

test-resilience:
	$(WITH_ENV) $(UV_TEST) --with httpx==0.28.1 \
	  pytest -v -s -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration/resilience

# PostgreSQL vu depuis la machine hôte (port publié sur 127.0.0.1)
DB_ADMIN = postgresql://postgres:$$POSTGRES_PASSWORD@localhost:5432

db-up:
	@grep -Eq '^POSTGRES_PASSWORD=.+' .env || { echo "POSTGRES_PASSWORD vide dans .env : voir infrastructure/database/README.md"; exit 1; }
	$(COMPOSE) up -d --wait postgresql
	$(COMPOSE) run --rm --build db-migrate

db-migrate:
	$(COMPOSE) run --rm --build db-migrate

db-seed:
	$(WITH_ENV) DATABASE_ADMIN_URL=$(DB_ADMIN)/baolsec uv run --quiet --with "psycopg[binary]==3.3.8" infrastructure/database/seed_dev.py

db-psql:
	$(COMPOSE) exec postgresql psql -U postgres -d baolsec

db-reset:
	@echo "Supprime toutes les données PostgreSQL puis recrée le schéma. Développement uniquement."
	$(COMPOSE) rm -sf postgresql
	docker volume rm -f baolsec_postgres-data
	$(MAKE) db-up db-seed

test-db:
	$(WITH_ENV) TEST_POSTGRES_DSN=$(DB_ADMIN)/postgres $(UV_TEST) --with alembic==1.16.5 --with sqlalchemy==2.0.43 \
	  --with "psycopg[binary]==3.3.8" --with pydantic-settings==2.16.2 \
	  --with-editable services/ingestion-gateway --with-editable services/normalization-worker \
	  --with-editable services/detection-worker \
	  pytest -v -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function \
	  tests/integration/database tests/integration/gateway/test_postgres_registry.py tests/integration/normalizer/test_postgres_sources.py

rules-load:
	$(WITH_ENV) DATABASE_ADMIN_URL=$(DB_ADMIN)/baolsec uv run --quiet --with pyyaml==6.0.2 --with jsonschema==4.26.0 \
	  --with "psycopg[binary]==3.3.8" infrastructure/database/load_rules.py

detection-up: normalizer-up db-up
	$(MAKE) rules-load
	$(COMPOSE) up -d --build --wait detection-worker

test-detection:
	cd services/detection-worker && uv run --extra dev pytest -q -o asyncio_default_fixture_loop_scope=function
	$(WITH_ENV) DATABASE_ADMIN_URL=$(DB_ADMIN)/baolsec $(UV_TEST) --with-editable services/detection-worker --with httpx==0.28.1 \
	  --with pyyaml==6.0.2 pytest -v -s -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function tests/integration/detection

bench-detection:
	$(WITH_ENV) uv run --with nats-py==2.16.0 scripts/testing/bench_detection.py 20000
