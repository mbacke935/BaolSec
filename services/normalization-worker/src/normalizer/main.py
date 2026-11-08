"""Démarrage du service de normalisation : broker, référentiel des sources, consommation, supervision."""
from __future__ import annotations

import asyncio
import json
import logging
import signal

import uvicorn

from baolsec_common.messaging import BrokerUnavailable
from baolsec_common.messaging.nats_adapter import NatsBroker

from .config import Settings
from .enrich import Enricher
from .health import create_health_app
from .normalize import Normalizer
from .sources import SourcesCache
from .worker import Worker

log = logging.getLogger("normalizer")


async def connect_broker(settings: Settings) -> NatsBroker:
    delay = 1.0
    while True:
        try:
            return await NatsBroker.connect(settings.broker_url, settings.broker_token, name="normalization-worker")
        except BrokerUnavailable as exc:
            log.warning("broker indisponible au démarrage (%s), nouvel essai dans %.0fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


def make_registry(settings: Settings):
    if settings.source_registry == "postgres":
        from .sources.postgres import PostgresSourceRegistry
        return PostgresSourceRegistry(settings.postgres_dsn)
    from .sources.file import FileSourceRegistry
    return FileSourceRegistry(settings.sources_file)


async def run(settings: Settings) -> None:
    cache = SourcesCache(make_registry(settings), settings.sources_refresh_s, settings.sources_max_stale_s)
    normalizer = Normalizer(settings.contracts_dir, Enricher(cache, settings.internal_networks), settings.tz)
    broker = await connect_broker(settings)
    worker = Worker(broker, normalizer, cache, stream=settings.stream, durable=settings.durable,
                    output_subject=settings.output_subject, batch=settings.fetch_batch,
                    publish_timeout_s=settings.publish_timeout_s)
    supervision = uvicorn.Server(uvicorn.Config(
        create_health_app(cache, lambda: broker.connected),
        host=settings.metrics_host, port=settings.metrics_port, log_level="warning", access_log=False))
    supervision.install_signal_handlers = lambda: None

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)
    cache_task = asyncio.create_task(cache.run(), name="sources-cache")
    http_task = asyncio.create_task(supervision.serve(), name="supervision")
    log.info("normalisation démarrée : %s/%s → %s", settings.stream, settings.durable, settings.output_subject)
    try:
        await worker.run()     # se termine après SIGTERM, une fois le lot en cours acquitté
    finally:
        log.info("arrêt demandé")
        supervision.should_exit = True
        await http_task
        cache_task.cancel()
        await broker.close()


class JsonFormatter(logging.Formatter):
    """Journaux structurés JSON (C3 4.1)."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **({"error": self.formatException(record.exc_info)} if record.exc_info else {}),
        }, ensure_ascii=False)


def main() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    asyncio.run(run(Settings()))


if __name__ == "__main__":
    main()
