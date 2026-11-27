"""Découpage des trames Syslog (RFC 5425 / RFC 6587) et comportement de SyslogServer."""
from __future__ import annotations

import asyncio
import hashlib

import pytest

from gateway.publisher import RawEventPublisher
from gateway.rate_limit import RateLimiter
from gateway.sources_cache import SourcesCache
from gateway.sources_cache.file import FileSourceRegistry
from gateway.syslog import FrameTooLong, SyslogServer, read_frame

from .conftest import assert_dlq_message, assert_raw_event, sources_document


def reader(data: bytes, limit: int = 2048) -> asyncio.StreamReader:
    r = asyncio.StreamReader(limit=limit)
    r.feed_data(data)
    r.feed_eof()
    return r


async def frames(data: bytes, max_bytes: int = 1000, limit: int = 2048) -> list:
    r, out = reader(data, limit), []
    while True:
        try:
            f = await read_frame(r, max_bytes)
        except FrameTooLong:
            out.append("TROP_LONG")
            continue
        if f is None:
            return out
        out.append(f)


async def test_comptage_octets():
    m1, m2 = b"<134>1 2026-11-05T10:00:00Z fw filterlog - - - a", "<134>1 é".encode()
    data = f"{len(m1)} ".encode() + m1 + f"{len(m2)} ".encode() + m2
    assert await frames(data) == [m1, m2]


async def test_fin_de_ligne_et_derniere_ligne_sans_retour():
    assert await frames(b"<13>ligne un\r\n<13>ligne deux\n<13>fin") == [b"<13>ligne un", b"<13>ligne deux", b"<13>fin"]


async def test_trame_trop_longue_ignoree_puis_suite_lue():
    long = b"<13>" + b"x" * 1500
    data = f"{len(long)} ".encode() + long + b"5 <13>a"
    assert await frames(data) == ["TROP_LONG", b"<13>a"]


async def test_ligne_trop_longue_ignoree():
    assert await frames(b"<13>" + b"y" * 5000 + b"\n<13>ok\n", max_bytes=1000, limit=1024) == ["TROP_LONG", b"<13>ok"]


async def test_entete_de_longueur_invalide():
    with pytest.raises(ValueError):
        await read_frame(reader(b"12x <13>a"), 1000)


# ------------------------------------------------------------- SyslogServer.handle (A-01)

class _FakeSSLObject:
    def __init__(self, der: bytes):
        self._der = der

    def getpeercert(self, binary_form=False):
        return self._der if binary_form else {}


class _FakeWriter:
    def __init__(self, der: bytes):
        self._extra = {"peername": ("10.0.0.1", 12345), "ssl_object": _FakeSSLObject(der)}
        self.closed = False

    def get_extra_info(self, key):
        return self._extra.get(key)

    def close(self):
        self.closed = True


async def test_trame_trop_longue_consignee_en_dlq(broker, tmp_path):
    """A-01 : une trame Syslog trop longue est conservée dans la DLQ (dlq_message/v1),
    avec un motif explicite et sans tenter de restituer un contenu jamais tamponné ; la
    lecture continue ensuite normalement (comportement C6 déjà attendu)."""
    import json as _json

    der = b"certificat-de-test-fw-edge-01"
    fingerprint = hashlib.sha256(der).hexdigest()
    doc = sources_document(fw_fingerprint=fingerprint)
    path = tmp_path / "sources.json"
    path.write_text(_json.dumps(doc), encoding="utf-8")
    cache = SourcesCache(FileSourceRegistry(path), refresh_s=30, max_stale_s=300)
    await cache.refresh()

    limiter = RateLimiter(rate_per_s=1000, burst=1000)
    publisher = RawEventPublisher(broker, timeout_s=1.0, concurrency=16)
    server = SyslogServer(cache, limiter, publisher, max_event_chars=100, idle_timeout_s=1.0)

    long_line = b"<13>" + b"x" * 1500 + b"\n"             # dépasse max_event_chars*4
    ok_line = b"<13>fw-edge-01 message correct\n"
    data = long_line + ok_line
    r = asyncio.StreamReader(limit=4096)
    r.feed_data(data)
    r.feed_eof()
    writer = _FakeWriter(der)

    await server.handle(r, writer)

    dlq = broker.on("dlq.ingestion-gateway")
    raw = broker.on("raw-events")
    assert len(dlq) == 1, "la trame trop longue doit produire exactement un message DLQ"
    assert_dlq_message(dlq[0])
    # Le motif doit rapporter la taille réellement observée de la trame rejetée (découpage par
    # ligne ici, puisque la trame ne commence pas par un en-tête de longueur), pas la taille du
    # repère de substitution (~100 car.) : valeur confirmée par exécution, pas supposée a priori.
    assert "1505" in dlq[0]["reason"], dlq[0]["reason"]
    assert "ligne" in dlq[0]["reason"]
    assert dlq[0]["attempts"] == 1
    assert dlq[0]["reason_code"] == "validation_error"
    assert dlq[0]["original_stream"] == "ingest"
    assert dlq[0]["source_id"] == next(s["id"] for s in doc["sources"] if s["name"] == "fw-edge-01")
    assert dlq[0]["payload"] != long_line.decode(), "le contenu réel n'a jamais été tamponné, il ne doit pas être inventé"
    assert len(raw) == 1, "la trame valide suivante doit être publiée normalement"
    assert_raw_event(raw[0])
    assert writer.closed


async def test_trame_trop_longue_comptage_octets_consignee_en_dlq(broker, tmp_path):
    """Même vérification que ci-dessus, pour l'autre mode de découpage (comptage d'octets,
    RFC 5425) : le motif doit rapporter 'comptage_octets' et la taille déclarée exacte."""
    import json as _json

    der = b"certificat-de-test-fw-edge-01-bis"
    fingerprint = hashlib.sha256(der).hexdigest()
    doc = sources_document(fw_fingerprint=fingerprint)
    path = tmp_path / "sources.json"
    path.write_text(_json.dumps(doc), encoding="utf-8")
    cache = SourcesCache(FileSourceRegistry(path), refresh_s=30, max_stale_s=300)
    await cache.refresh()

    limiter = RateLimiter(rate_per_s=1000, burst=1000)
    publisher = RawEventPublisher(broker, timeout_s=1.0, concurrency=16)
    server = SyslogServer(cache, limiter, publisher, max_event_chars=100, idle_timeout_s=1.0)

    long_msg = b"<13>" + b"y" * 2000
    ok_msg = b"<13>fw-edge-01 message correct"
    data = f"{len(long_msg)} ".encode() + long_msg + f"{len(ok_msg)} ".encode() + ok_msg
    r = asyncio.StreamReader(limit=8192)
    r.feed_data(data)
    r.feed_eof()
    writer = _FakeWriter(der)

    await server.handle(r, writer)

    dlq = broker.on("dlq.ingestion-gateway")
    raw = broker.on("raw-events")
    assert len(dlq) == 1
    assert_dlq_message(dlq[0])
    assert "comptage_octets" in dlq[0]["reason"]
    assert str(len(long_msg)) in dlq[0]["reason"]
    assert len(raw) == 1
    assert_raw_event(raw[0])


# --------------------------------------------------------- A-06 : révocation mi-connexion

async def test_source_revoquee_en_cours_de_connexion_ferme_sans_publier_la_suite(tmp_path):
    """A-06 : SyslogServer.handle() revérifie la validité de la source à chaque trame (boucle
    `while True`, cf. `if self._cache.by_fingerprint(fingerprint) is None: ... break`). Ce test
    démontre qu'une révocation survenant APRÈS l'établissement de la connexion TLS — donc sans
    qu'aucune nouvelle authentification TLS n'ait lieu — est bien prise en compte avant la trame
    suivante : la connexion est fermée et aucun événement postérieur à la révocation n'est publié.
    Jusqu'ici, ce comportement existait dans le code mais n'était couvert par aucun test."""
    import json as _json

    der = b"certificat-de-test-revocation-mi-connexion"
    fingerprint = hashlib.sha256(der).hexdigest()
    doc = sources_document(fw_fingerprint=fingerprint)
    path = tmp_path / "sources.json"
    path.write_text(_json.dumps(doc), encoding="utf-8")
    cache = SourcesCache(FileSourceRegistry(path), refresh_s=30, max_stale_s=300)
    await cache.refresh()

    class RevokingBroker:
        """Broker en mémoire qui révoque la source (côté référentiel) et rafraîchit le cache
        de la Gateway juste après avoir accepté la 1re publication — pour simuler une révocation
        décidée pendant que la connexion Syslog TLS est déjà en cours, sans jamais fermer cette
        connexion ni réauthentifier le certificat client."""

        def __init__(self):
            self.messages: list[tuple[str, dict]] = []
            self.ids: set[str] = set()
            self._revoked_once = False

        async def publish(self, subject, data, msg_id, timeout=5.0):
            if msg_id in self.ids:
                from baolsec_common.messaging import PublishResult
                return PublishResult("RAW_EVENTS", 0, True)
            self.ids.add(msg_id)
            self.messages.append((subject, _json.loads(data)))
            if subject == "raw-events" and not self._revoked_once:
                self._revoked_once = True
                doc_now = _json.loads(path.read_text(encoding="utf-8"))
                for s in doc_now["sources"]:
                    for c in s.get("credentials", []):
                        if c.get("cert_fingerprint") == fingerprint:
                            c["revoked_at"] = "2026-11-24T00:00:00Z"
                path.write_text(_json.dumps(doc_now), encoding="utf-8")
                await cache.refresh()
            from baolsec_common.messaging import PublishResult
            return PublishResult("RAW_EVENTS", len(self.messages), False)

        def on(self, subject: str) -> list[dict]:
            return [m for s, m in self.messages if s == subject]

    broker = RevokingBroker()
    limiter = RateLimiter(rate_per_s=1000, burst=1000)
    publisher = RawEventPublisher(broker, timeout_s=1.0, concurrency=16)
    server = SyslogServer(cache, limiter, publisher, max_event_chars=1000, idle_timeout_s=1.0)

    data = b"<13>fw-edge-01 message avant revocation\n<13>fw-edge-01 message apres revocation\n"
    r = asyncio.StreamReader(limit=4096)
    r.feed_data(data)
    r.feed_eof()
    writer = _FakeWriter(der)

    await server.handle(r, writer)

    raw = broker.on("raw-events")
    assert len(raw) == 1, "seule la 1re trame (avant révocation) doit être publiée"
    assert_raw_event(raw[0])
    assert "avant revocation" in raw[0]["payload"]
    assert "apres revocation" not in raw[0]["payload"]
    assert writer.closed, "la connexion doit être fermée une fois la source révoquée détectée"
    assert cache.by_fingerprint(fingerprint) is None, "le cache doit refléter la révocation"
