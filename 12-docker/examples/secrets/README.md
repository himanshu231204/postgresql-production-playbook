# secrets/

Local files for `compose.prod-like.yaml` (Compose file-based secrets).

```bash
umask 077
printf '%s' 'REPLACE_WITH_GENERATED_PASSWORD' > postgres_password.txt
```

- `postgres_password.txt` is git-ignored (see `../.gitignore`). Do not commit it.
- Do not use a password-like value that ends up in shell history; generate it
  with a password manager or `openssl rand -base64 32`.
- The file must be readable by the container's `postgres` user (see
  `../../persistent-volumes.md` for the UID check).
