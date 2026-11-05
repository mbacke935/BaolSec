"""Affiche un nouveau jeton de source et son empreinte à enregistrer dans secret_hash."""
from . import generate_token, hash_token

token = generate_token()
print(f"jeton (à configurer dans l'agent, affiché une seule fois) : {token}")
print(f"secret_hash (à enregistrer dans config.source_credentials) : {hash_token(token)}")
