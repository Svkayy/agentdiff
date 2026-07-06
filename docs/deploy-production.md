# Deploying AgentDiff to production

This guide covers a self-hosted production deployment of the AgentDiff hosted
platform: TLS, database migrations, backups, scaling, CORS, and secret
rotation. It builds on the base `docker-compose.yml` with the
`docker-compose.prod.yml` overlay.

## Hosting the UI on Vercel

AgentDiff's public landing page, docs, legal pages, and authenticated dashboard
are now one Vite SPA under `frontend/`. Vercel can host that UI as the single
public link, while the API, worker, Postgres, and Redis stay on your
self-hosted/Docker stack.

1. In Vercel, import the AgentDiff GitHub repo.
2. Set the project root directory to `frontend/`.
3. Keep the default Vite build settings (`npm run build`, output `dist`).
4. Add environment variables:

   ```text
   VITE_CLERK_PUBLISHABLE_KEY=pk_live_...
   VITE_AGENTDIFF_API_URL=https://api.your-agentdiff-domain.example
   ```

5. Deploy.

After deployment, set the API's `AGENTDIFF_CORS_ORIGINS` to the Vercel UI
origin (and any custom domain you attach). Vercel only hosts the browser UI;
it does not run the AgentDiff API, worker, Postgres, or Redis.

The Vite app includes `frontend/vercel.json`, which rewrites all public and
dashboard routes back to `index.html` so direct links such as `/docs`,
`/privacy`, `/projects`, and `/runs/<id>` work as SPA routes.

---

## Self-hosted stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The overlay changes three things versus local dev:

1. A one-shot **`migrate`** service runs `alembic upgrade head` to completion.
   `api` and `worker` wait on it (`depends_on: service_completed_successfully`)
   and **no longer migrate at boot** — schema changes apply exactly once even
   when you scale the API to multiple replicas.
2. **`nginx`** terminates TLS, redirects http→https, sets HSTS, and reverse-
   proxies to `api` and `dashboard`. Only nginx publishes host ports (80/443);
   Postgres, Redis, api, and dashboard are reachable only on the internal
   compose network.
3. Sentry (`AGENTDIFF_SENTRY_DSN`) and a tightened `AGENTDIFF_CORS_ORIGINS`
   are wired through to the api/worker.

---

## 1. TLS certificates (Let's Encrypt / certbot)

nginx expects a certificate chain and private key at:

```
deploy/certs/fullchain.pem
deploy/certs/privkey.pem
```

Edit `deploy/nginx.conf` and replace `agentdiff.example.com` with your domain
first.

### Issue certs with certbot (webroot mode)

```bash
# One-time: create the webroot the http-01 challenge is served from.
mkdir -p deploy/certbot

# Issue (run on the host with ports 80/443 free, or use the nginx webroot).
certbot certonly --webroot -w deploy/certbot \
  -d agentdiff.example.com \
  --email ops@example.com --agree-tos --no-eff-email

# Copy the issued material into deploy/certs (or symlink the live/ dir).
cp /etc/letsencrypt/live/agentdiff.example.com/fullchain.pem deploy/certs/
cp /etc/letsencrypt/live/agentdiff.example.com/privkey.pem   deploy/certs/
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart nginx
```

### Renewal

Certbot certs last 90 days. Renew and reload nginx via cron:

```cron
# /etc/cron.d/agentdiff-certs — renew weekly, reload nginx on change
0 3 * * 1 root certbot renew --quiet --deploy-hook \
  "cp /etc/letsencrypt/live/agentdiff.example.com/*.pem /opt/agentdiff/deploy/certs/ && \
   docker compose -f /opt/agentdiff/docker-compose.yml -f /opt/agentdiff/docker-compose.prod.yml restart nginx"
```

Do **not** enable the HSTS header (`Strict-Transport-Security`, already present
in `nginx.conf`) until every host under the domain serves HTTPS — the
`max-age=31536000` pin is sticky in browsers.

---

## 2. Database migrations

Migrations run once via the `migrate` service. To apply a new migration after
pulling code:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up migrate
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

To check the current head or roll back one revision manually:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate alembic current
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate alembic downgrade -1
```

---

## 3. Backups (pg_dump + tested restore)

### Automated nightly dumps

```cron
# /etc/cron.d/agentdiff-backup — nightly logical backup, 14-day retention
0 2 * * * root docker compose -f /opt/agentdiff/docker-compose.yml exec -T postgres \
  pg_dump -U agentdiff -Fc agentdiff > /var/backups/agentdiff/agentdiff-$(date +\%F).dump && \
  find /var/backups/agentdiff -name 'agentdiff-*.dump' -mtime +14 -delete
```

`-Fc` writes the custom (compressed) format, which `pg_restore` can restore
selectively and in parallel.

### Tested restore procedure

A backup you have never restored is not a backup. Verify it on a scratch DB:

```bash
# 1. Spin up a throwaway postgres (or use a separate database name).
docker compose exec -T postgres createdb -U agentdiff agentdiff_restore_test

# 2. Restore the dump into it.
cat /var/backups/agentdiff/agentdiff-2026-07-05.dump | \
  docker compose exec -T postgres pg_restore -U agentdiff -d agentdiff_restore_test --no-owner

# 3. Sanity-check row counts, then drop the scratch DB.
docker compose exec -T postgres psql -U agentdiff -d agentdiff_restore_test \
  -c "SELECT count(*) FROM runs; SELECT count(*) FROM orgs;"
docker compose exec -T postgres dropdb -U agentdiff agentdiff_restore_test
```

For a full disaster-recovery restore, restore into a fresh `agentdiff` DB
**before** starting api/worker so the schema and data are consistent, then run
`up -d`.

---

## 4. Scaling

- **API** is stateless — scale horizontally:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale api=3
  ```

  nginx load-balances across replicas via the `api` service DNS name. Because
  migrations are owned by the one-shot `migrate` service, extra replicas start
  cleanly without racing on schema.

- **Worker** can also be scaled (`--scale worker=N`). The drift and retention
  crons are guarded by Redis `SET NX EX` leases (`agentdiff:cron:drift`,
  `agentdiff:cron:retention`), so only one worker executes each cron per
  interval — no double drift runs, no double deletes. `process_run` is
  registered with `max_tries=3` so a transient DB/Redis blip retries.

- **Postgres / Redis** are single-instance here. For higher availability move
  to a managed Postgres (with read replicas / PITR) and a managed Redis, and
  point `AGENTDIFF_DATABASE_URL` / `AGENTDIFF_REDIS_URL` at them.

### Retention

The daily retention cron enforces the documented data contract:

| Env var                          | Default | Effect                                              |
| -------------------------------- | ------- | --------------------------------------------------- |
| `AGENTDIFF_RETENTION_DAYS`       | `90`    | Deletes Runs older than N days. `0` disables.       |
| `AGENTDIFF_LIVE_RETENTION_DAYS`  | `30`    | Deletes LiveTrajectories older than N days. `0` disables. |

---

## 5. CORS tightening

The default `AGENTDIFF_CORS_ORIGINS` is `http://localhost:5173` (dev). In
production set it to **exactly** your dashboard origin(s) — never `*` — since
the API sends credentialed requests:

```bash
AGENTDIFF_CORS_ORIGINS=https://app.example.com
# Multiple origins: comma-separated, no spaces.
AGENTDIFF_CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

---

## 6. Secret rotation

### Encryption key rotation (MultiFernet)

Slack tokens are encrypted at rest with a Fernet key
(`AGENTDIFF_SECRET_ENCRYPTION_KEY`). The value is **comma-separated**: the
first key is the *primary* (used to encrypt new data), and any following keys
are *fallbacks* (used only to decrypt older ciphertext). This is a MultiFernet
setup, so rotation is zero-downtime:

1. Generate a new key:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Prepend it, keeping the old key as a fallback:

   ```bash
   # was:  AGENTDIFF_SECRET_ENCRYPTION_KEY=<OLD>
   AGENTDIFF_SECRET_ENCRYPTION_KEY=<NEW>,<OLD>
   ```

   Restart api + worker. New encryptions use `<NEW>`; existing ciphertext still
   decrypts with `<OLD>`.

3. (Optional) Re-encrypt existing rows by reading and writing each Slack config
   through the API, then drop `<OLD>`:

   ```bash
   AGENTDIFF_SECRET_ENCRYPTION_KEY=<NEW>
   ```

   Only remove `<OLD>` once you are confident no ciphertext still requires it —
   otherwise those rows become undecryptable.

### Slack app credentials

Rotate `AGENTDIFF_SLACK_CLIENT_SECRET` in the Slack app admin
(https://api.slack.com/apps → Basic Information → App Credentials → regenerate),
update the env var, and restart api. Existing per-project bot tokens are stored
encrypted and are unaffected; only the OAuth flow uses the client secret.

### Clerk keys

Rotate the Clerk instance secret / JWKS in the Clerk dashboard. Update
`AGENTDIFF_CLERK_JWKS_URL` / `AGENTDIFF_CLERK_ISSUER` (and the dashboard's
`VITE_CLERK_PUBLISHABLE_KEY`) if the instance changes, then rebuild the
dashboard and restart api. Because tokens are verified against the live JWKS
endpoint, key rollover at Clerk is picked up automatically on the next fetch.

---

## 7. Health & metrics

- `GET /health` returns `{"status": "ok"|"degraded", "checks": {"database":
  bool, "redis": bool}}` and HTTP `503` when either dependency is down. Point
  your load balancer / uptime monitor at it.
- `GET /metrics` exposes Prometheus counters: `agentdiff_requests_total`,
  `agentdiff_runs_processed_total`, `agentdiff_drift_checks_total`,
  `agentdiff_quota_rejections_total`. Counters are per-process, so scrape each
  API replica.
