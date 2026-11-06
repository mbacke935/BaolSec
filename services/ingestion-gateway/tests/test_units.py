"""Tests unitaires : identifiant d'événement, validation, limitation de débit, cache des sources."""
from __future__ import annotations

import json

from gateway.auth import bearer_token, generate_token, hash_token
from gateway.event_id import PATTERN, content_hash, event_id
from gateway.rate_limit import RateLimiter
from gateway.sources_cache import Source
from gateway.validation import agent_name_from, http_records

from .conftest import FIREWALL_ID, LINUX_ID, LINUX_TOKEN, OLD_TOKEN, DISABLED_TOKEN, WINDOWS_ID, assert_raw_event

LINUX = Source(LINUX_ID, "srv-linux-01", "linux", "https", "direct")
WINDOWS = Source(WINDOWS_ID, "pc-compta-02", "windows", "https", "direct")
NOW = "2026-11-05T10:00:00.000Z"


# ------------------------------------------------------------------ event_id

def test_empreinte_stable_et_distincte_par_source():
    a = content_hash(LINUX_ID, "text", "ligne")
    assert a == content_hash(LINUX_ID, "text", "ligne")
    assert a != content_hash(WINDOWS_ID, "text", "ligne")
    assert PATTERN.fullmatch(a)


def test_identifiant_natif_windows():
    rec = {"Computer": "PC-COMPTA-02", "Channel": "Security", "EventRecordID": 98765, "EventID": 4625}
    assert event_id(WINDOWS_ID, "windows", "json", "{}", rec) == "win:PC-COMPTA-02:Security:98765"
    # sans les trois champs, retour à l'empreinte
    assert len(event_id(WINDOWS_ID, "windows", "json", "{}", {"EventID": 4625})) == 64
    # jamais pour une autre source
    assert len(event_id(LINUX_ID, "linux", "json", "{}", rec)) == 64


# ------------------------------------------------------------------ validation

def test_ligne_de_fichier_et_enregistrement_structure():
    records = [
        {"date": "2026-11-02T10:40:52.640Z", "log": "<38>Nov  2 10:40:52 srv sshd[1842]: Failed password\n"},
        {"date": 1793616052.64, "MESSAGE": "session opened", "_HOSTNAME": "srv"},
    ]
    events, rejected = http_records(records, LINUX, NOW, 65536, "fluent-bit")
    assert rejected == []
    text, js = events
    assert text["payload_format"] == "text" and not text["payload"].endswith("\n")
    assert text["agent"] == {"name": "fluent-bit", "read_at": "2026-11-02T10:40:52.640Z"}
    assert js["payload_format"] == "json" and json.loads(js["payload"]) == {"MESSAGE": "session opened", "_HOSTNAME": "srv"}
    assert js["agent"]["read_at"] == "2026-11-02T10:40:52.640Z"
    for e in events:
        assert_raw_event(e)


def test_rejets_individuels():
    records = ["texte", {}, {"log": ""}, {"log": 42}, {"log": "x" * 70000}, {"date": "pas une date", "log": "ok"}]
    events, rejected = http_records(records, LINUX, NOW, 65536, None)
    assert [r.index for r in rejected] == [0, 1, 2, 3, 4]
    assert len(events) == 1 and "agent" not in events[0]      # date illisible : omise, pas inventée
    assert_raw_event(events[0])


def test_meme_evenement_meme_identifiant():
    rec = [{"date": 1, "log": "même ligne"}]
    a, _ = http_records(rec, LINUX, NOW, 65536, None)
    b, _ = http_records([{"date": 2, "log": "même ligne"}], LINUX, "2026-11-05T11:00:00.000Z", 65536, None)
    assert a[0]["event_id"] == b[0]["event_id"]


def test_nom_agent():
    assert agent_name_from("Fluent-Bit/4.1.0") == "fluent-bit"
    assert agent_name_from(None) is None


# ------------------------------------------------------------------ jetons

def test_jetons():
    t = generate_token()
    assert t.startswith("bsk_") and len(t) > 40 and hash_token(t) != t
    assert bearer_token(f"Bearer {t}") == t and bearer_token(f"bearer  {t} ") == t
    assert bearer_token("Basic abc") is None and bearer_token("Bearer ") is None and bearer_token(None) is None


# ------------------------------------------------------------------ limitation de débit

def test_seau_a_jetons():
    now = [0.0]
    rl = RateLimiter(rate_per_s=10, burst=20, clock=lambda: now[0])
    assert rl.try_acquire("s", 15) == 0              # 5 jetons restants
    assert rl.try_acquire("s", 15) == 0              # accepté : dette de 10
    assert rl.try_acquire("s", 1) == 1.0             # attendre que la dette soit remboursée (10 à 10/s)
    now[0] = 1.05
    assert rl.try_acquire("s", 1) == 0
    assert rl.try_acquire("autre", 20) == 0          # compteurs séparés par source


def test_lot_plus_grand_que_la_rafale_jamais_bloque():
    now = [0.0]
    rl = RateLimiter(rate_per_s=100, burst=50, clock=lambda: now[0])
    assert rl.try_acquire("s", 5000) == 0            # un gros chunk passe…
    assert rl.try_acquire("s", 10) == 49.5           # …puis la source attend (débit moyen respecté)
    now[0] = 50
    assert rl.try_acquire("s", 10) == 0


# ------------------------------------------------------------------ cache des sources

async def test_cache_ne_garde_que_les_identifiants_valides(cache):
    assert cache.by_token_hash(hash_token(LINUX_TOKEN)).id == LINUX_ID
    assert cache.by_token_hash(hash_token(OLD_TOKEN)) is None        # révoqué
    assert cache.by_token_hash(hash_token(DISABLED_TOKEN)) is None   # source désactivée
    assert cache.by_fingerprint("aabbccdd").id == FIREWALL_ID        # empreinte normalisée
    assert cache.by_fingerprint("AA:BB:CC:DD").id == FIREWALL_ID


async def test_cache_perime_refuse_tout(cache):
    cache._max_stale_s = -1
    assert cache.by_token_hash(hash_token(LINUX_TOKEN)) is None
    assert not cache.usable
