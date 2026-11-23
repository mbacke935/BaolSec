"""Routes d'authentification (C20/C21, conforme C5).

POST /auth/login    → échange identifiants contre un jeton d'accès + de renouvellement
POST /auth/refresh  → échange un jeton de renouvellement contre un nouveau jeton d'accès
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from psycopg import AsyncConnection

from ..auth import (
    access_ttl_seconds,
    create_refresh_token,
    create_token,
    decode_refresh_token,
    revoke_token_str,
    verify_password,
)
from ..dependencies import get_conn
from ..models import ROLE_FROM_DB, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_user_by_email(conn: AsyncConnection, email: str):
    # Schéma normalisé C4 : le rôle est une FK vers acces.roles, on joint
    # pour récupérer son nom (« Administrateur » / « Analyste »).
    async with conn.cursor() as cur:
        await cur.execute(
            """SELECT u.id, u.email, u.password_hash, r.name, u.is_active
                 FROM acces.users u
                 JOIN acces.roles r ON r.id = u.role_id
                WHERE u.email = %s""",
            (email,),
        )
        return await cur.fetchone()


@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    conn: Annotated[AsyncConnection, Depends(get_conn)],
):
    row = await _get_user_by_email(conn, form.username)
    if row is None or not row[4]:  # is_active
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects")
    user_id, email, pw_hash, role_name, _ = row
    if not verify_password(form.password, pw_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects")
    role = ROLE_FROM_DB.get(role_name)
    if role is None:  # rôle inconnu en base → refus par prudence
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects")
    uid, email = str(user_id), email or ""
    return TokenResponse(
        access_token=create_token(uid, email, role),
        refresh_token=create_refresh_token(uid, email, role),
        expires_in=access_ttl_seconds(),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    payload = decode_refresh_token(body.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton de renouvellement invalide ou expiré",
        )
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
    - Inscrit chaque jti valide dans la blocklist en mémoire

    Le client doit en parallèle effacer ses propres jetons (C3).
    """
    # Révocation du jeton d'accès (Bearer depuis l'en-tête Authorization)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        revoke_token_str(auth_header[len("Bearer "):], "access")

    # Révocation du jeton de renouvellement (corps optionnel)
    if body and body.refresh_token:
        revoke_token_str(body.refresh_token, "refresh")

    return None
