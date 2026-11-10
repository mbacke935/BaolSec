# Image des outils du broker :
#  - broker-init : applique la topologie (flux, consommateurs, bucket KV), puis s'arrête ;
#  - dlq-monitor : expose la taille de la file de rejet pour Prometheus (dlq_admin.py metrics).
FROM python:3.12-slim
RUN pip install --no-cache-dir nats-py==2.16.0 prometheus-client==0.26.0 \
 && useradd --create-home --uid 10001 baolsec
WORKDIR /app
COPY broker/init_broker.py broker/dlq_admin.py broker/topology.json ./broker/
COPY state-store/detection-state.json ./state-store/
USER baolsec
CMD ["python", "broker/init_broker.py"]
