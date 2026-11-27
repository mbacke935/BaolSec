"""Démarrage du service Incidents : PostgreSQL, broker, consommation de alerts, commandes de l'API, supervision."""
from __future__ import annotations

import asyncio
import json
import logging
import signal

import uvicorn

from baolsec_common.messaging import BrokerUnavailable
from baolsec_common.messaging.nats_adapter import NatsBroker

from .commands import CommandService
from .config import Settings
from .consumer import AlertConsumer, PostgresAlertSink
from .contracts import Contracts
from .health import create_app
from .outbox import OutboxPublisher
from .repositories import Database

log = logging.getLogger("incidents")


async def connect_broker(settings: Settings) -> NatsBroker:
    delay = 1.0
    while True:
        try:
            return await NatsBroker.connect(settings.broker_url, settings.broker_token, name="incident-builder")
        except BrokerUnavailable as exc:
            log.warning("broker indisponible au démarrage (%s), nouvel essai dans %.0fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def run(settings: Settings) -> None:
    contracts = Contracts(settings.contracts_dir)
    db = Database(settings.postgres_dsn, max_size=settings.db_pool_size, timeout_s=settings.db_timeout_s)
    await db.open()
    broker = await connect_broker(settings)
    consumer = AlertConsumer(broker, PostgresAlertSink(db), contracts, stream=settings.stream,
                             durable=settings.durable, batch=settings.fetch_batch)
    outbox = OutboxPublisher(db, broker)
    app = create_app(broker_connected=lambda: broker.connected, db_ready=db.ping,
                     commands=CommandService(db), contracts=contracts, command_token=settings.command_token)
    supervision = uvicorn.Server(uvicorn.Config(app, host=settings.metrics_host, port=settings.metrics_port,
                                                log_level="warning", access_log=False))
    supervision.install_signal_handlers = lambda: None

    loop = asyncio.get_running_loop()
    def _stop() -> None:
        # Un seul gestionnaire par signal : add_signal_handler remplace le précédent, et un second
        # appel pour outbox.stop empêchait l'arrêt du consommateur (processus bloqué jusqu'au SIGKILL).
        consumer.stop()
        outbox.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _stop)
    outbox_task = asyncio.create_task(outbox.run(), name="outbox-publisher")
    server = asyncio.create_task(supervision.serve(), name="supervision")
    log.info("service Incidents démarré : %s/%s → incidents.alert_state, outbox → INCIDENTS, commandes sur le port %d",
             settings.stream, settings.durable, settings.metrics_port)
    try:
        await consumer.run()
    finally:
        log.info("arrêt demandé")
        outbox.stop()
        try:
            await asyncio.wait_for(outbox_task, timeout=10.0)
        except asyncio.TimeoutError:
            log.warning("OutboxPublisher : délai d'arrêt dépassé, annulation")
            outbox_task.cancel()
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
