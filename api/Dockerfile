FROM node:22-alpine AS ui-build
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/api/src \
    UI_DIST_DIR=/app/ui/dist

WORKDIR /app

COPY api/pyproject.toml /app/api/pyproject.toml
COPY api/src /app/api/src
RUN pip install --no-cache-dir -e /app/api

COPY api /app/api
COPY samples /app/samples
COPY evals /app/evals
COPY --from=ui-build /app/ui/dist /app/ui/dist
COPY api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chown -R appuser:appuser /app

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "tabular_analyst.main:app", "--host", "0.0.0.0", "--port", "8000"]
