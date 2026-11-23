"""Routes gestion utilisateurs (C20/C21), schéma normalisé C4.

GET    /users          → liste (ADMIN)
POST   /users          → créer (ADMIN)
GET    /users/me       → profil courant (tous)
GET    /users/{id}     → détail (ADMIN)
PUT    /users/{id}     → modifier rôle/statut (ADMIN)
DELETE /users/{id}     → désactiver (ADMIN)

Le rôle est stocké en FK (acces.users.role_id → acces.roles). Les requêtes
joignent acces.roles pour exposer le nom, et _to_user_response() le convertit
en rôle logique de l'API (ADMIN/ANALYST).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..auth import hash_password
from ..dependencies import get_conn, get_current_user, paginate, require_role
from ..models import (
    ROLE_DB_NAMES,
    ROLE_FROM_DB,
    Page,
    TokenPayload,
    UserCreate,
    UserResponse,
    UserRole,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])

_ADMIN = Depends(require_role(UserRole.ADMIN))

# Colonnes renvoyées par toutes les requêtes de lecture ; r.name est aliasé
# en « role » puis converti en énum par _to_user_response().
_SELECT = """SELECT u.id, u.username, u.email, r.name AS role,
                    u.is_active, u.created_at, u.updated_at
               FROM acces.users u
               JOIN acces.roles r ON r.id = u.role_id"""


def _to_user_response(row: dict) -> dict:
    """Convertit le nom de rôle FR (acces.roles) en rôle logique de l'API.

    Tolérant : accepte aussi une valeur déjà sous forme ADMIN/ANALYST, ce qui
    rend la fonction idempotente (utile pour les mocks de test partagés).
    """
    data = dict(row)
    role = data.get("role")
    if not isinstance(role, UserRole):
        data["role"] = ROLE_FROM_DB.get(role, role)
    return data


@router.get("", response_model=Page[UserResponse])
async def list_users(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_ADMIN,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    active_only: bool = False,
):
    where = " WHERE u.is_active = TRUE" if active_only else ""
    select_sql = _SELECT + where + " ORDER BY u.username"
    count_sql = f"SELECT COUNT(*) AS count FROM acces.users u{where}"
    page = await paginate(conn, select_sql, count_sql, [], limit, offset)
    page["items"] = [_to_user_response(r) for r in page["items"]]
    return page


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_ADMIN,
):
    username = body.username or body.email.split("@")[0]
    pw_hash = hash_password(body.password)
    async with conn.cursor(row_factory=dict_row) as cur:
        try:
            await cur.execute(
                """INSERT INTO acces.users (username, email, password_hash, role_id, is_active)
                   VALUES (%s, %s, %s, (SELECT id FROM acces.roles WHERE name = %s), %s)
                   RETURNING id, username, email,
                             (SELECT name FROM acces.roles WHERE id = role_id) AS role,
                             is_active, created_at, updated_at""",
                (username, body.email, pw_hash, ROLE_DB_NAMES[body.role], body.is_active),
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email ou nom d'utilisateur déjà utilisé",
                )
            raise
        return _to_user_response(await cur.fetchone())


@router.get("/me", response_model=UserResponse)
async def get_me(
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_SELECT + " WHERE u.id = %s", (current.sub,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return _to_user_response(row)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_ADMIN,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_SELECT + " WHERE u.id = %s", (user_id,))
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return _to_user_response(row)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _user=_ADMIN,
):
    updates = body.model_dump(exclude_none=True)
    set_parts: list[str] = []
    values: list = []
    if "role" in updates:
        # Résolution du nom de rôle en FK au sein de la requête.
        set_parts.append("role_id = (SELECT id FROM acces.roles WHERE name = %s)")
        values.append(ROLE_DB_NAMES[updates.pop("role")])
    if "password" in updates:
        set_parts.append("password_hash = %s")
        values.append(hash_password(updates.pop("password")))
    if "is_active" in updates:
        set_parts.append("is_active = %s")
        values.append(updates.pop("is_active"))
    if not set_parts:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun champ à modifier")
    set_clause = ", ".join(set_parts)
    values.append(user_id)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""UPDATE acces.users SET {set_clause}, updated_at = NOW()
                 WHERE id = %s
             RETURNING id, username, email,
                       (SELECT name FROM acces.roles WHERE id = role_id) AS role,
                       is_active, created_at, updated_at""",
            values,
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return _to_user_response(row)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_user(
    user_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _admin=_ADMIN,
):
    if str(user_id) == current.sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Impossible de se désactiver soi-même")
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE acces.users SET is_active = FALSE, updated_at = NOW() WHERE id = %s RETURNING id",
            (user_id,),
        )
        if await cur.fetchone() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
