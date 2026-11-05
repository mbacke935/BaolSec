"""Identifiant stable d'un événement (C3 3.1).

1. Identifiant natif fiable quand la source en fournit un : pour Windows, le triplet
   (ordinateur, canal, EventRecordID) est unique. Ce sont les champs Computer, Channel et
   EventRecordID produits par l'entrée winevtlog de Fluent Bit.
2. Sinon, empreinte SHA-256 de (source_id, format, contenu brut). Le contenu brut contient
   l'horodatage d'origine. Deux événements réellement identiques de la même source
   donnent la même empreinte : ce risque est accepté et documenté dans C3.

Le même événement renvoyé par un agent garde le même identifiant ; le broker écarte le doublon.
"""
from __future__ import annotations

import hashlib
import re

PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")   # raw_event/v1
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def content_hash(source_id: str, payload_format: str, payload: str) -> str:
    data = f"{source_id}\n{payload_format}\n{payload}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def native_id(source_type: str, record: dict) -> str | None:
    if source_type != "windows":
        return None
    computer, channel = record.get("Computer"), record.get("Channel")
    number = record.get("EventRecordID", record.get("RecordNumber"))
    if not (isinstance(computer, str) and isinstance(channel, str) and isinstance(number, int | str)):
        return None
    candidate = "win:" + ":".join(_UNSAFE.sub("_", str(p)) for p in (computer, channel, number))
    return candidate if PATTERN.fullmatch(candidate) else None


def event_id(source_id: str, source_type: str, payload_format: str, payload: str, record: dict | None = None) -> str:
    return (record is not None and native_id(source_type, record)) or content_hash(source_id, payload_format, payload)
