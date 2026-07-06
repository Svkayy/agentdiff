# Privacy Policy

_Last updated: 2026-07-05_

AgentDiff comes in two forms, and they have very different privacy footprints.
Read the part that applies to you.

---

## The short version

- **AgentDiff open source (the CLI)** runs entirely on your own machine or CI.
  We (the maintainers) receive **nothing** — no code, no LLM traffic, no
  telemetry. There is no account and no server involved.
- **AgentDiff hosted** (the multi-tenant dashboard at `app.agentdiff.ai`) is an
  account-based service. To do its job it stores the behavioral data you send
  it, including **captured LLM request/response traffic** (with redaction),
  your Slack connection, and your authentication identity.

If you never sign in to the hosted platform, this policy's hosted sections do
not apply to you.

---

## Open source CLI

The `agentdiff` Python package is MIT-licensed and self-hosted.

- **No telemetry.** The CLI does not phone home. It emits no usage analytics,
  crash reports, or "check for updates" pings.
- **Your data stays local.** Comparisons run against your code and your API
  keys. Captured LLM traffic, generated reports, and cached run artifacts are
  written to your local `.agentdiff/` directory (or wherever your CI stores
  them). They are never transmitted to us.
- **Your API keys are yours.** AgentDiff reads provider keys
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) from your environment to drive
  your agent during a comparison. Those requests go directly from your machine
  to your LLM provider. We are not in that path.

---

## Hosted platform

The hosted platform (`app.agentdiff.ai`) is optional and account-gated. When
you use it, we process the following.

### What we store, and why

- **Captured LLM traffic (with redaction).** The core of AgentDiff is a
  behavioral diff, which requires the actual request/response content of your
  agent's LLM calls. When you push runs to the hosted platform, that captured
  traffic is stored so we can compute and display the diff. **We apply
  redaction** to strip known secret-shaped values (API keys, bearer tokens) and
  configured PII patterns before persistence, but you should assume that
  prompt and completion text you send us is stored. Do not push runs
  containing data you are not permitted to store off your own infrastructure.
- **Slack connection.** If you connect Slack to receive briefs, we store the
  workspace/channel identifiers and an **OAuth access token**. That token is
  **encrypted at rest** and used only to post the briefs you asked for.
- **Authentication identity.** Sign-in is handled by **Clerk**, our
  authentication provider. Clerk stores your email and login credentials; we
  store the resulting user/organization identifiers to scope your data. See
  Clerk's own privacy policy for how they handle credentials.
- **Operational metadata.** Run timestamps, verdicts, project identifiers, and
  billing-relevant usage counts.

### What we do not do

- We do not sell your data.
- We do not use your captured LLM traffic to train models.
- We do not share your prompts or completions with other tenants — data is
  scoped per organization.

### Subprocessors

The hosted platform relies on third parties who process data on our behalf:
our authentication provider (**Clerk**), our cloud hosting and database
provider, and — only if you enable it — **Slack**. Each is bound to process
data only to provide their service.

### Retention and deletion

Hosted run data is retained while your account is active. You can request
deletion of your captured traffic and account data by contacting us (below);
we honor deletion requests for data under our control. Data that already left
our system — e.g. a Slack message we posted at your request — is governed by
that destination's own retention.

---

## Security

- Slack tokens are **encrypted at rest**.
- LLM traffic is **redacted** for known secrets/PII before storage, though
  redaction is best-effort and not a guarantee of completeness.
- Authentication is delegated to **Clerk**; we do not store your password.

For the full security posture, see the [Security](#/docs/security) doc.

---

## Contact

Questions, data requests, or security reports:
**security@agentdiff.dev** _(placeholder — a monitored inbox must be
provisioned before public launch)_.

This policy may change as the hosted platform matures. Material changes will be
reflected in the "Last updated" date above.
