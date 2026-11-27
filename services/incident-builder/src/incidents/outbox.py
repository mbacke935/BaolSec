"""Publisher Outbox transactionnel pour les incidents (C19).

Principe :
  1. Lire par lot les lignes incidents.incident_outbox dont published_at IS NULL,
     dans l'ordre d'insertion (id ASC), avec un verrou de ligne (FOR UPDATE SKIP LOCKED)
     pour autoriser plusieurs workers sans doublon.
  2. Pour chaque ligne, publier le payload sur NATS/INCIDENTS avec l'event_id comme
     Nats-Msg-Id (idempotence JetStream côté broker).
  3. Marquer published_at = now() UNIQUEMENT après confirmation de JetStream.

Garantie : at-least-once.  En cas de crash après la publication et avant le marquage,
la ligne sera représentée au prochain passage ; l'IncidentIndexer doit être idempotent
(il l'est : _id OpenSearch = incident_id, operation « index » = écrasement).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from baolsec_common.messaging import BrokerUnavailable
from baolsec_common.messaging.nats_adapter import NatsBroker

from .repositories import Database, DatabaseUnavailable

log = logging.getLogger("incidents.outbox")

_SUBJECT = "incidents"
_BATCH = 50          # lignes lues par tour
_POLL_INTERVAL = 2.0  # secondes entre deux tours quand le lot est vide


class OutboxPublisher:
    """Boucle asyncio qui vide la table incident_outbox vers NATS/INCIDENTS."""

    def __init__(self, db: Database, broker: NatsBroker) -> None:
        self._db = db
        self._broker = broker
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Demander l'arrêt propre (appelé depuis main.py au SIGTERM/SIGINT)."""
        self._stop.set()

    async def run(self) -> None:
        log.info("OutboxPublisher démarré (sujet=%s, batch=%d)", _SUBJECT, _BATCH)
        while not self._stop.is_set():
            try:
                published = await self._flush_batch()
            except DatabaseUnavailable as exc:
                log.warning("OutboxPublisher : base indisponible (%s), pause", exc)
                published = 0
            except BrokerUnavailable as exc:
                log.warning("OutboxPublisher : broker indisponible (%s), pause", exc)
                published = 0
            except Exception as exc:
                log.error("OutboxPublisher : erreur inattendue (%s), pause", exc, exc_info=True)
                published = 0

            if published == 0:
                # Rien à publier ou erreur : on attend avant le prochain tour.
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=_POLL_INTERVAL)
                except asyncio.TimeoutError:
                    pass

        log.info("OutboxPublisher arrêté")

    async def _flush_batch(self) -> int:
        """Publie un lot de lignes Outbox. Retourne le nombre de messages envoyés."""
        async with self._db.connection() as conn:
            # Verrou de ligne : SKIP LOCKED évite les blocages si plusieurs instances tournaient.
            cur = await conn.execute(
                """
                SELECT id, event_id, incident_id, payload
                FROM incidents.incident_outbox
                WHERE published_at IS NULL
                ORDER BY id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (_BATCH,),
            )
            rows = await cur.fetchall()
            if not rows:
                return 0

            published_ids: list[int] = []
            for row_id, event_id, incident_id, payload in rows:
                data = json.dumps(payload, ensure_ascii=False, default=str).encode()
                # msg_id = event_id (UUID stable) → JetStream déduplique les republications.
                await self._broker.publish(_SUBJECT, data, msg_id=str(event_id))
                published_ids.append(row_id)
                log.debug(
                    "OutboxPublisher : publié incident=%s event=%s", incident_id, event_id
                )

            # Marquer comme publiés en une seule UPDATE dans la même transaction.
            now = datetime.now(timezone.utc)
            await conn.execute(
                "UPDATE incidents.incident_outbox SET published_at = %s WHERE id = ANY(%s)",
                (now, published_ids),
            )
            # La transaction est commitée à la sortie du bloc `async with db.connection()`.

        log.info("OutboxPublisher : %d incident(s) publiés", len(published_ids))
        return len(published_ids)
