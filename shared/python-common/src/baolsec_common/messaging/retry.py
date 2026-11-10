"""Règle commune de traitement d'un message : 5 tentatives, puis dlq (C3 3.1).

    async def handler(msg): ...     # enregistre durablement les effets, lève une exception en cas d'échec
    await process(msg, handler, policy)

- Succès : le message est acquitté après le retour du handler (I-8).
- Échec définitif (ProcessingError(..., permanent=True) : message illisible, non conforme…) :
  le message part tout de suite dans la dlq, car une nouvelle tentative donnerait le même résultat.
- Échec passager avant la dernière tentative : nouvelle livraison après le délai du palier.
- Échec à la dernière tentative : publication d'un dlq_message/v1, attente de la
  confirmation, puis acquittement de l'original. Si la dlq est injoignable, le message
  n'est pas acquitté et sera relivré.

Le broker ne limite pas le nombre de livraisons (max_deliver = -1, C11) : c'est cette règle qui
compte les 5 tentatives. Un message dont la 5e tentative n'a pas abouti (service arrêté, dlq
injoignable) revient donc et part en dlq à la livraison suivante, au lieu de rester bloqué.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

from .interfaces import BrokerUnavailable, Publisher, ReceivedMessage

log = logging.getLogger(__name__)

MAX_PAYLOAD = 131072   # limite du champ payload de dlq_message/v1
MAX_REASON = 2000
MAX_ATTEMPTS = 5       # dlq_message/v1 : attempts.maximum

STREAM_CONTRACT = {
    "raw-events": "raw_event/v1",
    "normalized-events": "normalized_event/v1",
    "alerts": "alert/v1",
}
# Préfixe ajouté par l'outil de reprise de la file de rejet (infrastructure/broker/dlq_admin.py)
REPLAY_PREFIX = re.compile(r"^(?:replay:\d+:)+")
REASON_CODES = {"parse_error", "validation_error", "mapping_error", "index_rejected", "processing_error"}


class ProcessingError(Exception):
    """Échec de traitement avec un motif du contrat dlq_message/v1.

    permanent=True : l'échec ne dépend que du contenu du message (même résultat à chaque essai).
    """

    def __init__(self, reason_code: str, reason: str, permanent: bool = False):
        if reason_code not in REASON_CODES:
            raise ValueError(f"reason_code inconnu : {reason_code}")
        super().__init__(reason)
        self.reason_code = reason_code
        self.permanent = permanent


@dataclass(frozen=True)
class RetryPolicy:
    service: str                       # nom du service, ex. "normalization-worker"
    stream: str                        # flux consommé : raw-events, normalized-events ou alerts
    publisher: Publisher               # sert à publier dans la dlq
    max_deliver: int = 5
    backoff: tuple[float, ...] = field(default=(5, 15, 30, 60))

    def delay(self, delivery_count: int) -> float:
        return self.backoff[min(delivery_count, len(self.backoff)) - 1]


def original_message_id(msg: ReceivedMessage) -> str:
    """Msg-Id d'origine (event_id, alert_id), sans le préfixe d'une reprise depuis la file de rejet."""
    if not msg.msg_id:
        return f"seq:{msg.stream_sequence}"
    return REPLAY_PREFIX.sub("", msg.msg_id) or msg.msg_id


def dlq_msg_id(service: str, msg: ReceivedMessage) -> str:
    """Msg-Id de la publication en dlq.

    Stable pour un même message relivré (même séquence) : un rejet publié deux fois est écarté
    par le broker. Différent après une reprise (nouvelle séquence) : un message repris qui échoue
    de nouveau retourne bien en file de rejet.
    """
    return f"dlq:{service}:{original_message_id(msg)}:{msg.stream_sequence}"


def build_dlq_message(msg: ReceivedMessage, service: str, stream: str, exc: Exception) -> dict:
    if stream not in STREAM_CONTRACT:
        raise ValueError(f"flux sans dlq : {stream}")
    reason_code = getattr(exc, "reason_code", "processing_error")
    reason = (str(exc) or type(exc).__name__)[:MAX_REASON]

    try:
        text = msg.data.decode("utf-8")
        try:
            json.loads(text)
            encoding = "json"
        except ValueError:
            encoding = "text"
        payload = text
    except UnicodeDecodeError:
        encoding, payload = "base64", base64.b64encode(msg.data).decode("ascii")
    if len(payload) > MAX_PAYLOAD:
        encoding = "text" if encoding == "json" else encoding
        payload = payload[:MAX_PAYLOAD]
        reason = (reason + " (contenu tronqué)")[:MAX_REASON]

    return {
        "contract": "dlq_message/v1",
        "message_id": original_message_id(msg),
        "original_stream": stream,
        "original_contract": STREAM_CONTRACT[stream],
        "service": service,
        "attempts": min(msg.delivery_count, MAX_ATTEMPTS),
        "reason_code": reason_code,
        "reason": reason,
        "failed_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "payload_encoding": encoding,
        "payload": payload,
    }


async def process(
    msg: ReceivedMessage,
    handler: Callable[[ReceivedMessage], Awaitable[None]],
    policy: RetryPolicy,
) -> str:
    """Traite un message et renvoie l'issue : "ack", "retry" ou "dlq"."""
    try:
        await handler(msg)
    except Exception as exc:
        if msg.delivery_count < policy.max_deliver and not getattr(exc, "permanent", False):
            delay = policy.delay(msg.delivery_count)
            log.warning("échec %s (tentative %d), nouvelle livraison dans %ss : %s",
                        msg.msg_id, msg.delivery_count, delay, exc)
            await msg.nak(delay=delay)
            return "retry"
        dlq = build_dlq_message(msg, policy.service, policy.stream, exc)
        try:
            await policy.publisher.publish(
                f"dlq.{policy.service}",
                json.dumps(dlq, ensure_ascii=False).encode("utf-8"),
                msg_id=dlq_msg_id(policy.service, msg),
            )
        except BrokerUnavailable:
            log.error("dlq injoignable, %s non acquitté", msg.msg_id)
            return "retry"
        log.error("abandon de %s après %d tentative(s) : %s", msg.msg_id, msg.delivery_count, exc)
        await msg.ack()
        return "dlq"
    await msg.ack()
    return "ack"
