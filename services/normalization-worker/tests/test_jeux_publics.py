"""Normalisation de journaux publics réels (critère de C9).

Jeux téléchargés par scripts/testing/fetch_public_datasets.sh dans test-data/public/ (non versionnés) ;
sans eux, ces tests sont ignorés. Chaque ligne est enveloppée comme le fait la passerelle, puis normalisée.
Exigences : aucun événement produit n'est refusé par le schéma normalized_event/v1, et le taux de
lignes reconnues est mesuré par jeu (affiché avec pytest -s).
"""
from __future__ import annotations

import collections
import json

import pytest

from baolsec_common.messaging import ProcessingError

from .conftest import NORMALIZED, ROOT, raw

DATA = ROOT / "test-data" / "public"
RECEIVED = "2026-12-31T23:59:00.000Z"   # les lignes Syslog sans année sont datées de l'année de réception
pytestmark = pytest.mark.skipif(not DATA.is_dir(), reason="jeux publics absents : scripts/testing/fetch_public_datasets.sh")

# fichier, type de source, format, part minimale de lignes normalisées, actions attendues
DATASETS = [
    ("linux-openssh.log", "linux", "text", 1.0, {"ssh_login", "pam_auth"}),
    ("linux-syslog.log", "linux", "text", 0.999, {"pam_auth"}),   # une ligne « -- root[2421]: » sans programme
    ("iptables.log", "linux", "text", 1.0, {"connection_denied"}),
    ("iptables-ipv6.log", "linux", "text", 1.0, {"connection_logged"}),
    ("pfsense-bsd.log", "firewall", "text", None, {"connection_denied", "connection_allowed"}),
    ("pfsense-rfc5424.log", "firewall", "text", None, {"connection_denied", "connection_allowed"}),
    ("web-access.log", "http", "text", 1.0, {"http_request"}),
    ("windows-security.jsonl", "windows", "json", 1.0, {"logon", "process_start"}),
]
RESULTS: dict[str, dict] = {}


@pytest.mark.parametrize("name,kind,fmt,min_rate,actions", DATASETS, ids=[d[0] for d in DATASETS])
def test_jeu_public(normalizer, name, kind, fmt, min_rate, actions):
    path = DATA / name
    if not path.exists():
        pytest.skip(f"{name} absent")
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    stats = collections.Counter()
    errors = collections.Counter()
    for i, line in enumerate(lines):
        event = raw(kind, line, fmt=fmt, received_at=RECEIVED, event_id=f"{name.split('.')[0]}-{i:06d}")
        try:
            doc = normalizer.run(json.dumps(event).encode())
        except ProcessingError as exc:
            assert exc.reason_code == "parse_error", f"ligne {i + 1} : {exc}"
            errors[str(exc).split(":")[0]] += 1
            continue
        NORMALIZED.validate(doc)
        stats[(doc["event"]["action"], doc["event"]["outcome"])] += 1

    normalized = sum(stats.values())
    RESULTS[name] = {"lignes": len(lines), "normalisées": normalized, "actions": stats, "rejets": errors}
    if kind == "firewall":   # seules les lignes filterlog viennent du pare-feu ; les autres partent en rejet
        expected = sum(1 for line in lines if "filterlog" in line)
        assert normalized == expected
    else:
        assert normalized / len(lines) >= min_rate, errors.most_common(5)
    found = {a for a, _ in stats}
    assert actions <= found, f"actions absentes : {actions - found}"


def test_resume(capsys):
    """Tableau récapitulatif (pytest -s) pour le rapport de C9."""
    if not RESULTS:
        pytest.skip("aucun jeu traité")
    with capsys.disabled():
        print("\n| Jeu | Lignes | Normalisées | Actions principales | Rejets |")
        print("|---|---|---|---|---|")
        for name, r in RESULTS.items():
            top = ", ".join(f"{a}/{o} {n}" for (a, o), n in r["actions"].most_common(4))
            rej = sum(r["rejets"].values())
            print(f"| {name} | {r['lignes']} | {r['normalisées']} | {top} | {rej} |")
