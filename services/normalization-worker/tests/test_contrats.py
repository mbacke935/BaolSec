"""Chaque exemple brut du contrat raw_event/v1 donne exactement l'exemple normalisé correspondant (C5)."""
from __future__ import annotations

import json

import pytest

from .conftest import CONTRACTS

EXAMPLES = sorted(p.name for p in (CONTRACTS / "raw_event/v1/examples").glob("*.json"))


@pytest.mark.parametrize("name", EXAMPLES)
def test_exemple_du_contrat(normalizer, name):
    data = (CONTRACTS / "raw_event/v1/examples" / name).read_bytes()
    expected = json.loads((CONTRACTS / "normalized_event/v1/examples" / name).read_text(encoding="utf-8"))
    assert normalizer.run(data) == expected


def test_chaque_exemple_brut_a_son_exemple_normalise():
    normalized = {p.name for p in (CONTRACTS / "normalized_event/v1/examples").glob("*.json")}
    assert set(EXAMPLES) <= normalized
