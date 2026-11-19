#!/usr/bin/env python3
"""C27 — Mesure E2E : HTTPS Gateway -> NATS -> Normalisation -> OpenSearch.

Usage :
  BAOLSEC_SOURCE_TOKEN=... OPENSEARCH_PASSWORD=... \
    uv run --with httpx scripts/testing/bench_e2e.py

Le script envoie 100 événements en deux lots de 50, puis attend leur
apparition dans baolsec-events-* via le champ message.

Les événements sont injectés dans l'environnement BaolSec actif et
restent dans les flux et l'index après le test.
"""

from __future__ import annotations

import os
import sys
import time
import math
import uuid
from datetime import datetime, timezone

import httpx


TOTAL_EVENTS = int(os.getenv("BENCH_EVENTS", "100"))
BATCH_SIZE = int(os.getenv("BENCH_BATCH_SIZE", "50"))
RATE_EPS = float(os.getenv("BENCH_RATE_EPS", "0"))
GATEWAY_URL = os.getenv(
    "BAOLSEC_GATEWAY_URL", "https://127.0.0.1:8443"
).rstrip("/")
OPENSEARCH_URL = os.getenv(
    "OPENSEARCH_URL", "http://127.0.0.1:9200"
).rstrip("/")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "")
SOURCE_TOKEN = os.getenv("BAOLSEC_SOURCE_TOKEN", "")
WAIT_TIMEOUT = int(os.getenv("BENCH_WAIT_TIMEOUT", "120"))
POLL_INTERVAL = float(os.getenv("BENCH_POLL_INTERVAL", "1"))


def fail(message: str) -> None:
    print(f"ERREUR : {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if TOTAL_EVENTS < 1:
        fail("BENCH_EVENTS doit être supérieur ou égal à 1.")
    if TOTAL_EVENTS > 5000:
        fail("Limite de sécurité : maximum 5000 événements par exécution.")
    if BATCH_SIZE < 1 or RATE_EPS < 0:
        fail("BENCH_BATCH_SIZE doit être positif et BENCH_RATE_EPS non négatif.")
    if not SOURCE_TOKEN:
        fail("Variable BAOLSEC_SOURCE_TOKEN absente.")
    if not OPENSEARCH_PASSWORD:
        fail("Variable OPENSEARCH_PASSWORD absente.")

    run_id = uuid.uuid4().hex[:12]
    marker = f"baolsec-c27-e2e-{run_id}"

    # Source dev-linux : envoyer des lignes texte au format Syslog RFC3164.
    records = []
    for number in range(TOTAL_EVENTS):
        now = datetime.now(timezone.utc)
        message = f"{marker}-event-{number:04d}"
        syslog_line = (
            f"{now.strftime('%b %d %H:%M:%S')} "
            f"baolsec-c27 baolsec-bench[1000]: {message}"
        )
        records.append({
            "date": now.isoformat(),
            "log": syslog_line,
        })

    gateway_headers = {
        "Authorization": f"Bearer {SOURCE_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "BaolSec-C27-E2E-Benchmark/1.0",
    }

    print("===== BAOLSEC C27 — BENCHMARK E2E =====")
    print(f"Événements demandés : {TOTAL_EVENTS}")
    print(f"Taille des lots     : {BATCH_SIZE}")
    if RATE_EPS > 0:
        print(f"Débit cible         : {RATE_EPS:.2f} événements/s")
    print(f"Identifiant du test : {run_id}")
    print("Parcours mesuré     : HTTPS -> pipeline -> OpenSearch")
    print()

    start = time.perf_counter()
    accepted_total = 0
    stored_total = 0
    send_times = {}
    event_latencies = {}
    duplicates_total = 0
    rejected_total = 0

    try:
        with httpx.Client(
            verify=False,
            timeout=httpx.Timeout(20.0),
        ) as gateway:
            for offset in range(0, TOTAL_EVENTS, BATCH_SIZE):
                if RATE_EPS > 0:
                    target_time = start + offset / RATE_EPS
                    delay = target_time - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                batch = records[offset : offset + BATCH_SIZE]
                batch_sent_at = time.perf_counter()
                for number in range(offset, offset + len(batch)):
                    send_times[f'{marker}-event-{number:04d}'] = batch_sent_at

                response = gateway.post(
                    f"{GATEWAY_URL}/ingest",
                    headers=gateway_headers,
                    json=batch,
                )

                if response.status_code != 202:
                    fail(
                        f"Gateway HTTP {response.status_code} "
                        f"pour le lot commençant à {offset} : "
                        f"{response.text[:500]}"
                    )

                result = response.json()
                accepted_total += int(result.get("accepted", 0))
                stored_total += int(result.get("stored", 0))
                duplicates_total += int(result.get("duplicates", 0))
                rejected_items = result.get("rejected", [])
                rejected_total += len(rejected_items)

                print(
                    f"Lot {offset // BATCH_SIZE + 1} : "
                    f"acceptés={result.get('accepted', 0)}, "
                    f"stockés={result.get('stored', 0)}, "
                    f"doublons={result.get('duplicates', 0)}, "
                    f"rejetés={len(rejected_items)}"
                )
                if rejected_items:
                    print(f"  Détails des rejets : {rejected_items}")

        if accepted_total != TOTAL_EVENTS or rejected_total:
            fail(
                "Le gateway n'a pas accepté tous les événements : "
                f"acceptés={accepted_total}/{TOTAL_EVENTS}, "
                f"rejetés={rejected_total}."
            )

        print()
        print("Attente de l'indexation effective dans OpenSearch...")

        auth = (OPENSEARCH_USER, OPENSEARCH_PASSWORD)
        query = {
            "size": TOTAL_EVENTS,
            "query": {
                "match_phrase": {
                    "message": marker
                }
            },
        }

        indexed_count = 0
        deadline = time.perf_counter() + WAIT_TIMEOUT

        with httpx.Client(
            verify=False,
            timeout=httpx.Timeout(10.0),
            auth=auth,
        ) as search:
            while time.perf_counter() < deadline:
                response = search.post(
                    f"{OPENSEARCH_URL}/baolsec-events-*/_search",
                    json=query,
                )

                if response.status_code != 200:
                    fail(
                        f"OpenSearch HTTP {response.status_code} : "
                        f"{response.text[:500]}"
                    )

                hits = response.json().get("hits", {}).get("hits", [])
                observed_at = time.perf_counter()
                for hit in hits:
                    message = hit.get("_source", {}).get("message", "")
                    if message in send_times and message not in event_latencies:
                        event_latencies[message] = observed_at - send_times[message]
                indexed_count = len(event_latencies)
                elapsed = time.perf_counter() - start

                print(
                    f"\rIndexés : {indexed_count}/{TOTAL_EVENTS} "
                    f"| temps écoulé : {elapsed:.2f} s",
                    end="",
                    flush=True,
                )

                if indexed_count >= TOTAL_EVENTS:
                    break

                time.sleep(POLL_INTERVAL)

        end_to_end = time.perf_counter() - start
        print("\n")

        print("===== RÉSULTATS C27 =====")
        print(f"Événements acceptés       : {accepted_total}")
        print(f"Événements stockés        : {stored_total}")
        print(f"Doublons                  : {duplicates_total}")
        print(f"Événements rejetés        : {rejected_total}")
        print(f"Événements retrouvés      : {indexed_count}/{TOTAL_EVENTS}")
        print(f"Durée E2E                 : {end_to_end:.3f} s")

        if indexed_count >= TOTAL_EVENTS:
            values = sorted(event_latencies.values())
            percentile = lambda p: values[max(0, math.ceil(p * len(values)) - 1)] * 1000
            print(f"Latence médiane           : {percentile(0.50):.1f} ms")
            print(f"Latence P95               : {percentile(0.95):.1f} ms")
            print(f"Latence P99               : {percentile(0.99):.1f} ms")
            print(
                f"Débit E2E observé         : "
                f"{TOTAL_EVENTS / end_to_end:.2f} événements/s"
            )
            print("<escape>Résultat : indexation complète observée.</escape>")
        else:
            print(
                f"Résultat : délai dépassé ; "
                f"{TOTAL_EVENTS - indexed_count} événement(s) "
                "non retrouvés dans OpenSearch."
            )
            raise SystemExit(2)

        print()
        print(
            "Limite : mesure réalisée sur la machine et la configuration "
            "actuelles ; elle ne représente pas une capacité maximale "
            "généralisable à un serveur."
        )

    except httpx.HTTPError as exc:
        fail(f"Erreur de communication : {exc}")


if __name__ == "__main__":
    main()
