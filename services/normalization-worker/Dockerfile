# Service de normalisation et d'enrichissement (C9, C10) — image non root (C2 ES-10).
# Contexte de construction : racine du dépôt (pour inclure shared/python-common et shared/contracts).
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 baolsec
WORKDIR /app
COPY shared/python-common /opt/python-common
RUN pip install --no-cache-dir "/opt/python-common[nats]"
COPY shared/contracts /opt/baolsec/contracts
COPY services/normalization-worker/pyproject.toml ./
COPY services/normalization-worker/src ./src
RUN pip install --no-cache-dir --no-deps . \
 && pip install --no-cache-dir jsonschema-rs==0.59.0 fastapi==0.162.0 uvicorn==0.54.0 \
    pydantic-settings==2.16.2 prometheus-client==0.26.0 "psycopg[binary]==3.3.8"
USER baolsec
ENV NORMALIZER_CONTRACTS_DIR=/opt/baolsec/contracts
EXPOSE 9000
CMD ["python", "-m", "normalizer.main"]
