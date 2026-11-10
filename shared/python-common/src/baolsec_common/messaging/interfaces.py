"""Interface de messagerie utilisée par les services (I-9).

Le code métier n'importe que ce module. Le broker concret (NATS JetStream, ADR 0002)
est caché derrière `nats_adapter.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class BrokerUnavailable(Exception):
    """Le broker n'a pas confirmé la publication (arrêté, injoignable, délai dépassé).

    La passerelle répond 503 ; un worker n'acquitte pas le message en cours.
    """


@dataclass(frozen=True)
class PublishResult:
    stream: str
    sequence: int
    duplicate: bool  # True : même Msg-Id déjà reçu dans la fenêtre de déduplication


@runtime_checkable
class ReceivedMessage(Protocol):
    data: bytes
    subject: str
    msg_id: str | None          # Msg-Id fixé par le producteur (event_id, alert_id…)
    delivery_count: int         # 1 à la première livraison
    stream_sequence: int

    async def ack(self) -> None:
        """À appeler seulement après la persistance des effets (I-8)."""

    async def nak(self, delay: float | None = None) -> None:
        """Demande une nouvelle livraison, éventuellement après `delay` secondes."""

    async def in_progress(self) -> None:
        """Repousse le délai d'acquittement pendant un traitement long."""


class Publisher(Protocol):
    async def publish(self, subject: str, data: bytes, msg_id: str, timeout: float = 5.0) -> PublishResult:
        """Publie et attend la confirmation durable du broker. Lève BrokerUnavailable."""


class Subscription(Protocol):
    async def fetch(self, batch: int = 10, timeout: float = 5.0) -> list[ReceivedMessage]:
        """Renvoie jusqu'à `batch` messages ; liste vide si rien n'arrive avant `timeout`."""


class Broker(Publisher, Protocol):
    async def subscribe(self, stream: str, durable: str) -> Subscription:
        """Se rattache à un consommateur durable existant (créé par init_broker.py)."""

    async def close(self) -> None: ...


class StateConflict(Exception):
    """Écriture conditionnelle refusée : l'entrée a changé depuis sa lecture (autre instance)."""


@dataclass(frozen=True)
class StateEntry:
    key: str
    value: bytes
    revision: int


class StateStore(Protocol):
    """Stockage clé-valeur à écriture conditionnelle (KV du broker, C14).

    Une entrée expire après son délai de vie, compté depuis sa dernière écriture.
    """

    async def get(self, key: str) -> StateEntry | None:
        """Entrée courante, ou None si elle n'existe pas ou a expiré."""

    async def put(self, key: str, value: bytes, expected_revision: int, ttl_s: float) -> int:
        """Écrit si la révision courante vaut expected_revision (0 : l'entrée ne doit pas exister).

        Renvoie la nouvelle révision. Lève StateConflict, ou BrokerUnavailable.
        """

    async def scan(self) -> list[StateEntry]:
        """Toutes les entrées présentes (contrôles périodiques, tests)."""
