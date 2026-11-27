"""Application manuelle des modèles d'index OpenSearch de BaolSec (C19).

indexing-worker applique déjà ces modèles à son démarrage ; ce script sert à les (ré)appliquer
sans lui, par exemple avant une restauration d'instantané :
    OPENSEARCH_URL=https://localhost:9200 OPENSEARCH_USER=admin OPENSEARCH_PASSWORD=… \
        python opensearch/index_templates.py

Source unique des définitions : services/indexing-worker/src/indexing_worker/templates.py
(alignées sur les documents normalized_event/v1, alert/v1 et le résumé d'incident).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "indexing-worker" / "src"))

from indexing_worker.opensearch_client import OpenSearchClient  # noqa: E402
from indexing_worker.templates import TEMPLATES  # noqa: E402


def main() -> int:
    url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
    client = OpenSearchClient(url, os.environ.get("OPENSEARCH_USER", ""), os.environ.get("OPENSEARCH_PASSWORD", ""),
                              ca_cert=os.environ.get("OPENSEARCH_CA_CERT", ""),
                              verify_certs=os.environ.get("OPENSEARCH_VERIFY_CERTS", "true").lower() != "false")
    print(f"Connexion à {url} …")
    client.ensure_templates(TEMPLATES)
    print("Modèles d'index appliqués :", ", ".join(TEMPLATES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
