# SSL / TLS

## What it is

TLS encrypts the connection between client and PostgreSQL and, with
certificate verification, proves the client is talking to the intended
server. PostgreSQL docs and parameters still use the name "SSL".

## Why it matters

Without TLS, credentials (after authentication) and all query data cross
the network readable by anyone on the path. Encryption alone is not
enough: a client that does not verify the server certificate can be
redirected to an impostor.

## Server configuration

`postgresql.conf` (PostgreSQL 16):

```
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'root.crt'            # needed to verify client certificates
ssl_min_protocol_version = 'TLSv1.2' # the default since PostgreSQL 12
```

- `ssl_key_file` must not be group/world accessible: mode `0600` owned
  by the postgres user, or `0640` owned by root with the postgres user
  in the owning group. PostgreSQL refuses to start otherwise.
- Changing `ssl` requires a reload (`pg_ctl reload`, `SELECT
  pg_reload_conf();`, or `systemctl reload postgresql`) in PostgreSQL 10
  and later; certificate files are reread on reload.
- Also set `listen_addresses` to specific interfaces, not `'*'`, unless
  a firewall/security group restricts access (see
  [13-cloud-production/networking.md](../13-cloud-production/networking.md)).

## Enforcing TLS with `pg_hba.conf`

`pg_hba.conf` is read top to bottom; the **first matching line wins**.

```
# TYPE    DATABASE  USER     ADDRESS        METHOD
hostssl   appdb     app_api  10.0.0.0/8     scram-sha-256
hostnossl all       all      0.0.0.0/0      reject
```

- `hostssl` matches only TLS connections; `hostnossl` matches only
  non-TLS ones. A `hostnossl ... reject` line after the allow rules
  forces TLS for everything else.
- Reload after editing: `SELECT pg_reload_conf();`.
- Check for syntax errors: `SELECT line_number, error FROM
  pg_hba_file_rules WHERE error IS NOT NULL;`

## Client `sslmode` (libpq / psql)

| `sslmode` | Encrypts | Verifies server cert | Verifies hostname | Use |
|---|---|---|---|---|
| `disable` | No | No | No | Local socket / tests only |
| `allow` | Only if server insists | No | No | Avoid |
| `prefer` (libpq **default**) | If server supports it, silently falls back to plaintext | No | No | Not suitable for production |
| `require` | Yes | No | No | Encrypts but accepts any certificate |
| `verify-ca` | Yes | Yes (trusted CA) | No | Weaker than `verify-full` |
| `verify-full` | Yes | Yes | Yes | **Production default** |

```bash
# Unix shell; psql with full verification
psql "host=db.internal port=5432 dbname=appdb user=app_api sslmode=verify-full sslrootcert=/etc/ssl/certs/db-ca.pem"
```

`verify-full` needs the server certificate's CN or SAN to match the
hostname the client connects to, and the CA certificate in
`sslrootcert` (default `~/.postgresql/root.crt`). Managed services
publish their CA bundle; download and pin it (see
[13-cloud-production/ssl-tls.md](../13-cloud-production/ssl-tls.md)).

Python drivers: `psycopg`/libpq accept `sslmode` in the URL. asyncpg
does not take libpq's `sslmode`/`sslrootcert` URL parameters (with
SQLAlchemy's asyncpg dialect they raise `TypeError`) and its default is
`prefer`. For `verify-full` semantics, pass an `ssl.SSLContext`:

```python
import ssl

context = ssl.create_default_context(cafile="/etc/ssl/certs/db-ca.pem")
engine = create_async_engine(DATABASE_URL, connect_args={"ssl": context})
```

`?ssl=require` encrypts without verifying the server certificate. Behavior
checked with asyncpg 0.31 and SQLAlchemy 2.x; re-check against the
versions you pin. See
[08-python-fastapi/async-postgresql.md](../08-python-fastapi/async-postgresql.md).

## Verify the connection is encrypted

| Command | Type | Result |
|---|---|---|
| `\conninfo` | psql meta-command | Prints `SSL connection (protocol: TLSv1.3, cipher: ...)` when encrypted |
| `SELECT ssl, version, cipher FROM pg_stat_ssl WHERE pid = pg_backend_pid();` | PostgreSQL SQL | `ssl = t` for this session |
| `SELECT a.usename, s.ssl, s.version FROM pg_stat_ssl s JOIN pg_stat_activity a USING (pid) WHERE a.backend_type = 'client backend';` | PostgreSQL SQL | Find any client connected without TLS |

## Client certificates (optional)

Add `clientcert=verify-full` to a `hostssl` line (or use the `cert`
method) so the client must present a certificate signed by
`ssl_ca_file`. This replaces or supplements password authentication;
it needs certificate issuance and rotation processes.

## Common mistakes

- Leaving the libpq default `sslmode=prefer` in production and assuming
  the connection is encrypted.
- `sslmode=require` without a CA: protects against passive sniffing but
  not an active man-in-the-middle.
- Certificate hostname mismatch, then "fixing" it by downgrading to
  `require` instead of issuing a correct certificate.
- Forgetting certificate expiry: monitor the notAfter date; an expired
  server certificate breaks every `verify-*` client at once.
- Terminating TLS at a pooler or proxy and leaving the proxy-to-database
  hop plaintext: encrypt both hops, or document the trust boundary.

## Troubleshooting

| Symptom | Check |
|---|---|
| `server does not support SSL, but SSL was required` | `ssl = on`? Cert and key files present, key permissions correct? Check the server log |
| `certificate verify failed` | `sslrootcert` points at the CA that signed the server cert; certificate not expired |
| `server certificate for "x" does not match host name "y"` | Connect using a name in the certificate's SAN, or reissue it |
| `FATAL: no pg_hba.conf entry for host ... no encryption` | Client connected without TLS and only `hostssl` lines match; set `sslmode` correctly |

## Quick revision

- Server: `ssl = on`, protected key file, `ssl_min_protocol_version = 'TLSv1.2'` or higher.
- `pg_hba.conf`: `hostssl` allow lines, `hostnossl ... reject` after.
- Clients: `sslmode=verify-full` with a pinned CA; never rely on `prefer`.
- Confirm with `pg_stat_ssl`.
