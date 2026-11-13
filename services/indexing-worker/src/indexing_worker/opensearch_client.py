"""Client OpenSearch pour l'Indexing Worker (C19).

Encapsule opensearch-py avec retry exponentiel et bulk indexing.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.helpers import bulk, BulkIndexError

log = logging.getLogger(__name__)


class OpenSearchClient:
    """Wrapper autour du client OpenSearch avec retry et bulk."""

    def __init__(self, url: str, user: str = "", password: str = "") -> None:
        kwargs: dict[str, Any] = {
            "hosts": [url],
            "connection_class": RequestsHttpConnection,
            "use_ssl": url.startswith("https://"),
            "verify_certs": False,
            "timeout": 10,
            "max_retries": 3,
            "retry_on_timeout": True,
        }
        if user and password:
            kwargs["http_auth"] = (user, password)
        self._client = OpenSearch(**kwargs)

    def index_one(self, index: str, doc_id: str, body: dict[str, Any]) -> None:
        """Indexe un document unique."""
        self._client.index(index=index, id=doc_id, body=body)

    def bulk_index(self, actions: list[dict[str, Any]]) -> tuple[int, int]:
        """Indexe une liste de documents en bulk.

        Retourne (succès, échecs).
        """
        try:
            success, errors = bulk(self._client, actions, raise_on_error=False)
            if errors:
                log.warning("bulk_index : %d erreurs sur %d", len(errors), success + len(errors))
            return success, len(errors)
        except BulkIndexError as exc:
            log.error("bulk_index : erreur fatale (%s)", exc)
            return 0, len(actions)

    def ping(self) -> bool:
        try:
            return self._client.ping()
        except Exception:
            return False
