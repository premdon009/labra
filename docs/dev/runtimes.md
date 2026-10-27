---
items: [W17, W18, W19, W42]
---

# Container runtimes

Labra runs the same image and the same `compose.yaml` on Docker, Podman, containerd (nerdctl) and
Incus ([ADR-0009](../adr/0009-runtime-neutral-packaging.md)). This page covers what to install
to test each one directly on a machine, how to compare them, and what differs between them.

## Install for testing
Commands for Ubuntu 26.04 (also under WSL2 with systemd on). Each runtime is independent;
install the ones you want to compare. `scripts/check_tools.sh` lists what it finds.

| Runtime | Install | Then |
|---|---|---|
| Docker Engine | [docs.docker.com/engine/install/ubuntu](https://docs.docker.com/engine/install/ubuntu/), or Docker Desktop | `docker info` works |
| Podman, Buildah | `sudo apt install podman buildah podman-compose uidmap passt` | `systemctl --user enable --now podman.socket` (for `podman compose` with the docker-compose provider) |
| containerd, nerdctl | the `nerdctl-full` release tarball, pinned: see below | `containerd-rootless-setuptool.sh install` |
| Incus | `sudo apt install incus` | `sudo incus admin init --minimal`, then `sudo usermod -aG incus-admin $USER` and log in again |
| Kaniko | nothing; it runs as a container on Docker or Podman | — |
| Podman Desktop | [podman-desktop.io](https://podman-desktop.io) (Windows, macOS) | see the checklist below |

nerdctl, pinned by checksum (the version `scripts/portability_job.sh` installs):
```sh
v=2.4.1
curl -fsSLO https://github.com/containerd/nerdctl/releases/download/v$v/nerdctl-full-$v-linux-amd64.tar.gz
echo "ff018f11ac2f1354bf7b3aaaca6e0b52d81139c746a89134744d0b7be3a0e62f  nerdctl-full-$v-linux-amd64.tar.gz" | sha256sum -c
sudo tar -C /usr/local -xzf nerdctl-full-$v-linux-amd64.tar.gz
containerd-rootless-setuptool.sh install
```

Under WSL2, if `incus admin init` fails on IPv6 firewall rules, create the bridge without IPv6:
`incus network create incusbr0 ipv6.address=none`.

## Compare them
```sh
scripts/compare_runtimes.sh                       # every runtime and builder found
scripts/compare_runtimes.sh --runtimes "podman nerdctl" --builders buildah
```
It builds the image once, loads the same archive into each runtime, and for each one runs
`stack_smoke.sh` (16 end-to-end checks) and then measures:

| Measure | How |
|---|---|
| Ready | seconds from `compose up` (images already pulled) until `/readyz` answers 200 through the proxy |
| Engine idle / stack up | resident memory of the runtime's own processes (dockerd, containerd and shims; Podman's conmon, pasta and aardvark-dns), before and while the stack runs |
| Stack containers | memory of the stack's containers from `<runtime> stats`, at rest and after load |
| Throughput | requests per second and 95th percentile latency for `/healthz` (proxy and app) and `/readyz` (also the database), 8 keep-alive connections for 15 s |
| Web restart | the web process exits; seconds until the runtime restarts it and it's ready again |
| Log driver, request ID | where the runtime keeps logs, and whether a request ID sent through the proxy comes back and appears in `<runtime> logs` |
| Builders | build and rebuild time per builder, then `check_image.sh` on the result |

Results go to a `results.md` in a temporary directory (or `--out DIR`). The numbers compare
runtimes on the same machine with the same load generator; they aren't absolute capacity
figures. Docker Desktop runs its engine in a separate VM, so its engine memory shows as n/a and
its ports pass through an extra forwarding layer.

## How they differ

| | Docker Engine | Podman | containerd + nerdctl | Incus |
|---|---|---|---|---|
| Shape | two daemons (dockerd, containerd) and a shim per container | no daemon; one small monitor (conmon) per container | one daemon (containerd) and a shim per container; nerdctl is only a CLI | a daemon running whole-OS system containers; the stack runs with Podman inside one |
| Weight at idle | heaviest of the three app runtimes | lightest: nothing runs when no container does | in between | heaviest: a full OS layer on top |
| Rootless | optional mode | the default | optional (RootlessKit) | containers are unprivileged by default |
| Compose | `docker compose`, the reference | `podman compose`, using docker-compose or podman-compose | `nerdctl compose`; ignores `depends_on` health conditions | whatever runs inside |
| Health checks | run by the daemon | run by systemd timers; without systemd they never run and `service_healthy` waits forever | not relied on; `labra migrate` waits for Postgres itself | inside |
| Restart after a crash | daemon restart policy | conmon restarts on exit | containerd's restart monitor | inside |
| Start at boot | the daemon starts the containers | `systemctl --user enable podman-restart.service` and `loginctl enable-linger` | containerd's user service | `boot.autostart` on the system container |
| Logs | `json-file` by default | `journald` on systemd hosts, else `k8s-file` | `json-file` | inside |
| Events | `docker events` | `podman events` | `nerdctl events` | `incus monitor` |
| Licence | Apache-2.0 (Engine); Docker Desktop has paid terms for larger companies | Apache-2.0 | Apache-2.0 | Apache-2.0 |

**Logs and traces are the same everywhere.** The app writes JSON lines to stdout with a
`request_id` on every request, and returns it in the `X-Request-ID` header (taking the caller's
if it's well formed). A runtime only stores stdout, so any collector that reads container logs
works on all of them; the comparison checks the ID survives proxy and runtime on each one.
Metrics are a `/metrics` endpoint, also independent of the runtime. Distributed traces (OTLP)
will be sent over the network to a collector (X35), so they won't depend on the runtime either.

## Known issues
- **Podman needs systemd for health checks.** In a container or a WSL distribution without
  systemd, `db` stays `starting` and `compose up` never finishes.
- **Podman 5 splits a Compose health check's arguments at spaces** (`podman compose` with the
  docker-compose provider, Podman 5.4 and 5.7; Podman 6 doesn't). `python -c "import …"` then
  fails with a `SyntaxError` and `web` is never healthy. The health checks run
  `python -m labra.probe /readyz` instead: no argument holds a space.
- **Podman 4.9.3 with netavark 1.4.0** (Ubuntu 24.04) gives containers no DNS on an
  `internal: true` network, so `migrate` can't find `db`. Podman 5.8.7 works.
- **podman-compose 1.0.6** (Ubuntu 24.04) ignores `profiles`, so it starts every tunnel too.
  1.6.0 works; or use `podman compose` with the docker-compose provider.
- **podman-compose** starts each container's monitor (`conmon`) as its own child, so a
  container started by a script inherits the script's open files. The job scripts close
  their lock before calling Compose (`9<&-`); without that, a container started by
  `restore.sh` held the lock and the next backup, drill or restore waited for it.
- **podman-compose `ps`** takes no service name, so scripts find a service's container by its
  Compose labels (`com.docker.compose.project` and `com.docker.compose.service`).
- **podman-compose `depends_on`** treats `service_completed_successfully` as "stopped", so it
  starts web after a failed migration, and it waits for ever for a `service_healthy`
  dependency that never gets healthy. `scripts/upgrade.sh` therefore runs the migrations as a
  job first, and gives the stack start `LABRA_UPGRADE_WAIT` seconds.
- **`podman compose`** prints a banner on stderr each time it hands over to a provider. Scripts
  that capture output should read stdout only.
- **Rootless nerdctl on Ubuntu 23.10 and later** stops at "RootlessKit failed" with
  `apparmor_restrict_unprivileged_userns is set to 1`: AppArmor refuses user namespaces to a
  program without a profile. Give RootlessKit one, as `scripts/portability_job.sh` does
  (`install_nerdctl`), then run `containerd-rootless-setuptool.sh install`, and
  `containerd-rootless-setuptool.sh install-buildkit` to build images.
- **nerdctl compose** pulls a missing image where Docker and Podman build it, so load the
  backup image before `compose run backup` (`scripts/compare_runtimes.sh` puts both images in
  its archive). Its `ps` can list two containers for one service; scripts take the newest.
- **nerdctl compose `stop web`** also stops the services web depends on, the database among
  them, and its `compose run` doesn't start them again. `stop_web` in
  `scripts/compose_run.sh` stops web, then starts the database and waits until it is ready.
- **nerdctl compose `run`** of a service that depends on the database starts a second database
  container on the same volume, and `compose exec db` may then pick that one once it has
  stopped. `scripts/upgrade.sh` runs the migrations with `--no-deps`, against the database
  `stop_web` left running.
- **nerdctl compose `run`** has no `-T`, and without a terminal it runs the container detached
  and exits 0 whatever the container did. The scripts run every job through
  `scripts/compose_run.sh`: on Docker and Podman that is `run --rm -T`; on nerdctl it starts
  the job detached, waits for it, then prints its output and returns its exit status. A job's
  output therefore appears when it ends; following the logs lost the last lines.
- **`nerdctl build`** uses BuildKit, which looks a `FROM` image up in a registry, never among
  the local images. The smoke test makes its upgrade images there by committing a container
  of the local image instead.
- **nginx looked the web app up once**, when it started. Under Podman a restore or an
  upgrade recreates web at a new address, and nginx answered 502. `deploy/nginx/labra.conf`
  is now a template: the nginx image's entrypoint fills in the DNS server from the
  container's `resolv.conf`, and nginx looks web up again every 10 seconds.
- **A failed smoke test says why.** When the stack doesn't start, `scripts/stack_smoke.sh`
  prints each container's state and what its last health checks printed; a drill, restore or
  upgrade that hangs is stopped after `SMOKE_STEP_LIMIT` seconds (default 600) with the
  Compose and engine commands still running. `scripts/compare_runtimes.sh` shows the whole log
  of a failed run.
- **Rootless ports below 1024** are refused. Use `LABRA_HTTP_PORT=8080 LABRA_HTTPS_PORT=8443`,
  or allow them once: `sudo sysctl -w net.ipv4.ip_unprivileged_port_start=80` (and add it to
  `/etc/sysctl.d/`).
- **Rootless limits need cgroup v2** with the `cpu`, `memory` and `pids` controllers
  delegated to the user. Without them Podman refuses to start a container that has limits, and
  rootless Docker drops the limits with a warning. Check with
  `cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/cgroup.controllers`.
- **Tests on Podman:** point testcontainers at Podman's socket with
  `DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock TESTCONTAINERS_RYUK_DISABLED=true`,
  or skip containers and use `LABRA_TEST_DATABASE_URL` with a database whose name ends in
  `_test`.

## Run the portability jobs locally
`.github/workflows/portability.yml` runs each row on a fresh GitHub runner. The commands for
each row are in `scripts/portability_job.sh`, so the same rows can run here before a push:

```sh
scripts/ci_portability.sh                            # every row, two at a time
scripts/ci_portability.sh nerdctl podman-compose --jobs 1
scripts/ci_portability.sh --if-needed                # only if the branch changes a watched path
```

Each row gets its own lab: a privileged Ubuntu 26.04 container from
`deploy/ci-lab/Containerfile` with systemd as PID 1, Docker, Podman, Buildah and a sudo user
`runner`. Podman's health checks, its socket and rootless containerd therefore run as user
services, as they do on the runner. The script builds the lab image once (again only when the
Containerfile changes) and the app and backup images once on this machine. It loads those images
into every lab along with the pinned Postgres, Caddy, nginx and Kaniko images and the app
image's Python and uv base images and Dockerfile frontend, so a lab pulls nothing except
Kaniko's base images. It copies in the working tree, uncommitted changes included, and runs
`portability_job.sh --install ROW` and then `portability_job.sh ROW` as `runner`. At the end it
prints one line per row: PASS, FAIL with the log to read, or SKIP with the reason. It exits 1 if
any row failed.

Logs and each row's results go to `.ci/portability/<UTC time>/<row>/`. `--build` makes each row
build its own images, as the runner does. `--keep` leaves the labs running, so you can look
inside with `docker exec -it -u runner labra-ci-<UTC time>-<row> bash`.

The local run doesn't cover everything the GitHub run does:
- **incus** is always SKIP: it needs a VM, so it runs on GitHub only.
- **Docker's version differs.** The lab has Ubuntu's `docker.io` package (29.1.3, Compose
  2.40.3), not the Docker packages on GitHub's runner image, and the kernel is this machine's.
  A fault tied to one Docker release or kernel can still show up only on GitHub.
- **outside-postgres** starts a throwaway PostgreSQL at the digest the workflow's service
  runs, instead of a service container.
- **Kaniko in the builders row** fetches its base images from the registries itself, so its
  build can fail here when Docker Desktop drops a pull
  ([tooling issues](tooling-issues.md#docker-desktop-pulls-fail-now-and-then)). A Kaniko
  failure with a registry error in `build-kaniko.log` is the network, not the change; GitHub's
  run checks Kaniko.

The lab is built this way for these reasons:
- systemd boots as PID 1 under `--privileged --cgroupns=private` with `/run` on tmpfs, also on
  Docker Desktop under WSL2, so Podman's health checks run as they do on a host. The cgroup
  namespace must be the lab's own: with the host's, systemd sees its tree under
  `/docker/<id>/` while Podman looks for a pod's slice at the top, asks systemd to create it a
  second time, and podman-compose waits for ever on containers that never start.
- `/var/lib/docker`, `/var/lib/containerd`, `/var/lib/containers` and `/home/runner` are
  volumes. An overlay filesystem inside another one refuses whiteouts, and `docker load` then
  failed with "operation not permitted".
- Commands run as `runner` get Docker's default `PATH`, the `sbin` directories included.
  `containerd-rootless-setuptool.sh` writes the `PATH` it runs with into the containerd user
  service, and RootlessKit needs `ip` from `iproute2`.
- Recommended packages are installed, as the runner's `apt-get install` does. Without them
  Podman has no `aardvark-dns`, and the stack's containers can't find each other by name.
- `/` is made a shared mount at boot, which Podman needs.
- The lab is on Docker's default bridge, so it gets this machine's name servers, as the runner
  has real ones. On a network of its own it would see only Docker's `127.0.0.11`, and nerdctl
  would print a notice about it on every `run` into output the checks compare.

## Podman Desktop on Windows
A GUI, so it's checked by hand once per release:
1. Install Podman Desktop, create the Podman machine, and enable "Docker compatibility".
2. In the machine's terminal, clone the repository and create `secrets/` as in
   [Running the stack](running-the-stack.md).
3. Run `scripts/stack_smoke.sh --compose "podman compose"`; every line should be PASS.
4. Open `https://labra.lan:18443` from Windows after adding `127.0.0.1 labra.lan` to the
   hosts file, with the stack started by `stack_smoke.sh --keep`.

## Verified
Every combination below passed `stack_smoke.sh` or `check_image.sh`. These runs were made
inside a test container, so they prove behaviour, not performance:

| Runtime or builder | Version | Result |
|---|---|---|
| Docker Engine, Caddy and nginx | 29.8.1 | 16/16 checks |
| Podman rootless, docker-compose provider, Caddy and nginx | 5.8.7, compose 5.5.1 | 16/16 checks |
| Podman rootless, podman-compose, Caddy and nginx | 5.8.7, podman-compose 1.6.0 | 16/16 checks |
| containerd + nerdctl compose, Caddy and nginx | 2.4.1 | 16/16 checks |
| Builds: Docker, Podman, Buildah, Kaniko (fork) | BuildKit, 5.8.7, 1.43.4, 1.28.5 | image checks pass |
| Incus system container with nesting | 6.23 | starts and runs Podman; the full stack needs a run on a real host |
| Tailscale and NetBird profiles | 1.102.5, 0.80.0 | start and wait for login; the proxy keeps serving |
| Local CI lab, every portability row ([above](#run-the-portability-jobs-locally)), 2026-10-26 | Docker 29.1.3, Compose 2.40.3, Podman 5.7.0, podman-compose 1.5.0, nerdctl 2.4.1 | every row passes but incus, which is SKIP; a full run takes about 30 minutes two at a time |

## Measured
`compare_runtimes.sh` on one WSL2 laptop, 10 s of load per endpoint. Run it again on the
server that will host the lab; only numbers from the same machine compare.

| Runtime | Ready | Stack memory | After load | `/healthz` | `/readyz` | Errors | Web restart | Logs | Request ID in logs |
|---|---|---|---|---|---|---|---|---|---|
| Docker Desktop 29.8.1 | 20.4 s | 308 MiB | 348 MiB | 162 req/s, p95 56 ms | 147 req/s, p95 68 ms | 0 | 3.3 s | json-file | yes |

| Builder | First build | Rebuild | Image checks |
|---|---|---|---|
| Docker (BuildKit, warm cache) | 5.5 s | 2.0 s | PASS |
| Kaniko fork, no registry cache | 76.7 s | 76.7 s | PASS |

Kaniko rebuilds everything each time unless it's given a registry for `--cache-repo`, so it
suits CI on a cluster rather than the lab server.
