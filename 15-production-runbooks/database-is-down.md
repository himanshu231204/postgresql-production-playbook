# Runbook: Database Is Down

Applies to PostgreSQL 16, self-managed. On managed services, see
[the managed note](#managed-services).

## Symptoms

- App errors: `connection refused`, `could not connect to server`, `the database system is starting up`, `the database system is in recovery mode`, `the database system is shutting down`.
- `pg_isready` exit code `1` (rejecting connections) or `2` (no response).
- Health check fails, but the host itself is reachable.

## Triage (first 2 minutes)

Unix shell:

```bash
pg_isready -h HOST -p 5432; echo "exit=$?"
```

| Exit | Meaning | Next |
|---|---|---|
| `0` | Server is up. The problem is network, auth, or connection limits | [connection-exhaustion.md](connection-exhaustion.md); check firewall/DNS/`pg_hba.conf` |
| `1` | Process alive but rejecting: startup, **crash recovery in progress**, or shutting down | Watch the log (below). **Do not restart**; recovery may be progressing |
| `2` | No response: process dead, wrong host/port, or firewall | Check the process, below |
| `3` | Bad `pg_isready` arguments | Fix the command |

Is the process running? Pick your platform (these are OS commands, not SQL):

| Platform | Command |
|---|---|
| Linux (systemd, Debian/Ubuntu) | `pg_lsclusters` ; `systemctl status postgresql@16-main` |
| Linux (systemd, RHEL/Fedora) | `systemctl status postgresql-16` |
| Any Unix | `ps -ef \| grep '[p]ostgres -D'` ; `pg_ctl -D "$PGDATA" status` |
| macOS (Homebrew) | `brew services list` |
| Windows (PowerShell) | `Get-Service -Name 'postgresql*'` ; `Test-NetConnection -ComputerName localhost -Port 5432` |
| Docker | `docker ps -a --filter name=postgres` ; `docker compose ps` |

Service unit names vary by distro and install method. List them with
`systemctl list-units 'postgresql*'` if unsure.

## Diagnosis

### Step 1: Read the log. It names the cause.

Find the log location. If the server is up (even partially), ask it (SQL):

```sql
SHOW data_directory;
SHOW log_directory;           -- relative paths are inside data_directory
SHOW logging_collector;
SELECT pg_current_logfile();  -- NULL when logging_collector is off
```

If `logging_collector` is `off`, logs go to stderr: read them via the
service manager instead.

| Platform | Command (Unix shell / PowerShell as labeled) |
|---|---|
| Linux, systemd (Unix shell) | `journalctl -u postgresql@16-main -n 200 --no-pager` (RHEL: `-u postgresql-16`) |
| Debian/Ubuntu file log (Unix shell) | `tail -n 200 /var/log/postgresql/postgresql-16-main.log` |
| Collector enabled (Unix shell) | `tail -n 200 "$PGDATA"/log/postgresql-*.log` (use the file `pg_current_logfile()` reports) |
| macOS Homebrew (Unix shell) | `tail -n 200 "$(brew --prefix)"/var/log/postgresql@16.log` |
| Windows (PowerShell) | `Get-Content -Tail 200 (Get-ChildItem 'C:\Program Files\PostgreSQL\16\data\log' \| Sort-Object LastWriteTime \| Select-Object -Last 1).FullName` |
| Docker (Unix shell) | `docker logs --tail 200 CONTAINER` |

If the server will not start and you have no log, start it in the
foreground to see the error on the terminal (Unix shell; stop with Ctrl-C):

```bash
sudo -u postgres /usr/lib/postgresql/16/bin/postgres -D /path/to/data
```

(Path from your package; it differs per OS.)

### Step 2: Match the log line

Every message below was reproduced on PostgreSQL 16.

| Log line (excerpt) | Cause | Fix |
|---|---|---|
| `FATAL: lock file "postmaster.pid" already exists` + `HINT: Is another postmaster (PID n) running in data directory ...?` | Another postmaster really is running, or the PID in the file is alive (including reused by an unrelated process or a not-yet-reaped zombie) | Check `ps -p n`. If it is the real server, use it. Do not start a second one |
| `could not bind IPv4 address "...": Address already in use` + `could not create any TCP/IP sockets` | Another process (often a second PostgreSQL) holds the port | `ss -ltnp \| grep :5432` (Linux) / `lsof -nP -iTCP:5432 -sTCP:LISTEN` (macOS) / `Get-NetTCPConnection -LocalPort 5432` (PowerShell). Stop the other process or change `port` |
| `FATAL: data directory "..." has invalid permissions` + `Permissions should be u=rwx (0700) or u=rwx,g=rx (0750)` | Directory mode changed (bad restore/copy, `chmod -R`) | `chmod 700 "$PGDATA"` as the owner |
| `FATAL: configuration file ".../postgresql.conf" contains errors` preceded by `invalid value for parameter "x"` or `unrecognized configuration parameter "x" in file ... line N` | Bad edit to `postgresql.conf` / `postgresql.auto.conf` | Fix the named line, or revert from version control/backup. Validate before restart (below) |
| `database system was not properly shut down; automatic recovery in progress` ... `redo starts at ...` ... `redo done at ...` ... `database system is ready to accept connections` | Crash recovery (normal after a crash, `kill -9`, power loss) | **Wait.** See [recovery in progress](#crash-recovery-in-progress) |
| `PANIC: could not write to file "pg_wal/..."`: `No space left on device` | Disk full | [disk-full.md](disk-full.md) |
| `FATAL: could not open file ...: Permission denied` / `Operation not permitted` | Ownership/SELinux/AppArmor/volume mount changed | Fix ownership (`chown -R postgres:postgres "$PGDATA"`), check security module logs |
| `FATAL: could not access file "...": No such file or directory` for a `shared_preload_libraries` entry | Library listed but not installed | Remove it from `shared_preload_libraries` or install the package |
| `PANIC: could not locate a valid checkpoint record` / `invalid checkpoint record` | WAL or `pg_control` damaged | Stop. Go to [Escalation](#escalation--when-to-stop) |

Validate configuration without starting the server (Unix shell). It prints
the same `invalid value` / `unrecognized` errors and exits non-zero:

```bash
sudo -u postgres /usr/lib/postgresql/16/bin/postgres -D "$PGDATA" -C data_directory
```

On Debian/Ubuntu the config lives in `/etc/postgresql/16/main/`; pass
`-c config_file=/etc/postgresql/16/main/postgresql.conf` and
`-D /var/lib/postgresql/16/main`.

### Crash recovery in progress

A log sequence like this on a restart after a crash is **normal**:

```text
LOG:  database system was interrupted; last known up at ...
LOG:  database system was not properly shut down; automatic recovery in progress
LOG:  redo starts at 0/1506818
LOG:  invalid record length at 0/1506988: expected at least 24, got 0
LOG:  redo done at 0/1506960 ...
LOG:  checkpoint starting: end-of-recovery immediate wait
LOG:  database system is ready to accept connections
```

`invalid record length ... got 0` at the end of WAL is the expected end of
redo, not corruption. During recovery clients get
`FATAL: the database system is in recovery mode` and `pg_isready` returns
`1`. Recovery time is bounded by the WAL generated since the last
checkpoint (see `max_wal_size`, `checkpoint_timeout`). Watch progress with
`tail -f` on the log. Do not kill or restart the process while `redo` is
running unless you have a hard reason: the next start repeats the work.

## Remediation (ordered, safest first)

| # | Action | When | Risk |
|---|---|---|---|
| 1 | Wait and tail the log | `pg_isready` = `1`, recovery messages present | None |
| 2 | Fix the cause the log names (config line, permissions, port conflict, library) | Log names a cause | Low: change one thing, record it |
| 3 | Start the service | Process is down and the cause is fixed | Low |
| 4 | Free disk space | Disk-full messages | See [disk-full.md](disk-full.md) |
| 5 | Remove a **stale** `postmaster.pid` | Only after step 6 below proves no postgres process uses that data directory | Medium |
| 6 | Restore from backup | Checkpoint/WAL corruption, or storage loss | See [restore-database.md](restore-database.md) |

Start commands:

| Platform | Command |
|---|---|
| Linux systemd (Unix shell) | `sudo systemctl start postgresql@16-main` (RHEL: `postgresql-16`) |
| Any Unix (Unix shell) | `sudo -u postgres pg_ctl -D "$PGDATA" -l /path/to/startup.log start` |
| macOS (Unix shell) | `brew services start postgresql@16` |
| Windows (PowerShell, admin) | `Start-Service -Name postgresql-x64-16` |
| Docker (Unix shell) | `docker compose up -d postgres` (service name from your compose file) |

Always give `pg_ctl start` a `-l` log file, otherwise the server's stderr is
attached to your terminal and lost when it closes.

### Stale `postmaster.pid` (risky: read first)

- **What it does:** `postmaster.pid` in the data directory marks a running server. After `kill -9` or power loss it remains.
- **Normal case needs no action.** PostgreSQL checks whether the recorded PID is alive; if the process is gone, it starts normally (reproduced: after `kill -9` of the postmaster, the next `pg_ctl start` printed `another server might be running; trying to start server anyway` and succeeded).
- **Risk of deleting it by hand:** if a postgres process **is** still running on that directory (including orphaned child processes) and you start a second postmaster, two servers write the same files. This corrupts the cluster.
- **Safer alternative:** try to start first; the server decides if the file is stale.
- **Precaution:** only if start still fails with `lock file "postmaster.pid" already exists`, confirm no process holds the directory: `ps -ef | grep '[p]ostgres'` and `lsof +D "$PGDATA"` (Linux/macOS). Only when both are empty, move the file aside (`mv postmaster.pid /tmp/postmaster.pid.bak`) rather than deleting it.

### Killing the postmaster (risky)

- **What it does:** `kill -9` on the postmaster (or a child) forces the whole server through crash recovery; `kill -9` on a backend triggers a cluster-wide restart.
- **Risk:** in-flight transactions are lost, and the server is unavailable for the whole recovery.
- **Safer alternative:** `pg_ctl -D "$PGDATA" stop -m fast` (rolls back sessions, checkpoints, clean shutdown). Use `-m immediate` only if `fast` hangs, knowing it causes crash recovery on next start.
- **Precaution:** announce the outage and confirm the target host/instance.

## Verification

```bash
pg_isready -h HOST -p 5432; echo "exit=$?"      # expect: accepting connections, exit=0
```

```sql
SELECT pg_postmaster_start_time(), now() - pg_postmaster_start_time() AS uptime;
SELECT pg_is_in_recovery();   -- false on a primary; true on a standby (expected there)
```

- [ ] Application health check green, connection count normal.
- [ ] Log shows no repeating `ERROR`/`FATAL`/`PANIC` after `ready to accept connections`.
- [ ] Replicas reconnected (primary: `SELECT * FROM pg_stat_replication;`).
- [ ] If crash recovery occurred, run `ANALYZE;` (statistics may be stale) and review the cause before closing.

## Prevention

- Alert on `pg_isready`/synthetic query failure and on disk usage well before 100%.
- Validate config changes with `postgres -C` (above) and reload with `SELECT pg_reload_conf();` before restart-requiring changes.
- Keep a tested restore path: [07-backups-recovery/disaster-recovery.md](../07-backups-recovery/disaster-recovery.md).
- Run a replica or managed HA so one host loss is a failover, not an outage ([13-cloud-production/architecture.md](../13-cloud-production/architecture.md)).
- Set `restart: unless-stopped` for containers and a systemd `Restart=` policy only after you understand why it crashed: a crash loop can hide data-corruption signals.
- Health checks: [14-observability/health-checks.md](../14-observability/health-checks.md).

## Escalation / When to stop

Stop and escalate to a senior DBA or vendor support if you see:

- `PANIC: could not locate a valid checkpoint record`, `invalid checkpoint record`, or repeated `invalid page` / checksum errors.
- Recovery that does not finish and the log shows no progress for an extended period.
- Storage-layer errors (I/O errors in `dmesg`/`journalctl -k`, volume detach).

Before anyone considers `pg_resetwal`:

- **What it does:** discards WAL and forces `pg_control` to a new state so the server will start.
- **Risk:** can leave the database logically inconsistent (partial transactions, broken indexes, lost committed data) without any error.
- **Safer alternative:** restore from backup or PITR ([restore-database.md](restore-database.md)).
- **Precaution:** copy the whole data directory first (`cp -a` / volume snapshot), get explicit lead sign-off, and treat the result as untrusted: dump it, restore into a fresh cluster, and never go back to serving from it.

## Managed services

You cannot run `pg_ctl` or read the host. Check the provider console for
instance status, events (maintenance, failover, storage-full), and logs; fail
over or restore via the provider. Storage-full is the most common cause of
"down" on managed instances: see [disk-full.md](disk-full.md). Provider
notes: [13-cloud-production/managed-postgresql.md](../13-cloud-production/managed-postgresql.md).
