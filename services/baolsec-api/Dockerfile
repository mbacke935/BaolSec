# BaolSec — API REST (C18/C20)
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.7.3

COPY shared/python-common /app/shared/python-common
RUN uv pip install --system --no-cache /app/shared/python-common

COPY services/baolsec-api /app/service
RUN uv pip install --system --no-cache /app/service

RUN adduser --disabled-password --gecos "" baolsec
USER baolsec

EXPOSE 8000 9107
CMD ["python", "-m", "baolsec_api.main"]
