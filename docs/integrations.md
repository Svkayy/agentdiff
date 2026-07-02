# AgentDiff Integrations

AgentDiff CI always writes local artifacts first. Integrations are delivery
channels layered on top, so Slack, GitHub, or webhook failures never hide the
underlying verdict.

## Slack

Set a bot token and channel ID:

```bash
export SLACK_BOT_TOKEN=xoxb-...
export AGENTDIFF_SLACK_CHANNEL=C0123456789
agentdiff ci run --tier live --baseline origin/main --candidate working
```

The Slack brief is PM-friendly: impact first, likely cause second, report link
third when `--detail-url` is provided.

## GitHub PR Comments

When running inside GitHub Actions, AgentDiff can post or update one PR comment:

```yaml
permissions:
  contents: read
  pull-requests: write

steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0
  - uses: ./path/to/agentdiff
    with:
      tier: live
      baseline: origin/main
```

The composite Action reads `github.token`, `github.repository`, and
`github.event_path` automatically. Set `github-pr-comment: "false"` to disable
comment delivery.

## Security: fork PRs and secrets

The classic GitHub Actions vulnerability is running fork-PR code in a workflow
that has secret access (`pull_request_target` + checkout of the PR head). Since
AgentDiff *executes your agent code* on both refs, treat it like any other CI
job that runs untrusted code:

- **Use the `pull_request` trigger, never `pull_request_target`.** With
  `pull_request`, forked PRs get no secrets by default — GitHub enforces this.
- **The hermetic tier needs zero secrets.** No provider keys, no Slack token.
  This is the safe default for fork PRs: the gate still catches agent-invocation,
  tool-usage, and routing regressions from cassette replay alone.
- **Gate Slack + live tier to same-repo PRs.** Fork PRs skip delivery; the
  verdict still lands in the PR check and artifacts:

```yaml
- uses: your-org/agentdiff-action@v1
  with:
    tier: hermetic
    cassette: .agentdiff/cassettes/main.jsonl
- uses: your-org/agentdiff-action@v1
  if: github.event.pull_request.head.repo.full_name == github.repository
  env:
    SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
  with:
    tier: live
    slack-channel: C0123456789
```

- **Never echo tokens.** Pass them only via `secrets.*` → `env`. AgentDiff
  never logs token values; delivery errors log the Slack error code, not the
  credential.

## Generic Webhook

Use the webhook for tools that accept JSON or can be routed through Zapier,
Make, incident.io, Rootly, Linear automation, Jira automation, or PagerDuty
Event Orchestration:

```bash
export AGENTDIFF_WEBHOOK_URL=https://example.com/agentdiff
agentdiff ci run --tier live --baseline origin/main --candidate working
```

Payload shape:

```json
{
  "source": "agentdiff",
  "verdict": "fail",
  "warnings": [],
  "findings": [],
  "artifacts": {
    "summary_path": ".agentdiff/ci/.../agentdiff-ci.md",
    "postmortem_path": ".agentdiff/ci/.../postmortem.md",
    "json_path": ".agentdiff/ci/.../summary.json"
  }
}
```
