"""Auth JWT pour l'API BaolSec (C20/C21).

Conforme à C3/C5 : jetons de courte durée avec renouvellement.
  - un jeton d'accès court (défaut 15 min)
  - un jeton de renouvellement plus long (défaut 480 min), échangé sur /auth/refresh

Mots de passe hachés avec Argon2 (C3, §sécurité).

Fonctions :
  - create_token(user_id, email, role) → str            (jeton d'accès)
  - create_refresh_token(user_id, email, role) → str    (jeton de renouvellement)
  - decode_token(token) → TokenPayload | None           (jeton d'accès)
  - decode_refresh_token(token) → TokenPayload | None   (jeton de renouvellement)
  - hash_password(plain) → str                          (Argon2)
  - verify_password(plain, hashed) → bool
"""
from __future__ import annotations

import time
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from .models import TokenPayload, UserRole

# Argon2 pour le hachage des mots de passe (C3, §sécurité).
_pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")

_secret: str = ""
_algorithm: str = "HS256"
_access_expire_minutes: int = 15
_refresh_expire_minutes: int = 480


def configure(
    secret: str,
    algorithm: str = "HS256",
    expire_minutes: int = 15,
    refresh_expire_minutes: int = 480,
) -> None:
    global _secret, _algorithm, _access_expire_minutes, _refresh_expire_minutes
    _secret = secret
    _algorithm = algorithm
    _access_expire_minutes = expire_minutes
    _refresh_expire_minutes = refresh_expire_minutes


def _encode(user_id: str, email: str, role: UserRole, token_type: str, ttl_minutes: int) -> str:
    exp = int(time.time()) + ttl_minutes * 60
    payload = {
        "sub": user_id,
        "email": email,
        "role": role.value,
        "type": token_type,
        "exp": exp,
    }
    return jwt.encode(payload, _secret, algorithm=_algorithm)


def create_token(user_id: str, email: str, role: UserRole) -> str:
    """Jeton d'accès de courte durée."""
    return _encode(user_id, email, role, "access", _access_expire_minutes)


def create_refresh_token(user_id: str, email: str, role: UserRole) -> str:
    """Jeton de renouvellement de plus longue durée."""
    return _encode(user_id, email, role, "refresh", _refresh_expire_minutes)


def _decode(token: str, expected_type: str) -> Optional[TokenPayload]:
    try:
        raw = jwt.decode(token, _secret, algorithms=[_algorithm])
        # Rejette un jeton du mauvais type (ex. refresh utilisé comme accès).
        if raw.get("type", "access") != expected_type:
            return None
        return TokenPayload(
            sub=raw["sub"],
            email=raw["email"],
            role=UserRole(raw["role"]),
            exp=raw["exp"],
        )
    except (JWTError, KeyError, ValueError):
        return None


def decode_token(token: str) -> Optional[TokenPayload]:
    """Valide un jeton d'accès."""
    return _decode(token, "access")


def decode_refresh_token(token: str) -> Optional[TokenPayload]:
    """Valide un jeton de renouvellement."""
    return _decode(token, "refresh")


def access_ttl_seconds() -> int:
    return _access_expire_minutes * 60


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)
