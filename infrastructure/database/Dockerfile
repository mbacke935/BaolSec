# Conteneur ponctuel db-migrate : applique les migrations du schéma (C4) et pose les mots de passe
# des comptes de service, puis s'arrête.
FROM python:3.12-slim
RUN pip install --no-cache-dir alembic==1.16.5 sqlalchemy==2.0.43 "psycopg[binary]==3.3.8" \
 && useradd --create-home --uid 10001 baolsec
WORKDIR /app
COPY database/alembic.ini database/migrate.py ./database/
COPY database/migrations ./database/migrations
COPY database/sql ./database/sql
USER baolsec
CMD ["python", "database/migrate.py"]
