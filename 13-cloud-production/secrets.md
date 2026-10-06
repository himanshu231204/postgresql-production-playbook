# Secrets Management in the Cloud

Where database credentials live, how they reach the application, and how
to rotate them without an outage. Password hashing, `~/.pgpass`, `.env`
rules, and the base rotation steps are in
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md);
this page covers the cloud layer. Checklist:
[06-security/security-checklist.md](../06-security/security-checklist.md).

## What it is

A secrets manager is a managed store with access control, audit logging,
versioning, and (usually) rotation hooks. The application's runtime
identity (workload identity, instance role, service account) is allowed
to read specific secrets; no human or CI job holds the production
password.

## Why it matters

A `DATABASE_URL` in a repo, image layer, CI log, or ticket is a full
login. Centralizing secrets gives one place to rotate, audit reads, and
revoke.

## Credential types

| Type | Mechanism | Tradeoff |
|---|---|---|
| Static password in a secrets manager | App reads at start (or periodically) and builds the connection | Simple and portable; rotation requires coordination |
| Short-lived token as the password (provider IAM-style database auth) | App requests a token from the platform and uses it as the password | No long-lived secret; token fetch is a dependency; connection limits and rate limits on token use exist; provider-specific. Existing connections are unaffected by expiry, new ones need a fresh token |
| Dynamic secrets (a secrets system creates a temporary role per lease) | Role created on demand, dropped at lease end | Strong blast-radius control; adds a system to run; many roles to manage and clean up |
| Client certificates (mutual TLS) | Certificate identifies the client | Needs issuance/rotation; not supported by every managed service |

Pick by who you can operate: a static secret with a rehearsed rotation
beats a dynamic system nobody understands. Provider-specific forms of
token auth are not covered here; consult the provider's documentation.

## Delivery to the application

| Method | Notes |
|---|---|
| Platform injects secret as an environment variable at start | Easy; visible to anyone who can read the process environment or container spec; restart needed to change |
| Mounted file (tmpfs) refreshed by an agent | App can re-read without restart; protect file mode |
| App fetches from the secrets API at start and on failure | Needs runtime identity and network path to the API; cache in memory only |
| CI injects at deploy | Never print; mask in logs; scope per environment |

Rules:

- Separate secrets per role (application, migration, admin) and per
  environment; the application never holds the migration or admin
  credential ([06-security/least-privilege.md](../06-security/least-privilege.md)).
- Build the connection from separate parts (host, user, password,
  database), so the password is never in a logged URL.
- Mask connection strings in logs and error reporting.
- Never put secrets in a `Dockerfile` `ENV`/`ARG` or compose file; see
  [12-docker/environment-variables.md](../12-docker/environment-variables.md).
- Restrict who can read the production secret to the runtime identity and
  a break-glass group; alert on reads by anything else.

## Rotation

Rotation must be a routine the team has already executed, not an
emergency invention.

### Overlap pattern (no downtime)

1. Create the new credential alongside the old: either a second login
   role in the same group (`app_api_b`) or, for single-role rotation, a
   change that both app versions tolerate.
2. Write the new value to the secrets manager as a new version.
3. Roll the application so every instance and pooler reads the new
   value. Poolers hold server connections with the old credential until
   they are recycled; restart or reload them (for PgBouncer, update the
   auth source and `RELOAD`).
4. Verify nothing uses the old credential:

   ```sql
   SELECT usename, application_name, count(*)
   FROM pg_stat_activity
   WHERE backend_type = 'client backend'
   GROUP BY 1, 2
   ORDER BY 3 DESC;
   ```

5. Disable the old credential (`ALTER ROLE app_api_a NOLOGIN;`), watch
   for errors, then drop it later.

This alternating-roles approach is the zero-downtime version of the base
procedure in 06-security. Changing a password with `ALTER ROLE` does not
disconnect existing sessions; new connections from instances that still
hold the old value fail.

### Automated rotation

If the secrets manager rotates automatically, test these failure modes:

- Rotation succeeds in the manager but the database change fails (or the
  reverse): the manager and the database disagree. Alert on rotation
  failure; know the manual repair.
- Pooler or app caches the old value indefinitely.
- The rotation function itself runs with a privileged credential;
  protect it like the admin role.
- Rotation of the superuser/admin credential has no application impact;
  rotate that on a schedule too.

### When a secret leaks

Rotate immediately (overlap pattern, fast), find the exposure, check
`pg_stat_activity` and server logs for logins by the leaked role from
unexpected addresses, and review recent grants. Deleting a commit does
not un-leak it.

## Common mistakes

- Sharing one password across environments or roles.
- Rotating the password in the manager without restarting the poolers.
- Giving CI the production application password "for smoke tests".
- Long-lived static credentials with no owner and no rotation date.
- Putting the full URL, including the password, in an error message.
- Treating the secrets manager as private by default; verify access
  policies and audit logs.

## Security considerations

Audit every read of the production secret. Use separate roles to make
rotation of one credential not affect the others. Provider IAM-style
database authentication and secrets-manager features differ per cloud;
verify against current provider docs before designing around them.

## Troubleshooting

| Symptom | Check |
|---|---|
| `FATAL: password authentication failed` after rotation | Some instances or the pooler still hold the old value; SCRAM requires correct stored hash for the new password |
| Errors begin hours after rotation | Connections made with the old credential were alive until recycled; the pool just opened a new one |
| App cannot read secret at startup | Runtime identity policy, network path to the secrets service, wrong secret version |
| Rotation job reports success but logins fail | Manager and database out of sync; set the password explicitly and re-fetch |

## Quick revision

- Secrets manager plus workload identity; no human holds production passwords.
- One credential per role and environment; app never has DDL or admin.
- Rotate with overlapping roles; recycle poolers; verify with `pg_stat_activity`.
- Short-lived tokens remove a long-lived secret but add a runtime dependency.
