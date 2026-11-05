"""Jetons des sources HTTPS.

Un jeton est une valeur aléatoire de 256 bits ; seule son empreinte SHA-256 est stockée
(config.source_credentials.secret_hash). Un hachage lent (Argon2) n'apporte rien pour une
valeur aléatoire de cette taille et empêcherait la recherche directe par empreinte.

Générer un jeton (en attendant l'écran d'administration de l'API) :
    python -m gateway.auth
"""
from __future__ import annotations

import hashlib
import secrets

PREFIX = "bsk_"


def generate_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bearer_token(authorization: str | None) -> str | None:
    """Extrait le jeton de l'en-tête « Authorization: Bearer <jeton> »."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    value = value.strip()
    if scheme.lower() != "bearer" or not value or len(value) > 256:
        return None
    return value
