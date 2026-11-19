"""Point d'entrée du service Indexing Worker (C19)."""
from __future__ import annotations

import asyncio
import json
import logging
import signal

import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from baolsec_common.messaging import BrokerUnavailable
from baolsec_common.messaging.nats_adapter import NatsBroker

from .config import Settings
from .indexers import AlertIndexer, EventIndexer, IncidentIndexer
from .opensearch_client import OpenSearchClient

log = logging.getLogger("indexing_worker")

EVENTS_INDEXED = Counter("baolsec_indexing_events_total", "Événements indexés")
ALERTS_INDEXED = Counter("baolsec_indexing_alerts_total", "Alertes indexées")
INCIDENTS_INDEXED = Counter("baolsec_indexing_incidents_total", "Incidents indexés")


async def connect_broker(settings: Settings) -> NatsBroker:
    delay = 1.0
    while True:
        try:
            return await NatsBroker.connect(
                settings.nats_url, settings.nats_token, name="indexing-worker"
            )
        except BrokerUnavailable as exc:
            log.warning("broker indisponible (%s), nouvel essai dans %.0fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


def create_health_app(os_client: OpenSearchClient) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        os_ok = os_client.ping()
        body = {"status": "ok" if os_ok else "degraded", "opensearch": "reachable" if os_ok else "unreachable"}
        return JSONResponse(body, status_code=200 if os_ok else 503)

    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


async def run(settings: Settings) -> None:
    os_client = OpenSearchClient(
        settings.opensearch_url,
        settings.opensearch_user,
        settings.opensearch_password,
    )

    broker = await connect_broker(settings)

    ev_consumer = await broker.subscribe(
        stream=settings.normalized_stream,
        durable=settings.normalized_durable,
    )
    al_consumer = await broker.subscribe(
        stream=settings.alerts_stream,
        durable=settings.alerts_durable,
    )
    inc_consumer = await broker.subscribe(
        stream=settings.incidents_stream,
        durable=settings.incidents_durable,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    app = create_health_app(os_client)
    server = uvicorn.Server(uvicorn.Config(
        app, host=settings.metrics_host, port=settings.metrics_port,
        log_level="warning", access_log=False,
    ))
    server.install_signal_handlers = lambda: None

    tasks = [
        asyncio.create_task(EventIndexer(os_client).run(ev_consumer, stop_event), name="event-indexer"),
        asyncio.create_task(AlertIndexer(os_client).run(al_consumer, stop_event), name="alert-indexer"),
        asyncio.create_task(IncidentIndexer(os_client).run(inc_consumer, stop_event), name="incident-indexer"),
        asyncio.create_task(server.serve(), name="supervision"),
    ]

    log.info("Indexing Worker démarré (port %d)", settings.metrics_port)
    await stop_event.wait()
    log.info("arrêt demandé")

    for t in tasks[:-1]:
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    server.should_exit = True
    await tasks[-1]
    await broker.close()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **({"error": self.formatException(record.exc_info)} if record.exc_info else {}),
        }, ensure_ascii=False)


def main() -> None:
    h = logging.StreamHandler()
    h.setFormatter(_JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[h])
    asyncio.run(run(Settings()))


if __name__ == "__main__":
    main()