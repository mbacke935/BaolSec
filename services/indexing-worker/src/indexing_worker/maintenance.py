"""Maintenance OpenSearch (ES-09, C4 section 8) : instantané quotidien et rétention des événements.

- Instantané : dépôt de type « fs » (path.repo d'OpenSearch, volume opensearch-snapshots) ; un
  instantané par jour des index baolsec-* ; seuls les SNAPSHOT_KEEP plus récents sont conservés.
- Rétention : les index quotidiens d'événements et d'alertes (baolsec-events-AAAA.MM.JJ,
  baolsec-alerts-AAAA.MM.JJ) plus anciens que RETENTION_DAYS jours sont supprimés. L'index des
  incidents n'est jamais purgé (les incidents restent consultables ; PostgreSQL fait foi).
- Reconstruction : restaurer le dernier instantané (POST _snapshot/baolsec/<nom>/_restore), puis
  laisser indexing-worker relire les flux du broker (C4 section 8) ; voir
  docs/deployment/sauvegarde_restauration.md.

Lancement : python -m indexing_worker.maintenance            (boucle, toutes les 24 h)
            python -m indexing_worker.maintenance --once     (une passe)
Variables : OPENSEARCH_URL, OPENSEARCH_USER, OPENSEARCH_PASSWORD, OPENSEARCH_CA_CERT,
            OPENSEARCH_VERIFY_CERTS, RETENTION_DAYS (90), SNAPSHOT_REPO (baolsec),
            SNAPSHOT_PATH (/usr/share/opensearch/snapshots), SNAPSHOT_KEEP (14), MAINTENANCE_INTERVAL_S (86400).
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

from .opensearch_client import OpenSearchClient

log = logging.getLogger("indexing_worker.maintenance")
DAILY = re.compile(r"^baolsec-(events|alerts)-(\d{4})\.(\d{2})\.(\d{2})$")


def expired_indices(names: list[str], today: date, retention_days: int) -> list[str]:
    """Index quotidiens strictement plus anciens que la rétention (fonction pure, testée)."""
    limit = today - timedelta(days=retention_days)
    out = []
    for name in names:
        m = DAILY.match(name)
        if m and date(int(m.group(2)), int(m.group(3)), int(m.group(4))) < limit:
            out.append(name)
    return sorted(out)


def snapshots_to_delete(names: list[str], keep: int) -> list[str]:
    ours = sorted(n for n in names if n.startswith("baolsec-"))
    return ours[:-keep] if keep > 0 and len(ours) > keep else []


def run_once(client: OpenSearchClient, *, retention_days: int, repo: str, path: str, keep: int) -> dict:
    os_ = client._client
    report: dict = {"deleted_indices": [], "snapshot": None, "deleted_snapshots": []}
    names = list(os_.indices.get(index="baolsec-*", ignore_unavailable=True, allow_no_indices=True).keys())
    for name in expired_indices(names, datetime.now(timezone.utc).date(), retention_days):
        os_.indices.delete(index=name)
        report["deleted_indices"].append(name)
        log.info("index supprimé (rétention %d j) : %s", retention_days, name)
    try:
        os_.snapshot.create_repository(repository=repo, body={"type": "fs", "settings": {"location": path}})
        snap = f"baolsec-{datetime.now(timezone.utc):%Y.%m.%d-%H%M%S}"
        os_.snapshot.create(repository=repo, snapshot=snap, wait_for_completion=True,
                            body={"indices": "baolsec-*", "include_global_state": False})
        report["snapshot"] = snap
        log.info("instantané créé : %s/%s", repo, snap)
        existing = [s["snapshot"] for s in os_.snapshot.get(repository=repo, snapshot="_all")["snapshots"]]
        for old in snapshots_to_delete(existing, keep):
            os_.snapshot.delete(repository=repo, snapshot=old)
            report["deleted_snapshots"].append(old)
    except Exception as exc:  # noqa: BLE001 — path.repo absent : la rétention reste appliquée
        log.error("instantané impossible (%s) : vérifier path.repo d'OpenSearch", exc)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Maintenance OpenSearch de BaolSec (instantanés, rétention)")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = OpenSearchClient(os.environ.get("OPENSEARCH_URL", "http://opensearch:9200"),
                              os.environ.get("OPENSEARCH_USER", ""), os.environ.get("OPENSEARCH_PASSWORD", ""),
                              ca_cert=os.environ.get("OPENSEARCH_CA_CERT", ""),
                              verify_certs=os.environ.get("OPENSEARCH_VERIFY_CERTS", "true").lower() != "false")
    kwargs = {"retention_days": int(os.environ.get("RETENTION_DAYS", "90")),
              "repo": os.environ.get("SNAPSHOT_REPO", "baolsec"),
              "path": os.environ.get("SNAPSHOT_PATH", "/usr/share/opensearch/snapshots"),
              "keep": int(os.environ.get("SNAPSHOT_KEEP", "14"))}
    interval = float(os.environ.get("MAINTENANCE_INTERVAL_S", "86400"))
    while True:
        try:
            log.info("passe de maintenance : %s", run_once(client, **kwargs))
        except Exception as exc:  # noqa: BLE001
            log.error("maintenance impossible (OpenSearch injoignable ?) : %s", exc)
            if a.once:
                return 1
        if a.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
