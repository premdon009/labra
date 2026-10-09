---
items: [W17, W18, W19]
status: accepted
date: 2026-10-09
---

# ADR-0009: Runtime-neutral packaging

## Context
Labra ships as a container image and a Compose file, and until now it was proven only on Docker with Caddy and Cloudflare Tunnel. A lab may have to move to another runtime (licence terms, a distribution's packages, a rootless policy, Windows desktops) or away from one edge vendor. That move should be a change of command, not a rewrite.

## Decision
- **One OCI image** built from one `Dockerfile` by any of Docker (BuildKit), Podman, Buildah or Kaniko. Podman and Buildah build with `--format docker` so the image keeps its `HEALTHCHECK`.
- **Fully qualified image names** with digests everywhere (`docker.io/library/postgres:18@sha256:…`). Podman and Buildah refuse short names without a registry search list; `scripts/audit_deps.py` fails on one.
- **The common subset of the Compose spec** that Docker Compose, `podman compose` (with either provider) and `nerdctl compose` all honour. Where one implementation is weaker, the app covers the gap instead of the file: `labra migrate` waits for Postgres because nerdctl doesn't wait on health checks.
- **Nothing tied to one host's user numbers:** secrets live in a 0700 directory, and the one the app reads is mode 0644, since rootless runtimes remap the app's user. Ports, the proxy subnet and the secrets directory are settings.
- **Every edge piece has a tested alternative:** nginx for Caddy (an override file), and Tailscale/Headscale or NetBird for Cloudflare Tunnel (profiles). The app sets its own security headers, so the proxy only adds HSTS, TLS and the `/metrics` block.
- **One smoke test for all of them.** `scripts/stack_smoke.sh` brings the stack up on any Compose implementation and checks it end to end; `scripts/check_image.sh` checks an image from any builder; `scripts/compare_runtimes.sh` runs both on every runtime installed and measures them.
- **Support tiers:**
  - Tier 1: Docker Engine and Podman 5, tested on every change to the deploy files.
  - Tier 2: containerd with nerdctl, and Incus (Podman inside a system container), tested weekly.
  - Kubernetes stays out of scope (design §4).

## Consequences
- Moving runtime is `podman compose up -d` instead of `docker compose up -d`, with the same files and secrets.
- New Compose features are used only when every Tier 1 and Tier 2 implementation supports them; the smoke test catches the ones that don't.
- Known floors: Podman 4.9.3 with netavark 1.4.0 (Ubuntu 24.04) gives no DNS on internal networks, and podman-compose 1.0.6 ignores profiles; Podman 5.8.7 and podman-compose 1.6.0 pass. Details and workarounds are in [Container runtimes](../dev/runtimes.md).
- Kaniko's original project was archived in 2025; the maintained fork is pinned instead, and dropping Kaniko costs nothing because Buildah covers rootless, daemonless builds.
