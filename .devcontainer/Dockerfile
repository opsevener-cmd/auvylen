FROM node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS node
FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS python
FROM postgres:18-bookworm@sha256:afc7e2d441324c0388fa80c3d24f733b4194a4eb7f47dd8ee2b08eb1a24a647c
COPY --from=python /usr/local /usr/local
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=ghcr.io/astral-sh/uv:0.11@sha256:77280f2f771df71f90786c314fe1bbc1e023feac652969bbf139c280babf2eb7 /uv /usr/local/bin/uv
# PostgreSQL 18 tools are already pinned in the base; only Debian dev utilities are needed.
RUN rm -f /etc/apt/sources.list.d/pgdg.list /etc/apt/sources.list.d/pgdg.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git curl procps supervisor gnupg libstdc++6 \
    libbz2-1.0 libffi8 libsqlite3-0 liblzma5 libreadline8 libexpat1 libncursesw6 libuuid1 libzstd1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && useradd --create-home --uid 1000 --shell /bin/bash auvylen
ENV NEXT_TELEMETRY_DISABLED=1 UV_HTTP_TIMEOUT=120 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
ENTRYPOINT []
USER auvylen
WORKDIR /workspaces/auvylen
CMD ["sleep", "infinity"]
