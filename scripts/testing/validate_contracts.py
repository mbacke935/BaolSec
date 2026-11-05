#!/usr/bin/env python3
"""Valide les contrats de shared/contracts/.

- Chaque fichier de <contrat>/v1/examples/ doit être ACCEPTÉ par son schéma.
- Chaque fichier de <contrat>/v1/invalid/ doit être REJETÉ.
- Les fichiers nommés result_*.json utilisent result.schema.json (incident_command).

Usage (depuis la racine du dépôt) :
    uv run --with jsonschema --with rfc3339-validator scripts/testing/validate_contracts.py
ou  python3 scripts/testing/validate_contracts.py   (jsonschema et rfc3339-validator installés)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover
    sys.exit("jsonschema manquant : pip install jsonschema rfc3339-validator")

ROOT = Path(__file__).resolve().parents[2] / "shared" / "contracts"
CHECKER = FormatChecker()
if "date-time" not in CHECKER.checkers:
    sys.exit("rfc3339-validator manquant : les dates ne seraient pas vérifiées (pip install rfc3339-validator)")


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validator_for(version_dir: Path, example: Path) -> Draft202012Validator:
    name = "result.schema.json" if example.name.startswith("result_") else "schema.json"
    schema = load(version_dir / name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=CHECKER)


def main() -> int:
    failures = 0
    checked = 0
    for version_dir in sorted(ROOT.glob("*/v*")):
        contract = f"{version_dir.parent.name}/{version_dir.name}"
        for example in sorted((version_dir / "examples").glob("*.json")):
            checked += 1
            errors = sorted(validator_for(version_dir, example).iter_errors(load(example)), key=str)
            if errors:
                failures += 1
                print(f"ÉCHEC  {contract}/examples/{example.name} devrait être valide :")
                for err in errors[:5]:
                    print(f"         - {'/'.join(map(str, err.absolute_path)) or '(racine)'} : {err.message}")
            else:
                print(f"ok     {contract}/examples/{example.name}")
        for example in sorted((version_dir / "invalid").glob("*.json")):
            checked += 1
            if validator_for(version_dir, example).is_valid(load(example)):
                failures += 1
                print(f"ÉCHEC  {contract}/invalid/{example.name} aurait dû être rejeté")
            else:
                print(f"ok     {contract}/invalid/{example.name} (rejeté)")
    print(f"\n{checked} fichier(s) vérifié(s), {failures} échec(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
