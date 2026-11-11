FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS wheels
WORKDIR /build
COPY backend/pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip wheel --wheel-dir /wheels -r /tmp/requirements.txt
COPY backend/app ./app
RUN --mount=type=cache,target=/root/.cache/pip pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data STATIC_DIR=/opt/static TZ=UTC
RUN groupadd -g 10001 panel && useradd -u 10001 -g panel -M -s /usr/sbin/nologin panel \
    && mkdir /data && chown panel:panel /data
COPY --from=wheels /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels reality-control && rm -rf /wheels
WORKDIR /opt/backend
COPY --chown=10001:10001 backend/alembic.ini ./
COPY --chown=10001:10001 backend/alembic ./alembic
COPY --from=frontend /build/dist /opt/static
USER 10001:10001
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
