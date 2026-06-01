FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/api/src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

COPY api/pyproject.toml /app/api/pyproject.toml
COPY api/src /app/api/src
RUN pip install --no-cache-dir -e /app/api

COPY api /app/api
COPY samples /app/samples
COPY evals /app/evals

EXPOSE 8000
CMD ["uvicorn", "tabular_analyst.main:app", "--host", "0.0.0.0", "--port", "8000"]
