"""Démarrage du moteur de détection : broker, KV detection-state, règles, consommation, supervision."""
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
from .rules import FileRules, PostgresRules, RulesCache, RuleValidator
from .worker import Worker

log = logging.getLogger("detector")


async def connect_broker(settings: Settings) -> NatsBroker:
    delay = 1.0
    while True:
        try:
            return await NatsBroker.connect(settings.broker_url, settings.broker_token, name="detection-worker")
        except BrokerUnavailable as exc:
            log.warning("broker indisponible au démarrage (%s), nouvel essai dans %.0fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def run(settings: Settings) -> None:
    source = PostgresRules(settings.postgres_dsn) if settings.rules_source == "postgres" else FileRules(settings.rules_dir)
    rules = RulesCache(source, RuleValidator(settings.contracts_dir), settings.rules_refresh_s)
    broker = await connect_broker(settings)
    worker = Worker(broker, broker.state_store(settings.kv_bucket), rules, stream=settings.stream,
                    durable=settings.durable, output_subject=settings.output_subject, batch=settings.fetch_batch,
                    publish_timeout_s=settings.publish_timeout_s, late_tolerance_s=settings.late_tolerance_s,
                    pending_interval_s=settings.pending_interval_s, cas_retries=settings.cas_retries)
    supervision = uvicorn.Server(uvicorn.Config(
        create_health_app(rules, lambda: broker.connected),
        host=settings.metrics_host, port=settings.metrics_port, log_level="warning", access_log=False))
    supervision.install_signal_handlers = lambda: None

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)
    tasks = [asyncio.create_task(rules.run(), name="rules"),
             asyncio.create_task(supervision.serve(), name="supervision"),
             asyncio.create_task(worker.pending_loop(), name="pending")]
    log.info("détection démarrée : %s/%s → %s (règles : %s)", settings.stream, settings.durable,
             settings.output_subject, settings.rules_source)
    try:
        await worker.run()
    finally:
        log.info("arrêt demandé")
        supervision.should_exit = True
        await tasks[1]
        tasks[0].cancel()
        await tasks[2]
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
