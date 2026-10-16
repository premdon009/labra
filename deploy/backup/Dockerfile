# syntax=docker/dockerfile:1
# The Labra backup image (ADR-0013): the database's own postgres:18 image, so pg_dump and psql
# match the server, plus restic and rclone release binaries checked by SHA-256. It runs one job
# and exits; host timers start it with `compose --profile jobs run --rm backup …`.
# Versions and checksums have rows in docs/DEPENDENCIES.md (scripts/audit_deps.py --check).

FROM docker.io/library/postgres:18@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336 AS fetch
ARG RESTIC_VERSION=0.19.1
ARG RESTIC_SHA256_AMD64=f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c
ARG RESTIC_SHA256_ARM64=a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465
ARG RCLONE_VERSION=1.75.2
ARG RCLONE_SHA256_AMD64=349ac8fba6ff65d6247043f1750cdcb518ec5d500ef91463a10d37c0ccdf3702
ARG RCLONE_SHA256_ARM64=7e1e8d69654941b7b7df84ee74c5f7fb09cce7d5496947fb7bf16b55ff427d10
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl bzip2 unzip \
    && rm -rf /var/lib/apt/lists/*
# dpkg names the architecture the same way both projects do (amd64, arm64), whichever builder
# runs this; TARGETARCH isn't set by every one of them.
RUN set -eu; \
    arch=$(dpkg --print-architecture); \
    case $arch in \
      amd64) restic_sum=$RESTIC_SHA256_AMD64; rclone_sum=$RCLONE_SHA256_AMD64 ;; \
      arm64) restic_sum=$RESTIC_SHA256_ARM64; rclone_sum=$RCLONE_SHA256_ARM64 ;; \
      *) echo "no checksum for $arch" >&2; exit 1 ;; \
    esac; \
    cd /tmp; \
    curl -fsSLo restic.bz2 "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_${arch}.bz2"; \
    echo "$restic_sum  restic.bz2" | sha256sum -c -; \
    bunzip2 restic.bz2; \
    install -m 0755 restic /usr/local/bin/restic; \
    curl -fsSLo rclone.zip "https://github.com/rclone/rclone/releases/download/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-${arch}.zip"; \
    echo "$rclone_sum  rclone.zip" | sha256sum -c -; \
    unzip -q -j rclone.zip "*/rclone"; \
    install -m 0755 rclone /usr/local/bin/rclone

FROM docker.io/library/postgres:18@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336
# curl sends the heartbeat pings.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=fetch /usr/local/bin/restic /usr/local/bin/rclone /usr/local/bin/
COPY labra-backup.sh /usr/local/bin/labra-backup
# The same uid as the app, so the backup reads /data/files and owns what it writes to the USB disk.
RUN useradd --system --uid 10001 --home-dir /backup labra \
    && mkdir -p /backup/cache /backup/work \
    && chown -R labra /backup \
    && chmod 0755 /usr/local/bin/labra-backup
ENV RESTIC_CACHE_DIR=/backup/cache \
    RCLONE_CONFIG=/run/secrets/rclone_conf \
    RESTIC_PASSWORD_FILE=/run/secrets/restic_password
USER labra
WORKDIR /backup
ENTRYPOINT ["labra-backup"]
CMD ["help"]
