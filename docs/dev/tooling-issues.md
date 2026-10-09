---
items: [W08]
---

# Known tooling issues

Problems seen on development machines, and their fixes. Add an entry when something costs more than a few minutes.

## Docker unreachable from WSL
**Symptom:** tests that need Postgres are skipped with "Docker not reachable"; `docker ps` in WSL fails or runs a Windows-side shim.
**Cause:** Docker Desktop is running, but WSL integration is off for this distribution.
**Fix:** Docker Desktop ▸ Settings ▸ Resources ▸ WSL integration ▸ enable the distribution, then restart the WSL shell. Until then, `docker.exe compose config` can still validate Compose files.

## rtk compresses file reads
**Symptom:** an agent's edit fails because the text it "read" doesn't match the file.
**Cause:** rtk's output compression shortens long reads.
**Fix:** read exact bytes with `rtk proxy cat <file>`, or read in small ranges, before editing.
