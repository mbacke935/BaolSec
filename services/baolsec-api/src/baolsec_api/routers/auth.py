"""Routes d'authentification (C20/C21, conforme C5).

POST /auth/login    → échange identifiants contre un jeton d'accès + de renouvellement
POST /auth/refresh  → échange un jeton de renouvellement contre un nouveau jeton d'accès
POST /auth/logout   → révoque les jetons présentés
GET  /auth/me       → utilisateur connecté et son rôle (C5)

Sécurité (ES-01, ES-07) : verrouillage temporaire du compte après des échecs répétés
(acces.users.failed_attempts / locked_until) et traçage de chaque tentative de connexion
dans le journal d'audit, réussie ou non.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from psycopg import AsyncConnection

from .. import audit
from .. import auth as auth_mod
from ..auth import (
    access_ttl_seconds,
    create_refresh_token,
    create_token,
    decode_refresh_token,
    revoke_token_str,
    verify_password,
)
from ..dependencies import get_conn, get_current_user
from ..models import ROLE_FROM_DB, RefreshRequest, TokenPayload, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_BAD_CREDENTIALS = "Identifiants incorrects"


async def _get_user(conn: AsyncConnection, login: str):
    # Schéma normalisé C4 : le rôle est une FK vers acces.roles. L'identifiant saisi peut être
    # l'adresse e-mail ou le nom d'utilisateur (les deux sont uniques).
    async with conn.cursor() as cur:
        await cur.execute(
            """SELECT u.id, u.email, u.password_hash, r.name, u.is_active, u.username,
                      u.failed_attempts, u.locked_until
                 FROM acces.users u
                 JOIN acces.roles r ON r.id = u.role_id
                WHERE lower(u.email) = lower(%s) OR u.username = %s
                ORDER BY (lower(u.email) = lower(%s)) DESC
                LIMIT 1""",
            (login, login, login),
        )
        return await cur.fetchone()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    conn: Annotated[AsyncConnection, Depends(get_conn)],
):
    login_name = form.username.strip()
    ip = _client_ip(request)
    row = await _get_user(conn, login_name)
    now = datetime.now(timezone.utc)

    async def refuse(reason: str, actor_id=None, http_status=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS):
        await audit.record(actor_id=actor_id, actor_username=login_name[:200], action="auth.login",
                           target_type="session", target_id=login_name[:200], outcome="refus",
                           details={"reason": reason}, client_ip=ip)
        raise HTTPException(status_code=http_status, detail=detail)

    if row is None:
        await refuse("compte inconnu")
    user_id, email, pw_hash, role_name, is_active, username, failed, locked_until = row

    if locked_until is not None and locked_until > now:
        minutes = max(1, math.ceil((locked_until - now).total_seconds() / 60))
        await refuse("compte verrouillé", user_id, status.HTTP_423_LOCKED,
                     f"Compte temporairement verrouillé après des échecs répétés. Réessayez dans {minutes} min.")
    if not is_active:
        await refuse("compte désactivé", user_id)

    if not verify_password(form.password, pw_hash):
        failed = (failed or 0) + 1
        if failed >= auth_mod.max_failed_attempts:
            lock_until = now + timedelta(minutes=auth_mod.lockout_minutes)
            await conn.execute(
                "UPDATE acces.users SET failed_attempts = 0, locked_until = %s WHERE id = %s",
                (lock_until, user_id),
            )
            await refuse(f"mot de passe incorrect ({failed} échecs) : compte verrouillé {auth_mod.lockout_minutes} min",
                         user_id, status.HTTP_423_LOCKED,
                         f"Trop d'échecs : compte verrouillé pendant {auth_mod.lockout_minutes} min.")
        await conn.execute("UPDATE acces.users SET failed_attempts = %s WHERE id = %s", (failed, user_id))
        await refuse(f"mot de passe incorrect ({failed}/{auth_mod.max_failed_attempts})", user_id)

    role = ROLE_FROM_DB.get(role_name)
    if role is None:  # rôle inconnu en base → refus par prudence
        await refuse(f"rôle inconnu : {role_name}", user_id)

    await conn.execute(
        "UPDATE acces.users SET failed_attempts = 0, locked_until = NULL, last_login_at = %s WHERE id = %s",
        (now, user_id),
    )
    uid, email = str(user_id), email or ""
    await audit.record(actor_id=uid, actor_username=email or username, action="auth.login",
                       target_type="session", target_id=uid, outcome="succes",
                       details={"role": role.value}, client_ip=ip)
    return TokenResponse(
        access_token=create_token(uid, email or username, role),
        refresh_token=create_refresh_token(uid, email or username, role),
        expires_in=access_ttl_seconds(),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, conn: Annotated[AsyncConnection, Depends(get_conn)]):
    payload = decode_refresh_token(body.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton de renouvellement invalide ou expiré",
        )
    # Un compte désactivé (ou verrouillé) depuis l'émission du jeton ne peut plus le renouveler.
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT is_active, locked_until FROM acces.users WHERE id = %s", (payload.sub,)
        )
        row = await cur.fetchone()
    if row is None or not row[0] or (row[1] is not None and row[1] > datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte inactif ou verrouillé")
    # Rotation : l'ancien jeton de renouvellement ne peut pas être réutilisé.
    revoke_token_str(body.refresh_token, "refresh")
    return TokenResponse(
        access_token=create_token(payload.sub, payload.email, payload.role),
        refresh_token=create_refresh_token(payload.sub, payload.email, payload.role),
        expires_in=access_ttl_seconds(),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    body: RefreshRequest | None = None,
):
    """Révocation serveur des jetons en cours (C5).

    - Extrait le jeton d'accès depuis l'en-tête Authorization: Bearer …
    - Extrait le jeton de renouvellement depuis le corps (optionnel)
    - Inscrit chaque jti valide dans la liste de révocation

    Le client doit en parallèle effacer ses propres jetons (C3).
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        revoke_token_str(auth_header[len("Bearer "):], "access")
    if body and body.refresh_token:
        revoke_token_str(body.refresh_token, "refresh")
    return None


@router.get("/me", response_model=UserResponse)
async def me(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
):
    from .users import get_me  # même réponse que GET /users/me
    return await get_me(conn, current)
