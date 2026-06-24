#!/usr/bin/env bash
# Reproducible demo run. Copies this sample app into a throwaway git repo,
# commits the baseline, applies the candidate regression (disabling the
# fact-checker), runs `agentdiff compare`, and copies the real report into
# docs/demo/sample-report/. Requires a local Ollama with the AGENT_MODEL pulled.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
VENV="$REPO_ROOT/.venv/bin"
WORK="$(mktemp -d)"
SAMPLES="${SAMPLES:-8}"

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://localhost:11434/v1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-ollama}"
export AGENT_MODEL="${AGENT_MODEL:-llama3.1:8b}"
export AGENTDIFF_LLM_PROVIDER=openai
export AGENTDIFF_LLM_MODEL="${AGENTDIFF_LLM_MODEL:-llama3.1:8b}"

echo "==> Staging sample app in $WORK"
cp -R "$HERE/." "$WORK/"
rm -rf "$WORK/.agentdiff/reports"
cd "$WORK"
git init -q
git add -A
git commit -qm "baseline: research assistant with fact-checking enabled"
BASELINE_SHA="$(git rev-parse HEAD)"

echo "==> Applying candidate regression (disable the fact-checker)"
"$VENV/python" - <<'PY'
import pathlib
p = pathlib.Path("agents/fact_checker.py")
src = p.read_text()
marker = "    # AGENTDIFF_DEMO_MARKER (the candidate replaces this line to disable the step)"
assert marker in src, "demo marker not found in fact_checker.py"
src = src.replace(
    marker,
    '    return ""  # fact-checking disabled pending the latency fix (TODO: re-enable)',
)
p.write_text(src)
PY

echo "==> Running agentdiff compare (baseline ${BASELINE_SHA:0:7}, ${SAMPLES} samples/side)"
"$VENV/agentdiff" compare --baseline "$BASELINE_SHA" --samples "$SAMPLES" --project .

LATEST="$(ls -dt "$WORK"/.agentdiff/reports/*/ | head -1)"
DEST="$REPO_ROOT/docs/demo/sample-report"
echo "==> Copying report to $DEST"
rm -rf "$DEST"
mkdir -p "$DEST"
# *.jsonl is gitignored upstream; the sqlite already holds the trajectories.
cp "$LATEST/agentdiff.sqlite" "$LATEST/report.md" "$LATEST/metadata.json" "$DEST/"
[ -f "$LATEST/dashboard.html" ] && cp "$LATEST/dashboard.html" "$DEST/" || true

# Drop the absolute sqlite_store path (it points into this throwaway temp dir) so
# the committed report is portable and reads its OWN copied agentdiff.sqlite.
"$VENV/python" - "$DEST/metadata.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
data.pop("sqlite_store", None)
json.dump(data, open(path, "w"), indent=2)
PY

echo "==> Done. Verdict:"
grep -m1 "Overall verdict" "$DEST/report.md" || true
echo "Report: $DEST"
