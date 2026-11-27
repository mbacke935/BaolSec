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

    def __init__(self, url: str, user: str = "", password: str = "", ca_cert: str = "",
                 verify_certs: bool = True) -> None:
        https = url.startswith("https://")
        kwargs: dict[str, Any] = {
            "hosts": [url],
            "connection_class": RequestsHttpConnection,
            "use_ssl": https,
            # Certificat vérifié dès qu'un CA est fourni ; sans CA, uniquement si la vérification
            # est explicitement désactivée (développement, certificat de démonstration).
            "verify_certs": bool(https and (ca_cert or verify_certs)),
            "ssl_show_warn": False,
            "timeout": 10,
            "max_retries": 3,
            "retry_on_timeout": True,
        }
        if ca_cert:
            kwargs["ca_certs"] = ca_cert
        if user and password:
            kwargs["http_auth"] = (user, password)
        self._client = OpenSearch(**kwargs)

    def ensure_templates(self, templates: dict[str, dict]) -> None:
        """Crée ou met à jour les modèles d'index (idempotent). Lève l'exception d'OpenSearch."""
        for name, body in templates.items():
            self._client.indices.put_index_template(name=name, body=body)

    def bulk_index_ids(self, actions: list[dict[str, Any]]) -> set[str]:
        """Indexe en lot et renvoie les _id en échec (tous si OpenSearch est injoignable).

        Permet d'acquitter un message seulement si son document est réellement indexé : les
        autres sont relivrés par le broker (aucune perte, ENF-05).
        """
        if not actions:
            return set()
        try:
            _ok, errors = bulk(self._client, actions, raise_on_error=False, raise_on_exception=False)
        except Exception as exc:  # noqa: BLE001
            log.error("bulk : OpenSearch injoignable (%s)", type(exc).__name__)
            return {str(a.get("_id")) for a in actions}
        failed = set()
        for item in errors or []:
            info = next(iter(item.values()), {}) if isinstance(item, dict) else {}
            failed.add(str(info.get("_id")))
            log.warning("bulk : document %s refusé (%s)", info.get("_id"), str(info.get("error"))[:200])
        return failed

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
