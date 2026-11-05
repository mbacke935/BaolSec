# Indexation — image non root (C2 ES-10). Fixer la version exacte de l'image avant la mise en production.
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 baolsec
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
USER baolsec
CMD ["python", "-m", "indexer.main"]
