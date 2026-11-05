# Conteneur ponctuel qui applique la topologie du broker (flux, consommateurs, bucket KV), puis s'arrête.
FROM python:3.12-slim
RUN pip install --no-cache-dir nats-py==2.16.0 \
 && useradd --create-home --uid 10001 baolsec
WORKDIR /app
COPY broker/init_broker.py broker/topology.json ./broker/
COPY state-store/detection-state.json ./state-store/
USER baolsec
CMD ["python", "broker/init_broker.py"]
