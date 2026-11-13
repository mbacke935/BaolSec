"""Consultation des alertes en ligne de commande (suivi sans interface, démonstration).

    python -m incidents.cli list [--status nouvelle] [--severity critique] [--rule AUTH-001] [--page 1] [--size 25]
    python -m incidents.cli show <alert_id>
    python -m incidents.cli count

Variable : INCIDENTS_POSTGRES_DSN (compte svc_incidents ; le compte svc_api convient aussi, en lecture).
Même requêtes que l'API (C20), qui lira la table incidents.alert_state avec le compte svc_api.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict

import psycopg

from .repositories import alerts as repo


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


async def run(args: argparse.Namespace) -> int:
    dsn = os.environ.get("INCIDENTS_POSTGRES_DSN")
    if not dsn:
        print("INCIDENTS_POSTGRES_DSN manquant", file=sys.stderr)
        return 1
    async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=5) as conn:
        await conn.set_read_only(True)
        if args.command == "count":
            print(_json(await repo.count_alerts(conn)))
        elif args.command == "show":
            row = await repo.get_alert(conn, args.alert_id)
            if row is None:
                print(f"alerte {args.alert_id} inconnue", file=sys.stderr)
                return 2
            print(_json(asdict(row)))
        else:
            page = await repo.list_alerts(
                conn, repo.AlertFilter(status=args.status, severity=args.severity, rule_code=args.rule),
                page=args.page, size=args.size)
            for a in page.items:
                print(f"{a.triggered_at:%Y-%m-%d %H:%M:%S}  {a.severity:<9} {a.status:<9} {a.alert_id[:16]}  "
                      f"assignée à {a.assigned_to or '—'}")
            print(f"{len(page.items)} alerte(s) affichée(s) sur {page.total} (page {page.page})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="incidents.cli", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list", help="lister les alertes, les plus récentes d'abord")
    ls.add_argument("--status", choices=["nouvelle", "en_cours", "cloturee"])
    ls.add_argument("--severity", choices=["faible", "moyenne", "elevee", "critique"])
    ls.add_argument("--rule", help="code de la règle, ex. AUTH-001")
    ls.add_argument("--page", type=int, default=1)
    ls.add_argument("--size", type=int, default=25)
    show = sub.add_parser("show", help="état d'une alerte")
    show.add_argument("alert_id")
    sub.add_parser("count", help="compteurs par statut et par sévérité")
    sys.exit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
