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
import uuid
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

# Verrouillage temporaire après des échecs répétés (ES-01) ; valeurs posées par configure().
max_failed_attempts: int = 5
lockout_minutes: int = 15

# ── Blocklist de tokens révoqués ──────────────────────────────────────────────
# Structure : { jti: exp_timestamp }
# Nettoyage automatique des entrées expirées à chaque révocation.
# Note : en mémoire — perdu au redémarrage du processus.
# Pour une production robuste, remplacer par une entrée Redis :
#   SETEX jti (exp - now) "1"   +   GET jti dans _decode()
_revoked: dict[str, int] = {}


def _cleanup_revoked() -> None:
    """Supprime les jti dont l'expiration est dépassée (nettoyage passif)."""
    now = int(time.time())
    expired = [jti for jti, exp in _revoked.items() if exp <= now]
    for jti in expired:
        del _revoked[jti]


def revoke_token(jti: str, exp: int) -> None:
    """Révoque un jti jusqu'à son expiration naturelle."""
    _cleanup_revoked()
    _revoked[jti] = exp


def is_revoked(jti: str) -> bool:
    """Retourne True si le jti est dans la blocklist et non encore expiré."""
    exp = _revoked.get(jti)
    if exp is None:
        return False
    if int(time.time()) >= exp:
        del _revoked[jti]
        return False
    return True


def configure(
    secret: str,
    algorithm: str = "HS256",
    expire_minutes: int = 15,
    refresh_expire_minutes: int = 480,
    failed_attempts: int = 5,
    lockout_mins: int = 15,
) -> None:
    global _secret, _algorithm, _access_expire_minutes, _refresh_expire_minutes
    global max_failed_attempts, lockout_minutes
    _secret = secret
    _algorithm = algorithm
    _access_expire_minutes = expire_minutes
    _refresh_expire_minutes = refresh_expire_minutes
    max_failed_attempts = failed_attempts
    lockout_minutes = lockout_mins


def _encode(user_id: str, email: str, role: UserRole, token_type: str, ttl_minutes: int) -> str:
    exp = int(time.time()) + ttl_minutes * 60
    payload = {
        "sub": user_id,
        "email": email,
        "role": role.value,
        "type": token_type,
        "exp": exp,
        # jti (JWT ID) unique par token — utilisé par la blocklist de révocation.
        "jti": str(uuid.uuid4()),
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
        # Rejette un jeton révoqué (logout, rotation forcée).
        jti = raw.get("jti", "")
        if jti and is_revoked(jti):
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


def revoke_token_str(token: str, expected_type: str) -> bool:
    """Tente de révoquer un jeton (accès ou renouvellement) à partir de sa valeur brute.

    Retourne True si le jeton a été révoqué, False s'il était invalide ou déjà expiré.
    Ne lève aucune exception.
    """
    try:
        raw = jwt.decode(token, _secret, algorithms=[_algorithm])
        if raw.get("type", "access") != expected_type:
            return False
        jti = raw.get("jti", "")
        if not jti:
            return False
        revoke_token(jti, raw["exp"])
        return True
    except (JWTError, KeyError, ValueError):
        return False


def access_ttl_seconds() -> int:
    return _access_expire_minutes * 60


def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)
