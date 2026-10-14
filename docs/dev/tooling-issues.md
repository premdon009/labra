---
items: [W08]
---

# Known tooling issues

Problems seen on development machines, and their fixes. Add an entry when something costs more than a few minutes.

## A test failed once, then passed
**Symptom:** the gate's tests stage failed, and a re-run is green.
**Cause:** an intermittent test: timing, ordering, or state left by another test.
**Fix:** the gate re-runs a failed test once and names it `flaky` when it then passes. The failed run's logs are kept: `ls .ci/runs/*/flaky.txt` and `grep -l '^FAILED' .ci/runs/*/pytest.txt` find the run, and its `pytest.txt` names the test and shows the error. Fix the test; don't re-run until it's green.

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
