#!/usr/bin/env python3
"""Charge les règles YAML du dossier rules/ dans config.rules, config.rule_versions et config.rule_requirements.

Outil d'administration en attendant l'écran des règles de l'API (C20, C22), qui sera l'écrivain normal
du schéma config. Peut être relancé :
- une règle nouvelle est créée en version 1 ;
- une règle dont le YAML a changé reçoit une nouvelle version, qui devient la version courante ;
- une règle inchangée n'est pas touchée.
Chaque fichier est contrôlé par le contrat rule/v1 avant tout enregistrement ; un seul fichier invalide
arrête le chargement sans rien écrire.

Variables : DATABASE_ADMIN_URL ; RULES_DIR (défaut rules/).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

import psycopg
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
# Même espace que detection-worker (detector/rules/model.py) : config.rules.id = UUID v5 (espace, code)
RULE_NAMESPACE = uuid.UUID("6f1c0d5e-2b7a-5c3e-9a41-baa15ec00001")
SCHEMA = json.loads((ROOT / "shared" / "contracts" / "rule" / "v1" / "schema.json").read_text(encoding="utf-8"))

UPSERT_RULE = """
INSERT INTO config.rules (id, name, description, rule_type, severity, is_enabled, current_version)
VALUES (%(id)s, %(name)s, %(description)s, %(type)s, %(severity)s, %(enabled)s, 1)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description,
  rule_type = EXCLUDED.rule_type, severity = EXCLUDED.severity, is_enabled = EXCLUDED.is_enabled, updated_at = now()
"""


def read_rules(directory: Path) -> list[tuple[Path, str, dict]]:
    validator = Draft202012Validator(SCHEMA)
    out, errors, codes = [], [], {}
    for path in sorted(directory.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        problems = [e.message for e in validator.iter_errors(data)] if isinstance(data, dict) else ["pas un objet YAML"]
        if problems:
            errors.append(f"{path.name} : {problems[0]}")
            continue
        if data["id"] in codes:
            errors.append(f"{path.name} : code {data['id']} déjà utilisé par {codes[data['id']]}")
        codes[data["id"]] = path.name
        out.append((path, text, data))
    if errors:
        raise SystemExit("Règles refusées, rien n'a été écrit :\n  " + "\n  ".join(errors))
    return out


def load(conn: psycopg.Connection, rules: list[tuple[Path, str, dict]]) -> dict[str, int]:
    stats = {"créées": 0, "nouvelle version": 0, "inchangées": 0}
    for _path, text, data in rules:
        rid = str(uuid.uuid5(RULE_NAMESPACE, data["id"]))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        last = conn.execute("SELECT version, checksum FROM config.rule_versions WHERE rule_id = %s "
                            "ORDER BY version DESC LIMIT 1", (rid,)).fetchone()
        conn.execute(UPSERT_RULE, {"id": rid, "name": data["name"], "description": data.get("description"),
                                   "type": data["type"], "severity": data["severity"],
                                   "enabled": data.get("enabled", True)})
        if last and last[1] == digest:
            stats["inchangées"] += 1
            continue
        version = (last[0] + 1) if last else 1
        conn.execute("INSERT INTO config.rule_versions (rule_id, version, definition_yaml, checksum) VALUES (%s, %s, %s, %s)",
                     (rid, version, text, digest))
        conn.execute("UPDATE config.rules SET current_version = %s, updated_at = now() WHERE id = %s", (version, rid))
        conn.execute("DELETE FROM config.rule_requirements WHERE rule_id = %s", (rid,))
        for req in data.get("requires", []):
            conn.execute("INSERT INTO config.rule_requirements (rule_id, source_type, required_fields) VALUES (%s, %s, %s)",
                         (rid, req["source_type"], req.get("fields") or None))
        stats["créées" if version == 1 else "nouvelle version"] += 1
    return stats


def main() -> int:
    url = os.environ.get("DATABASE_ADMIN_URL", "").replace("postgresql+psycopg://", "postgresql://", 1)
    directory = Path(os.environ.get("RULES_DIR", ROOT / "rules"))
    if not url:
        print("DATABASE_ADMIN_URL manquant", file=sys.stderr)
        return 1
    rules = read_rules(directory)
    with psycopg.connect(url) as conn:          # une seule transaction : tout ou rien
        stats = load(conn, rules)
    print(", ".join(f"{k} : {v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
