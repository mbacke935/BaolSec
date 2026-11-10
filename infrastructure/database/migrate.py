#!/usr/bin/env python3
"""Applique les migrations (alembic upgrade head), puis pose les mots de passe des comptes de service.

Variables :
  DATABASE_ADMIN_URL      postgresql+psycopg://postgres:<mot de passe>@<hôte>:5432/baolsec
  SVC_<COMPTE>_PASSWORD   mot de passe d'un compte (SVC_API_PASSWORD, SVC_DETECTION_PASSWORD…) ;
                          un compte sans variable garde son état (sans mot de passe, il ne peut pas se connecter).
Peut être relancé sans risque : une migration déjà appliquée n'est pas rejouée.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql

HERE = Path(__file__).resolve().parent
ACCOUNTS = ["svc_api", "svc_passerelle", "svc_normalisation", "svc_detection", "svc_incidents", "svc_couverture"]


def libpq_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def set_passwords(url: str) -> list[str]:
    done = []
    with psycopg.connect(libpq_url(url), autocommit=True) as conn:
        for account in ACCOUNTS:
            password = os.environ.get(f"{account.upper()}_PASSWORD")
            if password:
                conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(account), sql.Literal(password)))
                done.append(account)
    return done


def main() -> int:
    url = os.environ.get("DATABASE_ADMIN_URL")
    if not url:
        print("DATABASE_ADMIN_URL manquant", file=sys.stderr)
        return 1
    try:
        command.upgrade(Config(str(HERE / "alembic.ini")), "head")
        done = set_passwords(url)
    except Exception as exc:  # message lisible pour l'exploitant
        print(f"ÉCHEC : {type(exc).__name__} : {exc}", file=sys.stderr)
        return 1
    print(f"migrations appliquées ; mots de passe posés : {', '.join(done) or 'aucun'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
