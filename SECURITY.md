# Security Policy

## Supported versions

AgentDiff is pre-1.0 (`0.x`). Only the latest published `0.x` release is
supported with security fixes — there is no long-term-support branch yet.

| Version        | Supported          |
| -------------- | ------------------ |
| Latest `0.x`   | :white_check_mark: |
| Older `0.x`    | :x:                |

## Reporting a vulnerability

Please report suspected security vulnerabilities privately — **do not** open
a public GitHub issue.

Email **sandeepvinay.sk@gmail.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (a minimal repro is very helpful).
- The affected version(s) or commit.

You will receive an acknowledgment within **48 hours**. We'll follow up with
an assessment and, if confirmed, a plan and timeline for a fix. Please give
us a reasonable window to ship a patch before any public disclosure.

## Scope

This covers the `agentdiff` Python package (capture, comparison, attribution,
CLI, dashboard artifact) and the optional self-hosted platform (`server/`,
`frontend/`, `landing/`) in this repository. Notably relevant given
AgentDiff's job (capturing LLM/HTTP traffic):

- Secret/credential leakage through capture or redaction (see
  `docs/data-handling.md` for the current redaction guarantees).
- Cross-tenant data exposure in the hosted platform (auth, API-key scoping,
  audit log).
- Injection or deserialization issues in report generation or the dashboard.

## Disclosure credit

With your permission, we're happy to credit reporters in the release notes
once a fix ships.
