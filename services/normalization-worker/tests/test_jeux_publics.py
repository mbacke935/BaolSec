"""Normalisation de journaux publics réels (critère de C9).

Jeux téléchargés par scripts/testing/fetch_public_datasets.sh dans test-data/public/ (non versionnés) ;
sans eux, ces tests sont ignorés. Chaque ligne est enveloppée comme le fait la passerelle, puis normalisée.
Exigences : aucun événement produit n'est refusé par le schéma normalized_event/v1, et le taux de
lignes reconnues est mesuré par jeu (affiché avec pytest -s).
"""
from __future__ import annotations

import collections
import hashlib
import json

import pytest
import yaml

from baolsec_common.messaging import ProcessingError

from .conftest import NORMALIZED, ROOT, raw

DATA = ROOT / "test-data" / "public"
RECEIVED = "2026-12-31T23:59:00.000Z"   # les lignes Syslog sans année sont datées de l'année de réception
pytestmark = pytest.mark.skipif(not DATA.is_dir(), reason="jeux publics absents : scripts/testing/fetch_public_datasets.sh")

# fichier, type de source, format, part minimale de lignes normalisées, actions attendues
MANIFEST = yaml.safe_load((ROOT / "test-data" / "manifest.yaml").read_text(encoding="utf-8"))
DATASETS = [entry for entry in MANIFEST["datasets"] if entry["validation"]["directly_processable"]]
RESULTS: dict[str, dict] = {}


def test_manifeste_couvre_les_douze_artefacts():
    """Le manifeste est l'unique inventaire : présence, intégrité et chaîne EVTX sont vérifiées."""
    entries = MANIFEST["datasets"]
    assert MANIFEST["version"] == 1 and len(entries) == 12
    assert len({entry["id"] for entry in entries}) == len({entry["path"] for entry in entries}) == 12
    for entry in entries:
        path = DATA / entry["path"]
        assert path.is_file(), f"dataset absent : {entry['path']}"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], entry["path"]
        validation = entry["validation"]
        assert validation["parser"] in {"linux", "firewall", "http", "windows"}
        if entry["origin"]["type"] == "public-download":
            assert entry["format"] in {"text", "evtx"}
            assert all(entry[key] for key in ("source", "revision", "source_path"))
        else:
            assert entry["origin"]["type"] == "derived"
            assert entry["source"] is entry["revision"] is entry["source_path"] is None
            assert entry["origin"]["conversion"]["script"] == "scripts/testing/evtx_to_fluentbit.py"
    evtx = [entry for entry in entries if entry["format"] == "evtx"]
    assert len(evtx) == 4
    assert all(not entry["validation"]["directly_processable"] for entry in evtx)
    assert {entry["validation"]["conversion_output"] for entry in evtx} == {"windows-security.jsonl"}
    derived = next(entry for entry in entries if entry["path"] == "windows-security.jsonl")
    assert derived["format"] == "jsonl" and derived["validation"]["directly_processable"]
    assert set(derived["origin"]["inputs"]) == {entry["path"] for entry in evtx}


@pytest.mark.parametrize("entry", DATASETS, ids=[d["id"] for d in DATASETS])
def test_jeu_public(normalizer, entry):
    name, kind = entry["path"], entry["validation"]["parser"]
    fmt = "json" if entry["format"] == "jsonl" else entry["format"]
    min_rate = entry["validation"].get("minimum_normalized_rate")
    actions = set(entry["validation"]["expected_actions"])
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
