"""Chaîne reproductible EVTX public -> JSONL Fluent Bit, sans modifier les jeux publics."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from .conftest import ROOT


EVTX = ROOT / "test-data" / "public" / "windows"
SCRIPT = ROOT / "scripts" / "testing" / "evtx_to_fluentbit.py"


def test_quatre_evtx_convertissent_vers_des_evenements_windows(tmp_path):
    paths = sorted(EVTX.glob("*.evtx"))
    assert len(paths) == 4
    result = subprocess.run([sys.executable, str(SCRIPT), *(str(path) for path in paths)], check=True,
                            text=True, capture_output=True)
    records = [json.loads(line) for line in result.stdout.splitlines() if line]
    assert len(records) == 29
    assert {record["EventID"] for record in records} >= {4624, 4625, 4634, 4688}
    assert all(record.get("TimeCreated") for record in records)
    supported = [record for record in records if record["EventID"] in {4624, 4625, 4634, 4688}]
    assert all(isinstance(record.get("EventData"), dict) for record in supported)
    current = [json.loads(line) for line in (ROOT / "test-data" / "public" / "windows-security.jsonl").read_text().splitlines()]
    assert records == current
