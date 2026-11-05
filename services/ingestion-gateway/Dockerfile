# Passerelle d'ingestion — image non root (C2 ES-10).
# Contexte de construction : racine du dépôt (pour inclure shared/python-common).
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 baolsec
WORKDIR /app
COPY shared/python-common /opt/python-common
RUN pip install --no-cache-dir "/opt/python-common[nats]"
COPY services/ingestion-gateway/pyproject.toml ./
COPY services/ingestion-gateway/src ./src
RUN pip install --no-cache-dir --no-deps . \
 && pip install --no-cache-dir fastapi==0.162.0 uvicorn==0.54.0 pydantic-settings==2.16.2 \
    prometheus-client==0.26.0 "psycopg[binary]==3.3.8"
USER baolsec
EXPOSE 8443 6514 9000
CMD ["python", "-m", "gateway.main"]
