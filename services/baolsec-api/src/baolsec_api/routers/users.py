"""Routes gestion utilisateurs (C20/C21), schéma normalisé C4.

GET    /users                    → liste (ADMIN)
POST   /users                    → créer (ADMIN)
GET    /users/me                 → profil courant (tous)
GET    /users/{id}               → détail (ADMIN)
PATCH  /users/{id} (ou PUT)      → modifier nom, e-mail, rôle, statut, mot de passe (ADMIN)
POST   /users/{id}/deactivate    → désactiver (ADMIN) ; DELETE /users/{id} est un alias
POST   /users/{id}/reactivate    → réactiver et déverrouiller (ADMIN)

Garde-fous : un administrateur ne peut ni se désactiver ni se retirer le rôle ; le dernier
administrateur actif ne peut pas être désactivé ni rétrogradé (la plateforme resterait sans
gestionnaire).

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
                    u.is_active, u.last_login_at, u.locked_until, u.created_at, u.updated_at
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
                             is_active, last_login_at, locked_until, created_at, updated_at""",
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


async def _active_admins_other_than(conn, user_id: uuid.UUID) -> int:
    async with conn.cursor() as cur:
        await cur.execute(
            """SELECT COUNT(*) FROM acces.users u JOIN acces.roles r ON r.id = u.role_id
                WHERE r.name = %s AND u.is_active AND u.id <> %s""",
            (ROLE_DB_NAMES[UserRole.ADMIN], user_id),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _guard_admin_loss(conn, user_id: uuid.UUID, current: TokenPayload, *, deactivate: bool, demote: bool) -> None:
    if str(user_id) == current.sub and (deactivate or demote):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Impossible de se désactiver ou de se retirer le rôle Administrateur soi-même")
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT r.name FROM acces.users u JOIN acces.roles r ON r.id = u.role_id WHERE u.id = %s AND u.is_active",
            (user_id,))
        row = await cur.fetchone()
    is_active_admin = bool(row) and row[0] == ROLE_DB_NAMES[UserRole.ADMIN]
    if is_active_admin and (deactivate or demote) and await _active_admins_other_than(conn, user_id) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Dernier administrateur actif : il ne peut être ni désactivé ni rétrogradé")


_RETURNING = """RETURNING id, username, email,
                       (SELECT name FROM acces.roles WHERE id = role_id) AS role,
                       is_active, last_login_at, locked_until, created_at, updated_at"""


@router.patch("/{user_id}", response_model=UserResponse)
@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _user=_ADMIN,
):
    updates = body.model_dump(exclude_none=True)
    await _guard_admin_loss(conn, user_id, current,
                            deactivate=updates.get("is_active") is False,
                            demote=updates.get("role") not in (None, UserRole.ADMIN))
    set_parts: list[str] = []
    values: list = []
    if "username" in updates:
        set_parts.append("username = %s"); values.append(updates["username"].strip())
    if "email" in updates:
        set_parts.append("email = %s"); values.append(updates["email"].strip() or None)
    if "role" in updates:
        # Résolution du nom de rôle en FK au sein de la requête.
        set_parts.append("role_id = (SELECT id FROM acces.roles WHERE name = %s)")
        values.append(ROLE_DB_NAMES[updates["role"]])
    if "password" in updates:
        set_parts.append("password_hash = %s")
        values.append(hash_password(updates["password"]))
    if "is_active" in updates:
        set_parts.append("is_active = %s")
        values.append(updates["is_active"])
        if updates["is_active"]:
            set_parts.append("failed_attempts = 0, locked_until = NULL")
    if not set_parts:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Aucun champ à modifier")
    values.append(user_id)
    async with conn.cursor(row_factory=dict_row) as cur:
        try:
            await cur.execute(
                f"UPDATE acces.users SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = %s {_RETURNING}",
                values,
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Email ou nom d'utilisateur déjà utilisé") from exc
            raise
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return _to_user_response(row)


async def _set_active(conn, user_id: uuid.UUID, active: bool) -> dict:
    extra = ", failed_attempts = 0, locked_until = NULL" if active else ""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"UPDATE acces.users SET is_active = %s{extra}, updated_at = NOW() WHERE id = %s {_RETURNING}",
            (active, user_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable")
    return _to_user_response(row)


@router.post("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _admin=_ADMIN,
):
    await _guard_admin_loss(conn, user_id, current, deactivate=True, demote=False)
    return await _set_active(conn, user_id, False)


@router.post("/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(
    user_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    _admin=_ADMIN,
):
    return await _set_active(conn, user_id, True)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_user(
    user_id: uuid.UUID,
    conn: Annotated[AsyncConnection, Depends(get_conn)],
    current: Annotated[TokenPayload, Depends(get_current_user)],
    _admin=_ADMIN,
):
    await _guard_admin_loss(conn, user_id, current, deactivate=True, demote=False)
    await _set_active(conn, user_id, False)
