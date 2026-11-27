"""Contrôle des messages reçus et des événements produits (motifs de rejet du contrat dlq_message/v1)."""
from __future__ import annotations

import json

import pytest

from baolsec_common.messaging import ProcessingError

from .conftest import raw


@pytest.mark.parametrize("data", [b"pas du json", b"[1]", json.dumps({"contract": "raw_event/v1"}).encode()])
def test_message_raw_events_invalide(normalizer, data):
    with pytest.raises(ProcessingError) as err:
        normalizer.run(data)
    assert err.value.reason_code == "validation_error" and err.value.permanent


def test_resultat_non_conforme_mapping_error(normalizer, monkeypatch):
    from normalizer import normalize as module

    def broken(*_args, **_kw):
        from normalizer.parsers.base import Parsed
        return Parsed({"event": {"category": ["inventee"], "type": ["info"], "action": "x", "outcome": "unknown",
                                 "dataset": "linux.auth"}}, None, "info", "x")
    monkeypatch.setattr(module, "parse", broken)
    with pytest.raises(ProcessingError) as err:
        normalizer.run(json.dumps(raw("linux", "x")).encode())
    assert err.value.reason_code == "mapping_error" and "event/category/0" in str(err.value)


def test_original_conserve_et_identifiant_repris(norm):
    line = "<38>Nov  2 10:40:52 srv-linux-01 sshd[1842]: Failed password for admin from 10.0.4.23 port 51234 ssh2"
    d = norm("linux", line, event_id="f" * 64, read_at="2026-11-02T10:40:52.640Z")
    assert d["event"]["original"] == line and d["event"]["id"] == "f" * 64
    assert d["event"]["created"] == "2026-11-02T10:40:52.640Z"
    assert d["ecs"] == {"version": "9.5.0"} and d["baolsec"]["contract"] == "normalized_event/v1"

def test_syslog_bsd_month_case_insensitive(norm):
    from datetime import datetime, timezone
    from normalizer.parsers.base import parse_syslog

    received = datetime(2026, 11, 20, 3, 30, tzinfo=timezone.utc)

    for month in ("Nov", "nov", "NOV"):
        line = f"<38>{month} 20 03:27:39 srv-linux-01 sshd[1842]: Failed password"
        parsed = parse_syslog(line, received, timezone.utc)
        assert parsed is not None
        assert parsed.timestamp == datetime(2026, 11, 20, 3, 27, 39, tzinfo=timezone.utc)
        assert parsed.program == "sshd"
        assert parsed.message == "Failed password"

    invalid = "<38>Nvx 20 03:27:39 srv-linux-01 sshd[1842]: Failed password"
    assert parse_syslog(invalid, received, timezone.utc) is None

