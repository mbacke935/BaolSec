"""Crée (ou met à jour) un compte administrateur pour la démo de l'interface.

Le schéma est le schéma normalisé C4 (acces.users.role_id → acces.roles), posé
par la pile : `make db-up`. On insère donc en résolvant le rôle « Administrateur »
en FK, et on identifie l'utilisateur par son username (NOT NULL UNIQUE, C4).

Usage (contre la base de la pile, en tant que propriétaire) :
    POSTGRES_DSN="postgresql://postgres:<mot_de_passe>@127.0.0.1:5432/baolsec" \
      uv run --python 3.13 --extra dev python seed_admin.py

Variables optionnelles : ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PW.
"""
import os
import psycopg
from baolsec_api.auth import hash_password

dsn = os.environ["POSTGRES_DSN"]
username = os.environ.get("ADMIN_USERNAME", "admin")
email = os.environ.get("ADMIN_EMAIL", "admin@baolsec.local")
pw = os.environ.get("ADMIN_PW", "Admin1234!")

with psycopg.connect(dsn, autocommit=True) as conn:
    conn.execute(
        """INSERT INTO acces.users (username, email, password_hash, role_id)
           VALUES (%s, %s, %s, (SELECT id FROM acces.roles WHERE name = 'Administrateur'))
           ON CONFLICT (username) DO UPDATE SET
             email         = EXCLUDED.email,
             password_hash = EXCLUDED.password_hash,
             role_id       = EXCLUDED.role_id,
             is_active     = true""",
        (username, email, hash_password(pw)),
    )

print(f"Admin prêt : {username} / {email} / {pw}")