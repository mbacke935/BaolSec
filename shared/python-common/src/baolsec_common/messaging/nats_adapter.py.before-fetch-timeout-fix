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

from .interfaces import BrokerUnavailable, PublishResult, StateConflict, StateEntry

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

    def state_store(self, bucket: str) -> "NatsStateStore":
        return NatsStateStore(self._js, bucket)

    async def close(self) -> None:
        # Le service arrête d'abord de demander des messages et termine ceux en cours ;
        # flush envoie les derniers acquittements avant la fermeture.
        await self._nc.flush(timeout=5)
        await self._nc.close()


WRONG_LAST_SEQUENCE = 10071      # JetStream : Nats-Expected-Last-Subject-Sequence non respecté


class NatsStateStore:
    """Bucket KV JetStream utilisé avec écriture conditionnelle et délai de vie par entrée.

    L'écriture passe par une publication sur $KV.<bucket>.<clé> avec les en-têtes
    Nats-Expected-Last-Subject-Sequence (révision attendue) et Nats-TTL (délai de vie) :
    le client nats-py n'expose pas encore le délai de vie sur une mise à jour.
    Le flux du bucket doit autoriser le délai de vie par message (allow_msg_ttl, posé par init_broker.py).
    """

    def __init__(self, js, bucket: str):
        self._js = js
        self._bucket = bucket
        self._kv = None

    async def _store(self):
        if self._kv is None:
            self._kv = await self._js.key_value(self._bucket)
        return self._kv

    async def get(self, key: str) -> StateEntry | None:
        from nats.js.errors import KeyDeletedError, KeyNotFoundError
        try:
            entry = await (await self._store()).get(key)
        except (KeyNotFoundError, KeyDeletedError):
            return None
        except _UNAVAILABLE as exc:
            raise BrokerUnavailable(f"{type(exc).__name__}: {exc}") from exc
        if entry.value is None:
            return None
        return StateEntry(key, entry.value, entry.revision)

    async def put(self, key: str, value: bytes, expected_revision: int, ttl_s: float) -> int:
        headers = {"Nats-Expected-Last-Subject-Sequence": str(expected_revision), "Nats-TTL": f"{max(1, int(ttl_s))}s"}
        try:
            ack = await self._js.publish(f"$KV.{self._bucket}.{key}", value, headers=headers, timeout=5)
        except APIError as exc:
            if exc.err_code == WRONG_LAST_SEQUENCE:
                raise StateConflict(key) from exc
            raise BrokerUnavailable(f"refus du broker : {exc.description}") from exc
        except _UNAVAILABLE as exc:
            raise BrokerUnavailable(f"{type(exc).__name__}: {exc}") from exc
        return ack.seq

    async def scan(self) -> list[StateEntry]:
        from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy
        stream = f"KV_{self._bucket}"
        info = await self._js.stream_info(stream)
        if info.state.messages == 0:
            return []
        sub = await self._js.pull_subscribe(f"$KV.{self._bucket}.>", durable=None, stream=stream, config=ConsumerConfig(
            deliver_policy=DeliverPolicy.LAST_PER_SUBJECT, ack_policy=AckPolicy.NONE, inactive_threshold=30))
        prefix = f"$KV.{self._bucket}."
        out: list[StateEntry] = []
        try:
            while True:
                try:
                    msgs = await sub.fetch(500, timeout=1)
                except (NatsTimeout, asyncio.TimeoutError):
                    break
                for m in msgs:
                    op = (m.headers or {}).get("KV-Operation")
                    if op not in ("DEL", "PURGE") and m.data:
                        out.append(StateEntry(m.subject[len(prefix):], m.data, m.metadata.sequence.stream))
                if msgs and msgs[-1].metadata.num_pending == 0:
                    break
        finally:
            await sub.unsubscribe()
        return out
