---
items: [W08]
---

# Known tooling issues

Problems seen on development machines, and their fixes. Add an entry when something costs more than a few minutes.

## A test failed once, then passed
**Symptom:** the gate's tests stage failed, and a re-run is green.
**Cause:** an intermittent test: timing, ordering, or state left by another test.
**Fix:** the gate re-runs a failed test once and names it `flaky` when it then passes. The failed run's logs are kept: `ls .ci/runs/*/flaky.txt` and `grep -l '^FAILED' .ci/runs/*/pytest.txt` find the run, and its `pytest.txt` names the test and shows the error. `uv run python scripts/flaky_report.py` shows whether it has happened before. Fix the test; don't re-run until it's green.

## Docker unreachable from WSL
**Symptom:** tests that need Postgres are skipped with "no Postgres for tests"; `docker ps` in WSL fails or runs a Windows-side shim.
**Cause:** Docker Desktop is running, but WSL integration is off for this distribution.
**Fix:** Docker Desktop ▸ Settings ▸ Resources ▸ WSL integration ▸ enable the distribution, then restart the WSL shell. Until then, `docker.exe compose config` can still validate Compose files.

## Docker socket: permission denied in WSL
**Symptom:** `docker version` in WSL shows the client, then "permission denied while trying to connect to the docker API at unix:///var/run/docker.sock"; database tests are skipped.
**Cause:** you were added to the `docker` group (`getent group docker` lists you) after the WSL session started, so running shells don't have the group (`id` doesn't show it).
**Fix:** in PowerShell, `wsl --shutdown`, then reopen the terminal or the editor's WSL window; `id` should now list `docker`. Until then, `docker.exe` (the Windows client) still reaches the engine, so `docker.exe build .` works.

## rtk compresses file reads
**Symptom:** an agent's edit fails because the text it "read" doesn't match the file.
**Cause:** rtk's output compression shortens long reads.
**Fix:** read exact bytes with `rtk proxy cat <file>`, or read in small ranges, before editing.

## Docker Desktop pulls fail now and then
**Symptom:** `docker pull` fails with "tls: error decoding message" or "server gave HTTP response to HTTPS client".
**Cause:** Docker Desktop's built-in proxy drops a registry connection now and then.
**Fix:** retry; `scripts/compare_runtimes.sh` retries pulls itself.

## `podman compose` output has a stray banner
**Symptom:** a script that captures `podman compose exec …` output gets an extra line or escape codes.
**Cause:** `podman compose` prints a banner on stderr each time it hands over to its provider.
**Fix:** capture stdout only (`2>/dev/null`), not `2>&1`.

## The install rehearsal VM loses its network
**Symptom:** in a qemu VM with user-mode networking (slirp), started from inside a Docker container, SSH to the guest drops as soon as Docker starts in the guest; later, downloads in the guest fail with TLS decode errors.
**Cause:** slirp keeps a forwarded connection's real source address, which clashes with the guest's own `docker0` when the outer container also sits on 172.17.0.0/16. Once Docker turns on IP forwarding in the guest, slirp corrupts outgoing TCP.
**Fix:** run the qemu container on its own network (`docker network create --subnet 10.99.0.0/24 …`). In the guest, set `"ip-forward": false` in `/etc/docker/daemon.json` and `net.ipv4.ip_forward=0`, load the Labra images built on the host (`docker save` / `docker load`), and accept that the guest's containers have no internet. HTTPS from the host through the forwarded port still stalls; test from inside the guest.
