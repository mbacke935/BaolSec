"""
PATCH C21 — Intégration AuditMiddleware dans main.py (diff à appliquer).

Dans baolsec_api/main.py, ajouter après les imports existants :

    from .middleware import AuditMiddleware

Et dans create_app(), après l'ajout du CORSMiddleware :

    app.add_middleware(AuditMiddleware)

C'est tout : le middleware s'enchaîne automatiquement dans le pipeline ASGI.
"""
