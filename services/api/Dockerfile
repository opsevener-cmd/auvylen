FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS build
COPY --from=ghcr.io/astral-sh/uv:0.11@sha256:77280f2f771df71f90786c314fe1bbc1e023feac652969bbf139c280babf2eb7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_HTTP_TIMEOUT=120
COPY pyproject.toml uv.lock ./
COPY services/api services/api
COPY services/inference services/inference
COPY packages/contracts packages/contracts
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --locked --no-dev --no-editable

FROM build AS checks
RUN --mount=type=cache,target=/root/.cache/uv --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --locked
COPY conftest.py ./
CMD ["uv", "run", "pytest", "--integration"]

FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 APP_ENV=production
RUN useradd --create-home --uid 10001 auvylen
RUN mkdir -p /var/lib/auvylen/uploads /var/lib/auvylen/models && chown -R 10001:10001 /var/lib/auvylen && chmod 700 /var/lib/auvylen/uploads /var/lib/auvylen/models
COPY --from=build /app/.venv /app/.venv
COPY --chown=auvylen:auvylen services/api/alembic.ini services/api/alembic.ini
COPY --chown=auvylen:auvylen services/api/migrations services/api/migrations
USER auvylen
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"
CMD ["uvicorn", "aevyra_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header", "--no-proxy-headers"]
