---
items: [EC-L03, EC-D05]
---

# Disk full

Use this when the disk space alert comes (the server's disk is 80% full or more), or when
Labra stops saving and the logs say `No space left on device`.

**Act within days of the alert.** When the disk is completely full, Postgres stops saving and
may shut down, and Labra stops working for everyone. Freeing space doesn't touch the lab's
data if you follow this page.

**Never delete** anything inside Docker's volumes by hand (`/var/lib/docker/volumes/`), and
never the `secrets/` folder: they hold the database, the stored reports and the passwords.

## 1. See what is using the space

On the server, in the folder where Labra is installed:

```bash
scripts/labra.sh check-disk           # how full, as the alert sees it
df -h /                               # the whole disk
docker system df                      # images, containers and volumes
sudo du -xh --max-depth=1 /var | sort -h | tail
```

Most of the space normally goes to the database and the stored reports (the volumes), which
grow slowly. Something that grew fast is usually one of the items below.

## 2. Free space safely, in this order

1. **Old Labra images.** Each upgrade leaves the previous version's image behind, a few
   hundred MB each. Keep the one in use and the one before it (for a rollback); remove older
   ones:

   ```bash
   docker image ls
   docker image prune                    # images no container uses and that have no name
   docker image rm ghcr.io/premdon009/labra:0.1.0    # an old version, by name
   ```

2. **Export files.** `labra export` writes into the `exports` volume. Copy what is needed to an
   encrypted disk ([Data export](../manual/admin/data-export.md)), then remove the old ones:

   ```bash
   docker compose exec web ls -la /data/export
   docker compose exec web rm -r /data/export/<old folder>
   ```

3. **Container logs.** The install guide caps them; if that step was skipped, they can grow
   without end. Check `sudo du -sh /var/lib/docker/containers`, then set the cap
   ([install guide](../install/laptop.md#4-docker)) and `docker compose up -d --force-recreate`.
4. **The system journal and package cache:**

   ```bash
   sudo journalctl --vacuum-size=200M
   sudo apt-get clean
   ```

5. **The backup cache.** The `backup_cache` volume only speeds up backups and can be emptied;
   the next backup rebuilds it:

   ```bash
   docker volume rm labra_backup_cache
   ```

   (It fails while a backup is running. Wait a minute and try again.)

Check again with `scripts/labra.sh check-disk`. It should say `Disk space OK`.

## 3. If Labra had already stopped

1. Free space as above until `df -h /` shows at least a few GB free.
2. `docker compose up -d`, then open Labra on a main-lab PC.
3. `docker compose logs --tail 50 db` should end with `database system is ready to accept
   connections`. Postgres finishes anything it was writing by itself.
4. Take a backup now (`scripts/backup.sh backup`) and check the audit log
   (`scripts/labra.sh audit verify`).

## 4. For the long run

The database grows by well under 1 GB a year and the stored reports by about 6 to 7 GB a year
for a lab of this size ([design](../design/v1-plan.md), *Backups*), so a 256 GB disk lasts many
years. If the disk is genuinely too small:

- move to a bigger SSD: take a backup, fit the new disk, install as on a new server and
  restore ([Restore from backup](restore-from-backup.md#a-new-server));
- old reports are never deleted from Labra: the lab must keep them for at least two years.
