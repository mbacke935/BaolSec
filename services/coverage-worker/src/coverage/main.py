"""Démarrage du service Couverture : PostgreSQL, broker, trackers, évaluateur, supervision (C17)."""
from __future__ import annotations

import asyncio
import json
import logging
import signal

import uvicorn

from baolsec_common.messaging import BrokerUnavailable
from baolsec_common.messaging.nats_adapter import NatsBroker

from .config import Settings
from .evaluator import SourceStateEvaluator
from .health import create_app
from .repositories import Database
from .tracker import ProcessingTracker, ReceptionTracker

log = logging.getLogger("coverage")


async def connect_broker(settings: Settings) -> NatsBroker:
    delay = 1.0
    while True:
        try:
            return await NatsBroker.connect(settings.broker_url, settings.broker_token, name="coverage-worker")
        except BrokerUnavailable as exc:
            log.warning("broker indisponible au démarrage (%s), nouvel essai dans %.0fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def run(settings: Settings) -> None:
    db = Database(settings.postgres_dsn, max_size=settings.db_pool_size, timeout_s=settings.db_timeout_s)
    await db.open()

    broker = await connect_broker(settings)

    reception = ReceptionTracker(db)
    processing = ProcessingTracker(db)
    evaluator = SourceStateEvaluator(db, interval_s=settings.eval_interval_s)

    app = create_app(broker_connected=lambda: broker.connected, db_ready=db.ping)
    supervision = uvicorn.Server(uvicorn.Config(app, host=settings.metrics_host, port=settings.metrics_port,
                                                log_level="warning", access_log=False))
    supervision.install_signal_handlers = lambda: None

    # Consommateurs NATS
    raw_consumer = await broker.subscribe_pull(
        stream=settings.raw_stream,
        durable=settings.raw_durable,
        batch=settings.fetch_batch,
    )
    norm_consumer = await broker.subscribe_pull(
        stream=settings.normalized_stream,
        durable=settings.normalized_durable,
        batch=settings.fetch_batch,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    server = asyncio.create_task(supervision.serve(), name="supervision")
    eval_task = asyncio.create_task(evaluator.run(stop_event), name="evaluator")
    raw_task = asyncio.create_task(reception.run(raw_consumer, stop_event), name="raw-tracker")
    norm_task = asyncio.create_task(processing.run(norm_consumer, stop_event), name="norm-tracker")

    log.info(
        "service Couverture démarré : raw=%s/%s norm=%s/%s éval=%.0fs port=%d",
        settings.raw_stream, settings.raw_durable,
        settings.normalized_stream, settings.normalized_durable,
        settings.eval_interval_s, settings.metrics_port,
    )

    await stop_event.wait()
    log.info("arrêt demandé")

    for t in (eval_task, raw_task, norm_task):
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    supervision.should_exit = True
    await server
    await broker.close()
    await db.close()


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
