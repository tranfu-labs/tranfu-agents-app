FROM node:20-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

COPY frontend ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TF_DB=/data/tf.db \
    PORT=8788

WORKDIR /app

COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && addgroup --system tranfu \
    && adduser --system --ingroup tranfu --home /app tranfu \
    && mkdir -p /data \
    && chown -R tranfu:tranfu /app /data

COPY --chown=tranfu:tranfu server ./server
COPY --from=frontend-build --chown=tranfu:tranfu /frontend/dist ./frontend/dist
COPY --chown=tranfu:tranfu install.sh ./install.sh
COPY --chown=tranfu:tranfu shims ./shims
COPY --chown=tranfu:tranfu llms.txt robots.txt ./

USER tranfu

VOLUME ["/data"]
EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/healthz', timeout=8).read()" || exit 1

CMD ["sh", "-c", "exec python -m uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8788}"]
