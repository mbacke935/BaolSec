#!/usr/bin/env python3
"""Journaux des services BaolSec, lisibles sans connaissance technique.

Lit `docker compose logs` et affiche une ligne par message :

    27/11 03:12:05  Incidents        info       incident créé pour l'alerte AUTH-001
    27/11 03:12:09  Indexation       attention  OpenSearch injoignable, nouvel essai dans 5 s

Les journaux des services BaolSec sont en JSON (heure, niveau, message) : ils sont remis en forme,
le niveau traduit et le service nommé en français. Les lignes des autres composants (PostgreSQL,
NATS, OpenSearch…) sont affichées telles quelles. Les vérifications de santé et la collecte des
métriques, répétées toutes les quelques secondes, ainsi que les simples lectures réussies de l'API
(l'interface s'actualise toutes les 30 s), sont masquées (--tout pour les voir).

Usage (depuis la racine du dépôt) :
    make journaux                                   # 200 dernières lignes de chaque service
    make journaux ARGS="--suivre"                   # en continu (Ctrl+C pour arrêter)
    make journaux ARGS="--service incidents --niveau attention --depuis 2h"
    docker compose logs --no-color | python3 scripts/deployment/journaux.py --entree -

Options :
    --service NOM    un ou plusieurs services (nom technique ou français : incidents, passerelle…)
    --niveau N       niveau minimal : detail, info, attention, erreur (défaut : info)
    --depuis D       période : 30m, 2h, 1j… (défaut : les --lignes dernières lignes)
    --lignes N       nombre de lignes par service sans --depuis (défaut 200)
    --suivre         affiche les nouvelles lignes au fil de l'eau
    --tout           ne masque pas les lignes répétitives (santé, métriques)
    --entree -       lit les journaux sur l'entrée standard au lieu de lancer docker compose
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

SERVICES = {
    "ingestion-gateway": "Passerelle",
    "normalization-worker": "Normalisation",
    "detection-worker": "Détection",
    "incident-builder": "Incidents",
    "indexing-worker": "Indexation",
    "coverage-worker": "Couverture",
    "baolsec-api": "API",
    "frontend": "Interface",
    "postgresql": "PostgreSQL",
    "broker": "Broker NATS",
    "broker-init": "Init. broker",
    "db-migrate": "Migrations",
    "opensearch": "OpenSearch",
    "opensearch-maintenance": "Maint. index",
    "dlq-monitor": "File de rejet",
    "backup": "Sauvegarde",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
}
ALIASES = {v.lower(): k for k, v in SERVICES.items()} | {
    "passerelle": "ingestion-gateway", "normalisation": "normalization-worker", "detection": "detection-worker",
    "détection": "detection-worker", "incidents": "incident-builder", "indexation": "indexing-worker",
    "couverture": "coverage-worker", "api": "baolsec-api", "interface": "frontend", "broker": "broker",
    "base": "postgresql", "sauvegarde": "backup",
}
LEVELS = {  # niveau technique → (libellé, rang)
    "DEBUG": ("détail", 0), "INFO": ("info", 1), "WARNING": ("attention", 2), "WARN": ("attention", 2),
    "ERROR": ("erreur", 3), "CRITICAL": ("critique", 4), "FATAL": ("critique", 4),
}
MIN_LEVEL = {"detail": 0, "détail": 0, "info": 1, "attention": 2, "erreur": 3, "critique": 4}
COLORS = {0: "\033[2m", 1: "", 2: "\033[33m", 3: "\033[31m", 4: "\033[1;31m"}
NOISE = re.compile(r'"(GET|HEAD) /(health|metrics|healthz)[^"]*"|GET /_cluster/health|/metrics HTTP')
PREFIX = re.compile(r"^(?P<svc>[a-z0-9_.-]+?)(?:-\d+)?\s+\|\s?(?P<line>.*)$")
ACCESS = re.compile(r'^(?P<client>[\d.:a-f]+):\d+ - "(?P<method>[A-Z]+) (?P<path>\S+) HTTP/[\d.]+" (?P<status>\d{3})')
STATUS = {200: "réussie", 201: "réussie (créé)", 202: "acceptée", 204: "réussie", 400: "requête invalide",
          401: "non authentifiée", 403: "refusée : droits insuffisants", 404: "élément introuvable",
          409: "refusée : conflit", 413: "refusée : trop volumineuse", 422: "refusée : données invalides",
          423: "refusée : compte verrouillé", 429: "refusée : trop de requêtes", 503: "service indisponible"}
VERBS = {"POST": "Action", "PUT": "Modification", "PATCH": "Modification", "DELETE": "Suppression", "GET": "Lecture"}
TEXT_LEVEL = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL|PANIC)\b|\[(INF|WRN|ERR|FTL)\]")


def service_of(raw: str) -> str:
    """Nom de service Compose sans le préfixe de projet (« baolsec-incident-builder » → « incident-builder »)."""
    for name in sorted(SERVICES, key=len, reverse=True):
        if raw == name or raw.endswith("-" + name) or raw.endswith("_" + name):
            return name
    return raw


def when(value: str | None) -> str:
    if not value:
        return " " * 14
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:24] if "+" in value else value[:19], fmt).strftime("%d/%m %H:%M:%S")
        except ValueError:
            continue
    return value[:14]


def humanize_access(text: str) -> tuple[int, str] | None:
    """Journal d'accès de l'API (uvicorn) : « Action /incidents/…/close : réussie (127.0.0.1) »."""
    a = ACCESS.match(text)
    if not a:
        return None
    code = int(a["status"])
    path = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27}", lambda x: x.group(0)[:8] + "…", a["path"].split("?")[0])
    path = path.removeprefix("/api/v1")
    result = STATUS.get(code, "erreur du serveur" if code >= 500 else f"code {code}")
    rank = 3 if code >= 500 else 2 if code >= 400 and code not in (401, 404) else 1
    return rank, f"{VERBS.get(a['method'], a['method'])} {path} : {result} ({a['client']})"


def parse(line: str) -> tuple[str, int, str, str | None]:
    """(heure, rang du niveau, message, détail d'erreur) pour une ligne de journal."""
    text = line.strip()
    if text.startswith("{"):
        try:
            doc = json.loads(text)
        except ValueError:
            doc = None
        if isinstance(doc, dict):
            label = str(doc.get("level") or doc.get("levelname") or "INFO").upper()
            rank = LEVELS.get(label, ("info", 1))[1]
            msg = str(doc.get("msg") or doc.get("message") or doc.get("event") or text)
            err = doc.get("error") or doc.get("exc_info")
            access = humanize_access(msg)
            if access:
                rank, msg = max(rank, access[0]), access[1]
            return when(doc.get("time") or doc.get("ts") or doc.get("timestamp")), rank, msg, err
    access = humanize_access(text)
    if access:
        return " " * 14, access[0], access[1], None
    m = TEXT_LEVEL.search(text)
    rank = 1
    if m:
        tag = (m.group(1) or {"INF": "INFO", "WRN": "WARNING", "ERR": "ERROR", "FTL": "FATAL"}[m.group(2)]).upper()
        rank = LEVELS.get("CRITICAL" if tag == "PANIC" else tag, ("info", 1))[1]
    return " " * 14, rank, text, None


def level_name(rank: int) -> str:
    return {0: "détail", 1: "info", 2: "attention", 3: "erreur", 4: "critique"}[rank]


def main() -> int:
    ap = argparse.ArgumentParser(description="Journaux des services BaolSec, mis en forme.")
    ap.add_argument("--service", nargs="*", default=[])
    ap.add_argument("--niveau", default="info", choices=sorted(MIN_LEVEL))
    ap.add_argument("--depuis")
    ap.add_argument("--lignes", type=int, default=200)
    ap.add_argument("--suivre", action="store_true")
    ap.add_argument("--tout", action="store_true")
    ap.add_argument("--entree")
    args = ap.parse_args()

    wanted = []
    for name in args.service:
        key = ALIASES.get(name.lower(), name)
        if key not in SERVICES:
            print(f"Service inconnu : {name}. Services : {', '.join(SERVICES)}", file=sys.stderr)
            return 2
        wanted.append(key)

    if args.entree == "-":
        stream, proc = sys.stdin, None
    else:
        cmd = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml", "logs", "--no-color", "--timestamps"]
        if args.depuis:
            since = f"{int(args.depuis[:-1]) * 24}h" if args.depuis.endswith("j") else args.depuis   # 2j → 48h
            cmd += ["--since", since]
        else:
            cmd += ["--tail", str(args.lignes)]
        if args.suivre:
            cmd.append("--follow")
        cmd += wanted
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        stream = proc.stdout

    color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    minimum = MIN_LEVEL[args.niveau]
    shown = 0
    try:
        for raw in stream:
            m = PREFIX.match(raw.rstrip("\n"))
            if not m:
                continue
            svc = service_of(m["svc"])
            if wanted and svc not in wanted:
                continue
            line = m["line"]
            stamp = None
            ts = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\S*\s+(.*)$", line)   # préfixe --timestamps
            if ts:
                stamp, line = ts.group(1), ts.group(2)
            if not args.tout and (NOISE.search(line) or re.search(r'"GET [^"]+" [23]\d\d\b', line)):
                continue
            moment, rank, msg, err = parse(line)
            if rank < minimum:
                continue
            if not moment.strip() and stamp:
                moment = when(stamp)
            name = SERVICES.get(svc, svc)
            start, end = (COLORS[rank], "\033[0m") if color and COLORS[rank] else ("", "")
            print(f"{start}{moment}  {name[:15]:<15}  {level_name(rank):<9}  {msg}{end}")
            if err:
                for extra in str(err).strip().splitlines()[-6:]:
                    print(f"{start}{'':<44}{extra}{end}")
            shown += 1
    except KeyboardInterrupt:
        pass
    finally:
        if proc:
            proc.terminate()
    if not shown and not args.suivre:
        print("Aucune ligne à afficher pour ces critères.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
