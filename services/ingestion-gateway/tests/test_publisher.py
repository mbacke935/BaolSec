"""Publication par blocs (A-05) : tailles de lot, erreur en milieu de lot, sûreté du renvoi."""
from __future__ import annotations

import pytest

from baolsec_common.messaging import BrokerUnavailable, PublishResult
from gateway.publisher import PUBLISH_CHUNK_SIZE, RawEventPublisher


def make_event(i: int) -> dict:
    return {"event_id": f"evt-{i:06d}", "contract": "raw_event/v1", "payload": str(i)}


class FailAfterNBroker:
    """Broker en mémoire qui échoue après N publications réussies (panne simulée au milieu
    du lot), avec déduplication par Msg-Id comme le FakeBroker de conftest."""

    def __init__(self, fail_after: int):
        self.fail_after = fail_after
        self.calls = 0
        self.messages: list[tuple[str, str]] = []
        self.ids: set[str] = set()

    async def publish(self, subject, data, msg_id, timeout=5.0):
        self.calls += 1
        if self.calls > self.fail_after:
            raise BrokerUnavailable("panne simulée au milieu du lot")
        if msg_id in self.ids:
            return PublishResult("RAW_EVENTS", 0, True)
        self.ids.add(msg_id)
        self.messages.append((subject, msg_id))
        return PublishResult("RAW_EVENTS", len(self.messages), False)


@pytest.mark.parametrize("n", [1, PUBLISH_CHUNK_SIZE - 1, PUBLISH_CHUNK_SIZE, PUBLISH_CHUNK_SIZE + 1, 2 * PUBLISH_CHUNK_SIZE])
async def test_tailles_de_lot_autour_de_la_frontiere_de_bloc(n):
    """Lots < , ==, et > PUBLISH_CHUNK_SIZE (500) : aucun événement perdu ni dupliqué,
    quel que soit le nombre de blocs (1 bloc, pile 1 bloc, ou plusieurs blocs dont un partiel)."""
    broker = FailAfterNBroker(fail_after=10**9)   # jamais de panne ici
    publisher = RawEventPublisher(broker, timeout_s=1.0, concurrency=16)
    events = [make_event(i) for i in range(n)]
    summary = await publisher.publish_all(events, [])
    assert summary.stored == n and summary.duplicates == 0
    assert len(broker.messages) == n
    assert len({m[1] for m in broker.messages}) == n   # Msg-Id tous distincts, aucun doublon


async def test_erreur_en_milieu_de_lot_interrompt_les_blocs_suivants():
    """A-05 + atomicité : un lot de 3 blocs pleins (1500 événements) dont le 2e échoue ne doit
    PAS tenter le 3e bloc, et doit laisser le 1er bloc durablement publié (pas « annulé »,
    cf. docstring publish_all — ce n'est pas une transaction)."""
    n = 3 * PUBLISH_CHUNK_SIZE
    broker = FailAfterNBroker(fail_after=PUBLISH_CHUNK_SIZE + 5)   # casse au milieu du 2e bloc
    publisher = RawEventPublisher(broker, timeout_s=1.0, concurrency=16)
    events = [make_event(i) for i in range(n)]

    with pytest.raises(BrokerUnavailable):
        await publisher.publish_all(events, [])

    # Le 1er bloc est entièrement passé avant l'échec (ordre des blocs respecté).
    assert len(broker.messages) >= PUBLISH_CHUNK_SIZE
    # asyncio.gather(..., return_exceptions=True) attend TOUTES les tâches d'un même bloc avant
    # de rendre la main, même quand certaines échouent : le bloc 2 est donc intégralement tenté
    # (500 appels de plus), mais le bloc 3 ne l'est jamais — 2 blocs au total, pas 3.
    assert broker.calls == 2 * PUBLISH_CHUNK_SIZE, (
        "le 2e bloc doit être intégralement tenté (gather attend toutes ses tâches), "
        "mais le 3e bloc ne doit jamais l'être"
    )
    assert broker.calls < n, "le 3e bloc ne doit jamais être tenté après l'échec du 2e"


async def test_renvoi_complet_apres_echec_partiel_est_sans_perte_ni_doublon():
    """Simule ce que fait l'agent Fluent Bit sur 503 : il renvoie le lot ENTIER. Après un échec
    au milieu du 1er essai, un second essai avec les mêmes événements doit stocker exactement
    n événements au total, sans duplication des événements déjà publiés au 1er essai."""
    n = 2 * PUBLISH_CHUNK_SIZE
    broker = FailAfterNBroker(fail_after=PUBLISH_CHUNK_SIZE + 50)
    publisher = RawEventPublisher(broker, timeout_s=1.0, concurrency=16)
    events = [make_event(i) for i in range(n)]

    with pytest.raises(BrokerUnavailable):
        await publisher.publish_all(events, [])
    first_attempt_count = len(broker.messages)
    assert 0 < first_attempt_count < n

    broker.fail_after = 10**9   # la panne est résolue, l'agent renvoie le lot complet
    summary = await publisher.publish_all(events, [])
    assert summary.stored + summary.duplicates == n
    assert len(broker.messages) == n            # aucune perte : tout finit par être stocké
    assert len({m[1] for m in broker.messages}) == n   # aucun doublon dans le broker
