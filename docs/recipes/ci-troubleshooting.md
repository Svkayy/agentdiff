# CI Gate Troubleshooting Runbook

Every failure mode of `agentdiff ci run`, what it means, and the operational
response. The gate is designed so that no failure is silent: every error names
itself in the CI log, and the PR check remains the source of truth even when
delivery channels fail.

## Verdict semantics first

| Verdict | Meaning | Exit code (with `--fail-on fail`) |
|---------|---------|------------------------------------|
| PASS | No statistically significant behavioral change | 0 |
| WARN | Gate ran but is not fully meaningful (0 inputs, underpowered live sample) or minor shifts | 0 |
| FAIL | At least one significant behavioral regression | 1 |

`--fail-on warn` makes WARN block too; `--fail-on never` makes the gate
report-only.

## Failure modes

### "Hermetic tier requires --cassette"
The hermetic tier replays recorded HTTP responses; without a cassette there is
nothing to replay. Record one on a known-good ref:

```bash
agentdiff ci run --tier hermetic --cassette .agentdiff/cassettes/main.jsonl \
  --cassette-mode record --baseline origin/main
```

Commit the cassette. Re-record whenever the agent's provider traffic shape
changes (new tools, new prompts calling new endpoints).

### `CassetteMissError: no cassette recording for POST …`
The candidate code made a request the cassette has never seen — often this is
the regression itself (a new/changed call), but it can also mean the cassette
is stale. Response: re-record from the trusted baseline ref. If the miss only
happens on the candidate side, inspect the PR: it changed provider traffic.

**Security note:** always re-record cassettes from a trusted ref in CI, never
accept a cassette modified inside the PR under test — a poisoned cassette can
hide a regression.

### `CassetteSchemaError`
The cassette file is corrupt or from an incompatible schema version. Delete and
re-record.

### "Baseline/Candidate sampling failed: …"
The agent could not be executed at that ref. The error names the exception
class. Most common:
- **Import errors** — the baseline ref predates a module rename. Pin
  `--baseline` to a ref where the runner imports cleanly.
- **Timeouts / hangs** — check `sampling.workers` and consider lowering
  `samples_per_case` in CI.
- **Dependency drift** — pass `--install-deps` so each checkout installs its
  own lockfile (slower, correct across dependency changes).

### "AgentDiff ran on 0 inputs, so this gate is not meaningful" (WARN)
No test cases were found. The gate deliberately refuses to report a green PASS
on zero comparisons. Add test cases to `.agentdiff/test_cases.yaml` or generate
them from traffic: `agentdiff traffic discover --from prod-sample.jsonl`.

### "AgentDiff ran on N inputs, below the live-tier minimum of M" (WARN)
The live tier's statistical verdicts need enough samples to be meaningful.
Either add inputs, raise `--samples`, or lower `--min-live-samples` if you
accept reduced power.

### "slack delivery failed; PR check remains source of truth: …"
Slack delivery degraded — the verdict is unaffected. The error suffix is the
Slack error code:
- `invalid_auth` / `token_revoked` → rotate `SLACK_BOT_TOKEN`.
- `channel_not_found` / `not_in_channel` → invite the bot to the channel, or
  fix `AGENTDIFF_SLACK_CHANNEL` (use the channel ID, not the name).
- HTTP 429 / 5xx → transient; the client already retried twice with backoff.

### "github delivery failed …"
PR comment upsert failed (usually missing `pull-requests: write` permission in
the workflow). The check summary and artifacts still carry the full result.

### Reconstructing any verdict after the fact
Every run writes a self-contained artifact directory (uploaded by the Action as
`agentdiff-ci`):

```
summary.json          # the incident summary all renderers consume
comparison.json       # full statistical comparison
attribution.json      # ranked causes with hunks
slack_payload.json    # exactly what was (or would have been) posted
agentdiff-ci.md       # the PR check text
postmortem.md         # the postmortem draft
metadata.json         # refs, tier, samples, failure counts
```

If a developer disputes a verdict three weeks later, this directory is the
evidence.
