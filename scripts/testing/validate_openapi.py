#!/usr/bin/env python3
"""Valide docs/api/openapi.yaml.

1. Conformité à OpenAPI 3.1, y compris les références vers shared/contracts/.
2. Cohérence avec la matrice des droits de C2 (section 3) :
   - chaque opération déclare x-baolsec-roles et x-baolsec-access ;
   - utilisateurs, rôles, paramètres et audit : Administrateur uniquement ;
   - commandes (alertes, incidents) : Analyste uniquement, avec l'en-tête Idempotency-Key ;
   - toute opération authentifiée répond 401 et 403.

Usage (depuis la racine du dépôt) :
    uv run --with openapi-spec-validator --with pyyaml scripts/testing/validate_openapi.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from openapi_spec_validator import validate
from openapi_spec_validator.readers import read_from_filename

SPEC = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.yaml"
ADMIN_ONLY = ("/users", "/roles", "/settings", "/audit")
METHODS = {"get", "post", "put", "patch", "delete"}


def main() -> int:
    spec_dict, base_uri = read_from_filename(str(SPEC))
    validate(spec_dict, base_uri=base_uri)
    print("ok     conformité OpenAPI 3.1 (références externes résolues)")

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    problems: list[str] = []
    count = 0
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method not in METHODS:
                continue
            count += 1
            name = f"{method.upper()} {path}"
            roles = op.get("x-baolsec-roles")
            access = op.get("x-baolsec-access")
            if not roles or not access:
                problems.append(f"{name} : x-baolsec-roles ou x-baolsec-access manquant")
                continue
            if path.startswith(ADMIN_ONLY) and roles != ["administrateur"]:
                problems.append(f"{name} : réservé à l'Administrateur (C2, section 3)")
            if access == "commande":
                if roles != ["analyste"]:
                    problems.append(f"{name} : une commande est réservée à l'Analyste")
                params = [p.get("$ref", "") for p in op.get("parameters", [])]
                if "#/components/parameters/IdempotencyKey" not in params:
                    problems.append(f"{name} : en-tête Idempotency-Key manquant")
            if roles != ["public"]:
                missing = {"401", "403"} - set(op["responses"]) if path.startswith("/auth") is False else {"401"} - set(op["responses"])
                if missing:
                    problems.append(f"{name} : réponses manquantes {sorted(missing)}")
    for p in problems:
        print(f"ÉCHEC  {p}")
    print(f"\n{count} opération(s) vérifiée(s), {len(problems)} problème(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
