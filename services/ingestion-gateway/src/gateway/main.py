"""Démarrage de la passerelle : broker, cache des sources, HTTPS, Syslog TLS, supervision."""
from __future__ import annotations

import asyncio
import json
import logging
import signal

import uvicorn

from baolsec_common.messaging import BrokerUnavailable
from baolsec_common.messaging.nats_adapter import NatsBroker

from .config import Settings
from .health import create_health_app
from .http import create_app
from .publisher import RawEventPublisher
from .rate_limit import RateLimiter
from .sources_cache import SourcesCache
from .syslog import SyslogServer, tls_context

log = logging.getLogger("gateway")


async def connect_broker(settings: Settings) -> NatsBroker:
    delay = 1.0
    while True:
        try:
            return await NatsBroker.connect(settings.broker_url, settings.broker_token, name="ingestion-gateway")
        except BrokerUnavailable as exc:
            log.warning("broker indisponible au démarrage (%s), nouvel essai dans %.0fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


def make_registry(settings: Settings):
    if settings.source_registry == "postgres":
        from .sources_cache.postgres import PostgresSourceRegistry
        return PostgresSourceRegistry(settings.postgres_dsn)
    from .sources_cache.file import FileSourceRegistry
    return FileSourceRegistry(settings.sources_file)


async def run(settings: Settings) -> None:
    cache = SourcesCache(make_registry(settings), settings.sources_refresh_s, settings.sources_max_stale_s)
    broker = await connect_broker(settings)
    publisher = RawEventPublisher(broker, settings.publish_timeout_s, settings.publish_concurrency)
    limiter = RateLimiter(settings.rate_limit_events_per_s, settings.rate_limit_burst)

    ingest = uvicorn.Server(uvicorn.Config(
        create_app(settings, cache, limiter, publisher),
        host=settings.http_host, port=settings.http_port,
        ssl_certfile=str(settings.tls_cert), ssl_keyfile=str(settings.tls_key),
        log_level="info", access_log=False, server_header=False,
    ))
    supervision = uvicorn.Server(uvicorn.Config(
        create_health_app(cache, lambda: broker.connected),
        host=settings.metrics_host, port=settings.metrics_port, log_level="warning", access_log=False,
    ))
    # uvicorn installe ses propres gestionnaires de signaux : on les désactive pour arrêter tout ensemble.
    for server in (ingest, supervision):
        server.install_signal_handlers = lambda: None

    tasks = [asyncio.create_task(cache.run(), name="sources-cache"),
             asyncio.create_task(ingest.serve(), name="https"),
             asyncio.create_task(supervision.serve(), name="supervision")]
    syslog_server = None
    if settings.syslog_enabled:
        syslog = SyslogServer(cache, limiter, publisher, settings.max_event_chars, settings.syslog_idle_timeout_s)
        syslog_server = await syslog.start(
            settings.syslog_host, settings.syslog_port,
            tls_context(settings.tls_cert, settings.tls_key, settings.syslog_client_ca),
        )
        log.info("Syslog TLS à l'écoute sur %s:%d", settings.syslog_host, settings.syslog_port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    stopper = asyncio.create_task(stop.wait(), name="stop")
    done, _ = await asyncio.wait([stopper, *tasks], return_when=asyncio.FIRST_COMPLETED)
    failed = [t for t in done if t is not stopper]
    for t in failed:
        log.error("composant %s arrêté de façon inattendue : %r", t.get_name(), t.exception())

    # Arrêt propre : plus de nouvelles connexions, requêtes en cours terminées (réponse après PubAck), puis fermeture.
    log.info("arrêt demandé")
    if syslog_server:
        syslog_server.close()
    ingest.should_exit = supervision.should_exit = True
    await asyncio.gather(*(t for t in tasks if t.get_name() != "sources-cache"), return_exceptions=True)
    tasks[0].cancel()
    await broker.close()
    if failed:
        raise SystemExit(1)   # Docker redémarre le conteneur


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
