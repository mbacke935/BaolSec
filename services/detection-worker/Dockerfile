# Moteur de détection (C12, C14) — image non root (C2 ES-10).
# Contexte de construction : racine du dépôt (shared/python-common, shared/contracts et rules/).
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 baolsec
WORKDIR /app
COPY shared/python-common /opt/python-common
RUN pip install --no-cache-dir "/opt/python-common[nats]"
COPY shared/contracts /opt/baolsec/contracts
COPY rules /opt/baolsec/rules
COPY services/detection-worker/pyproject.toml ./
COPY services/detection-worker/src ./src
RUN pip install --no-cache-dir --no-deps . \
 && pip install --no-cache-dir pyyaml==6.0.2 jsonschema-rs==0.59.0 fastapi==0.162.0 uvicorn==0.54.0 \
    pydantic-settings==2.16.2 prometheus-client==0.26.0 "psycopg[binary]==3.3.8"
USER baolsec
ENV DETECTOR_CONTRACTS_DIR=/opt/baolsec/contracts DETECTOR_RULES_DIR=/opt/baolsec/rules
EXPOSE 9000
CMD ["python", "-m", "detector.main"]
