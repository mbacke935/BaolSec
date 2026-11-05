"""Adaptateur NATS JetStream de l'interface de messagerie (ADR 0002).

Seul fichier du code applicatif qui importe nats-py (I-9).
"""
from __future__ import annotations

import asyncio
import logging

import nats
from nats.aio.msg import Msg
from nats.errors import ConnectionClosedError, NoRespondersError, NoServersError, TimeoutError as NatsTimeout
from nats.js.errors import APIError

from .interfaces import BrokerUnavailable, PublishResult

log = logging.getLogger(__name__)

MSG_ID_HEADER = "Nats-Msg-Id"
_UNAVAILABLE = (NoRespondersError, NoServersError, ConnectionClosedError, NatsTimeout, asyncio.TimeoutError, OSError)


class NatsMessage:
    def __init__(self, raw: Msg):
        self._raw = raw
        meta = raw.metadata
        self.data: bytes = raw.data
        self.subject: str = raw.subject
        self.msg_id: str | None = (raw.headers or {}).get(MSG_ID_HEADER)
        self.delivery_count: int = meta.num_delivered
        self.stream_sequence: int = meta.sequence.stream

    async def ack(self) -> None:
        # ack_sync : attend la confirmation du serveur, l'acquittement n'est pas perdu en route.
        await self._raw.ack_sync()

    async def nak(self, delay: float | None = None) -> None:
        await self._raw.nak(delay=delay)

    async def in_progress(self) -> None:
        await self._raw.in_progress()


class NatsSubscription:
    def __init__(self, sub):
        self._sub = sub

    async def fetch(self, batch: int = 10, timeout: float = 5.0) -> list[NatsMessage]:
        try:
            msgs = await self._sub.fetch(batch=batch, timeout=timeout)
        except NatsTimeout:
            return []
        return [NatsMessage(m) for m in msgs]


class NatsBroker:
    """Connexion au broker. Utiliser `await NatsBroker.connect(url, token)`."""

    def __init__(self, nc):
        self._nc = nc
        self._js = nc.jetstream()

    @classmethod
    async def connect(
        cls, url: str, token: str | None = None, name: str | None = None, timeout: float = 10.0
    ) -> "NatsBroker":
        """Lève BrokerUnavailable si la première connexion échoue avant `timeout` secondes.

        Une fois connecté, le client se reconnecte sans fin après une coupure :
        un worker ne s'arrête pas parce que le broker redémarre.
        """
        async def on_error(exc: Exception) -> None:
            log.warning("broker : %s", exc)

        try:
            nc = await asyncio.wait_for(
                nats.connect(
                    url,
                    token=token or None,
                    name=name,
                    connect_timeout=5,
                    max_reconnect_attempts=-1,
                    reconnect_time_wait=2,
                    error_cb=on_error,
                ),
                timeout=timeout,
            )
        except _UNAVAILABLE as exc:
            raise BrokerUnavailable(f"connexion impossible à {url} : {type(exc).__name__}") from exc
        return cls(nc)

    @property
    def connected(self) -> bool:
        return self._nc.is_connected

    async def publish(self, subject: str, data: bytes, msg_id: str, timeout: float = 5.0) -> PublishResult:
        try:
            ack = await self._js.publish(subject, data, timeout=timeout, headers={MSG_ID_HEADER: msg_id})
        except _UNAVAILABLE as exc:
            raise BrokerUnavailable(f"{type(exc).__name__}: {exc}") from exc
        except APIError as exc:   # flux plein (dlq), message trop gros…
            raise BrokerUnavailable(f"refus du broker : {exc.description}") from exc
        return PublishResult(stream=ack.stream, sequence=ack.seq, duplicate=bool(ack.duplicate))

    async def subscribe(self, stream: str, durable: str) -> NatsSubscription:
        sub = await self._js.pull_subscribe_bind(durable=durable, stream=stream)
        return NatsSubscription(sub)

    async def close(self) -> None:
        # Le service arrête d'abord de demander des messages et termine ceux en cours ;
        # flush envoie les derniers acquittements avant la fermeture.
        await self._nc.flush(timeout=5)
        await self._nc.close()
