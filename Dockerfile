# syntax=docker/dockerfile:1
# The Labra web image. Base images are pinned by digest; scripts/audit_deps.py --check fails
# on one that isn't. Names are fully qualified, so Podman, Buildah and Kaniko resolve them
# without a registry search list. Built for amd64 and arm64 in CI.

FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv

FROM docker.io/library/python:3.14-slim@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE CHANGELOG.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM docker.io/library/python:3.14-slim@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2
# Pango, HarfBuzz and fontconfig for WeasyPrint; the fonts themselves are vendored.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fontconfig \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --home-dir /app labra \
    && mkdir -p /data/files /data/export \
    && chown labra /data/files /data/export \
    && chmod 700 /data/export
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CACHE_HOME=/tmp/labra-cache
USER labra
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
CMD ["labra", "serve", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
