"""Crée (ou réinitialise) le premier compte administrateur de BaolSec.

Le schéma est le schéma normalisé C4 (acces.users.role_id → acces.roles). L'utilisateur est
identifié par son username (NOT NULL UNIQUE). Le compte est réactivé et déverrouillé.

Usage, dans le conteneur de l'API (compte svc_api, déjà configuré) :
    make admin-create
    # ou : docker compose exec -e ADMIN_EMAIL=moi@exemple.sn baolsec-api python seed_admin.py

Variables : ADMIN_USERNAME (admin), ADMIN_EMAIL (admin@baolsec.local), ADMIN_PW.
Sans ADMIN_PW, un mot de passe aléatoire est généré et affiché une seule fois.
"""
import os
import secrets
import sys

import psycopg
from baolsec_api.auth import hash_password

dsn = os.environ["POSTGRES_DSN"]
username = os.environ.get("ADMIN_USERNAME", "admin")
email = os.environ.get("ADMIN_EMAIL", "admin@baolsec.local")
pw = os.environ.get("ADMIN_PW") or secrets.token_urlsafe(15)
if len(pw) < 8:
    sys.exit("ADMIN_PW : 8 caractères au minimum.")

with psycopg.connect(dsn, autocommit=True) as conn:
    # Un compte existant est retrouvé d'abord par son e-mail, puis par son identifiant (tous deux
    # uniques) : il est promu administrateur, réactivé et déverrouillé, avec le nouveau mot de passe.
    by_email = conn.execute("SELECT id, username, email FROM acces.users WHERE lower(email) = lower(%s)",
                            (email,)).fetchone()
    by_name = conn.execute("SELECT id, username, email FROM acces.users WHERE username = %s",
                           (username,)).fetchone()
    if by_email and by_name and by_email[0] != by_name[0] and "ADMIN_USERNAME" in os.environ:
        sys.exit(f"{email} appartient au compte « {by_email[1]} » et l'identifiant « {username} » à un autre "
                 f"compte ({by_name[2]}). Utilisez ADMIN_USERNAME={by_email[1]} ou une autre adresse.")
    target = by_email or by_name
    rows = [target] if target else []
    if rows:
        user_id, username, _ = rows[0]
        conn.execute(
            """UPDATE acces.users SET
                 email           = %s,
                 password_hash   = %s,
                 role_id         = (SELECT id FROM acces.roles WHERE name = 'Administrateur'),
                 is_active       = true,
                 failed_attempts = 0,
                 locked_until    = NULL
               WHERE id = %s""",
            (email, hash_password(pw), user_id),
        )
    else:
        conn.execute(
            """INSERT INTO acces.users (username, email, password_hash, role_id)
               VALUES (%s, %s, %s, (SELECT id FROM acces.roles WHERE name = 'Administrateur'))""",
            (username, email, hash_password(pw)),
        )

print(f"Compte administrateur prêt : {username} ({email})")
if not os.environ.get("ADMIN_PW"):
    print(f"Mot de passe généré (affiché une seule fois) : {pw}")
