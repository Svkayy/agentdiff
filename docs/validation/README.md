# Validation Deployments

v0 ships when AgentDiff has been deployed end-to-end on **at least two external
Python codebases** — one using an SDK with a registered shim (Anthropic/OpenAI),
one going through the HTTP-only capture path — with a saved report from each here
as evidence. At least one deployment should exercise a non-request-response
Runner recipe.

_Placeholders — replace with real saved reports:_

- `codebase_a_report.md` — external deployment #1 (registered SDK shim path).
- `codebase_b_report.md` — external deployment #2 (HTTP-only capture path).

## How to produce one

```bash
cd <external-project>
pip install -e /path/to/agentdiff
agentdiff init
# adapt a recipe from docs/recipes/ into .agentdiff/config.yaml + test_cases.yaml
agentdiff compare --baseline <ref>
cp .agentdiff/reports/<timestamp>/report.md \
   /path/to/agentdiff/docs/validation/codebase_a_report.md
```
