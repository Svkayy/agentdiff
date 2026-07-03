# Hosted Platform Quickstart

End-to-end walkthrough for setting up AgentDiff's multi-tenant hosted platform
(API server + background worker + React dashboard) for a new team.

---

## 1. Start the stack

### Prerequisites

- Docker and Docker Compose v2
- A [Clerk](https://clerk.com) account (free tier is fine)

### Create a Clerk application

1. In the Clerk dashboard create a new application (any name).
2. Note your **Publishable key** (starts with `pk_test_` or `pk_live_`).
3. Under **API Keys → Advanced** copy the **JWKS URL** and the **Issuer** (your
   Frontend API URL, e.g. `https://clerk.your-domain.com`).

### Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

```bash
# Generate a Fernet key for encrypting Slack tokens at rest:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

AGENTDIFF_SECRET_ENCRYPTION_KEY=<output from above>
AGENTDIFF_CLERK_JWKS_URL=https://<your-clerk-frontend-api>/.well-known/jwks.json
AGENTDIFF_CLERK_ISSUER=https://<your-clerk-frontend-api>
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
VITE_AGENTDIFF_API_URL=http://localhost:8000
```

### Bring up the stack

```bash
docker compose up --build -d
```

Five services start: `postgres`, `redis`, `api` (port 8000), `worker`, and
`dashboard` (port 5173). The API is healthy when
`curl http://localhost:8000/healthz` returns `{"status":"ok"}`.

---

## 2. Sign in, create a project, and mint an API key

1. Open `http://localhost:5173` and sign in with Clerk.
2. Click **New project**, give it a name, and confirm.
3. In the project's **API Keys** tab click **Create key**.
4. Copy the full key shown — it is displayed **exactly once** and never stored
   in plain text. Store it in your secrets manager or CI secrets now.

The key format is `adk_<prefix>_<secret>`. The prefix is shown in the key list;
the full value is only available at creation time.

---

## 3. Wire CI — send run results from GitHub Actions

Set two repository secrets in **Settings → Secrets → Actions**:

| Secret | Value |
|--------|-------|
| `AGENTDIFF_API_URL` | `http://your-api-host:8000` (or the public URL) |
| `AGENTDIFF_API_KEY` | The full key copied in step 2 |

Add a step to your workflow after the `agentdiff ci run` step:

```yaml
- name: AgentDiff CI gate
  env:
    AGENTDIFF_API_URL: ${{ secrets.AGENTDIFF_API_URL }}
    AGENTDIFF_API_KEY: ${{ secrets.AGENTDIFF_API_KEY }}
  run: |
    agentdiff ci run \
      --baseline origin/main \
      --samples 10 \
      --tier live
```

When both env vars are set, `agentdiff ci run` automatically uploads the run
payload to `POST /v1/runs` and the result appears in the dashboard. Omit the
env vars for hermetic (zero-cost) runs that don't upload.

---

## 4. Wire live monitoring — stream production trajectories

Use `LiveCollector` from the `collector` package to ship live agent trajectories
to `POST /v1/traffic`:

```python
from collector.live import LiveCollector

collector = LiveCollector(
    api_url="http://your-api-host:8000",
    api_key="adk_...",
    flush_every=20,          # auto-flush after this many trajectories
)

# In your agent's request handler or post-run hook:
collector.record(trajectory.model_dump(mode="json"))

# At shutdown (or end of a batch job):
collector.flush()
```

`LiveCollector` is fail-soft: any network error during flush is logged as a
warning and the batch is dropped. Your application is never interrupted.

### How drift detection works

The worker runs a drift check every 5 minutes over a **24-hour sliding window**
(configurable via `AGENTDIFF_DRIFT_WINDOW_MINUTES`). It compares the oldest
half of that window against the newest half using the same behavioral diff
engine as `agentdiff compare`. A drift run is only created when at least
`drift_min_samples` trajectories (default: 10) are available in each half;
below that threshold the check is skipped.

When a drift run finishes with verdict `warn` or `fail`, a Slack brief is posted
to the configured channel (see step 5). The brief shows what changed (agent
invocation rates, tool usage), the magnitude of each delta, and buttons linking
to the run detail in the dashboard.

---

## 5. Configure Slack notifications

In the dashboard, open your project and go to the **Slack** tab:

1. Paste your Slack bot token (`xoxb-...`). The token is encrypted at rest
   using your `AGENTDIFF_SECRET_ENCRYPTION_KEY` before being stored.
2. Paste the Slack channel ID (e.g. `C0123456789`).
3. Click **Save**.

Slack briefs are sent for every `warn` or `fail` verdict — both from CI runs
uploaded via `AGENTDIFF_API_KEY` and from automated drift detection. `pass`
verdicts are silent.

To configure via API directly:

```bash
curl -X PUT http://localhost:8000/v1/projects/<project_id>/slack \
  -H "Authorization: Bearer $CLERK_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_id":"C0123456789","bot_token":"xoxb-..."}'
```

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `401 Unauthorized` on `/v1/runs` or `/v1/traffic` | API key revoked or wrong | Regenerate key in dashboard → **API Keys**; update CI secret |
| Run stuck in `pending` | Worker or Redis is down | `docker compose ps`; restart `worker` and `redis` services |
| Drift check never fires / no drift runs appear | Not enough traffic to reach `drift_min_samples` (10), or window too wide | Lower `AGENTDIFF_DRIFT_WINDOW_MINUTES` or verify trajectory ingest via dashboard's live traffic view |
| `413 Request Entity Too Large` | Payload exceeds 50 MB body cap | Reduce batch size in `flush_every` or split trajectories |
| `429 Too Many Requests` | Rate limit exceeded (`/v1/runs`: 60/min; `/v1/traffic`: 600/min per project) | Back off and retry; increase limits via `AGENTDIFF_RATE_LIMIT_RUNS_PER_MINUTE` |
| Dashboard shows blank page / Clerk auth loop | `VITE_CLERK_PUBLISHABLE_KEY` not baked into the build | Rebuild the dashboard image: `docker compose build dashboard` |
| CORS errors in browser console | Dashboard origin not in `AGENTDIFF_CORS_ORIGINS` | Add dashboard URL: `AGENTDIFF_CORS_ORIGINS=http://localhost:5173,https://app.yourdomain.com` |
