#!/usr/bin/env python3
"""Genuine AgentDiff demo: real capture → real compare → real attribution.

Creates a throwaway git repo with a support-bot pipeline (orchestrator →
retriever → fact_checker → summarizer), commits a BASELINE where fact_checker
makes a real LLM call, then commits a CANDIDATE that introduces a behavioral
delta (code or prompt change), and runs `agentdiff ci run --tier live` against
the real local stack.

The demo requires:
  - Docker stack up:  docker compose up -d
  - Venv active:      source .venv/bin/activate
  - API credentials exported:
        export AGENTDIFF_API_URL=http://localhost:8000
        export AGENTDIFF_API_KEY=adk_...

Usage:
    python demo/run_real_demo.py              # code-change scenario (default)
    python demo/run_real_demo.py --scenario prompt  # prompt-change scenario
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEMO_REAL = Path(__file__).parent / "real"


def _run(args: list[str], cwd: Path, env: dict | None = None) -> None:
    full_env = {**os.environ, **(env or {})}
    result = subprocess.run(args, cwd=cwd, env=full_env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[demo] command failed: {' '.join(args)}")
        print(result.stdout[-2000:] if result.stdout else "")
        print(result.stderr[-2000:] if result.stderr else "")
        sys.exit(1)
    return result


def _git(args: list[str], cwd: Path) -> None:
    _run(["git", *args], cwd=cwd)


def _setup_git_repo(tmp: Path) -> Path:
    """Copy demo/real into a fresh git repo and commit as BASELINE."""
    repo = tmp / "support-bot"
    shutil.copytree(DEMO_REAL, repo)

    _git(["init"], repo)
    _git(["config", "user.email", "demo@agentdiff.ai"], repo)
    _git(["config", "user.name", "AgentDiff Demo"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "baseline: fact_checker enabled"], repo)

    return repo


def _apply_code_candidate(repo: Path) -> str:
    """Add candidate commit: early return in fact_checker.py (code change)."""
    fc = repo / "agents" / "fact_checker.py"
    original = fc.read_text(encoding="utf-8")

    # Insert an early return just before the prompt load — this is the REAL
    # behavioral change: fact_checker returns context without calling the LLM.
    patched = original.replace(
        "    raw_prompt = _load_prompt()",
        "    return context  # candidate: skip fact-checking for latency\n\n    raw_prompt = _load_prompt()",
    )
    assert patched != original, "patch didn't apply — check fact_checker.py"
    fc.write_text(patched, encoding="utf-8")

    _git(["add", "agents/fact_checker.py"], repo)
    _git(["commit", "-m", "candidate: skip fact_checker for latency (early return)"], repo)

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    )
    return result.stdout.strip()


def _apply_prompt_candidate(repo: Path) -> str:
    """Add candidate commit: remove [FACT_CHECK_ENABLED] from prompt file."""
    prompt_file = repo / "prompts" / "fact_checker.txt"
    original = prompt_file.read_text(encoding="utf-8")

    # Remove the activation marker line — fact_checker.py gates on this string,
    # so removing it causes the LLM call to be skipped. The rest of the prompt
    # text stays intact, so the baseline's observed system prompt still matches
    # this file and attribution names it via direct_prompt_change.
    patched = original.replace("[FACT_CHECK_ENABLED]\n", "")
    assert patched != original, "patch didn't apply — check fact_checker.txt"
    prompt_file.write_text(patched, encoding="utf-8")

    _git(["add", "prompts/fact_checker.txt"], repo)
    _git(["commit", "-m", "candidate: updated fact_checker prompt (marker removed)"], repo)

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentDiff genuine demo")
    parser.add_argument(
        "--scenario",
        choices=["code", "prompt"],
        default="code",
        help="code: early return in fact_checker.py; prompt: remove marker from prompt file",
    )
    args = parser.parse_args()

    api_url = os.environ.get("AGENTDIFF_API_URL")
    api_key = os.environ.get("AGENTDIFF_API_KEY")
    if not api_url or not api_key:
        print(
            "[demo] ERROR: AGENTDIFF_API_URL and AGENTDIFF_API_KEY must be set.\n"
            "       Create a project in the dashboard, mint an API key, then:\n"
            "         export AGENTDIFF_API_URL=http://localhost:8000\n"
            "         export AGENTDIFF_API_KEY=adk_..."
        )
        sys.exit(1)

    # Start the local mock provider
    sys.path.insert(0, str(Path(__file__).parent))
    from mock_provider import start_mock_provider, stop_mock_provider

    port = start_mock_provider()
    provider_url = f"http://127.0.0.1:{port}"
    print(f"[demo] Mock Anthropic provider started on {provider_url}")

    with tempfile.TemporaryDirectory(prefix="agentdiff-demo-") as tmp:
        tmp_path = Path(tmp)
        print("[demo] Setting up throwaway git repo …")
        repo = _setup_git_repo(tmp_path)

        # Baseline SHA
        baseline_result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        )
        baseline_sha = baseline_result.stdout.strip()
        print(f"[demo] Baseline commit: {baseline_sha[:7]}")

        # Apply candidate
        print(f"[demo] Applying '{args.scenario}' candidate …")
        if args.scenario == "code":
            candidate_sha = _apply_code_candidate(repo)
        else:
            candidate_sha = _apply_prompt_candidate(repo)
        print(f"[demo] Candidate commit: {candidate_sha[:7]}")

        # Find the agentdiff CLI in the venv
        agentdiff_bin = shutil.which("agentdiff")
        if agentdiff_bin is None:
            # Try the venv in the repo root
            venv_bin = REPO_ROOT / ".venv" / "bin" / "agentdiff"
            if venv_bin.exists():
                agentdiff_bin = str(venv_bin)
            else:
                print("[demo] ERROR: agentdiff CLI not found. Is the venv active?")
                sys.exit(1)

        output_dir = tmp_path / "ci-output"

        print("[demo] Running: agentdiff ci run …")
        cmd = [
            agentdiff_bin,
            "ci", "run",
            "--project", str(repo),
            "--baseline", baseline_sha,
            "--candidate", candidate_sha,
            "--tier", "live",
            "--fail-on", "never",
            "--output", str(output_dir),
        ]

        # Include repo root in PYTHONPATH so 'collector' package is importable
        # from the subprocess (it's in the editable install MAPPING for agentdiff/server
        # but not for collector).
        existing_pythonpath = os.environ.get("PYTHONPATH", "")
        repo_root_str = str(REPO_ROOT)
        new_pythonpath = f"{repo_root_str}:{existing_pythonpath}" if existing_pythonpath else repo_root_str

        env = {
            "AGENTDIFF_API_URL": api_url,
            "AGENTDIFF_API_KEY": api_key,
            "AGENTDIFF_DEMO_PROVIDER_URL": provider_url,
            # Make the anthropic SDK point to our mock
            "ANTHROPIC_BASE_URL": provider_url,
            "PYTHONPATH": new_pythonpath,
        }

        result = subprocess.run(
            cmd,
            cwd=repo,
            env={**os.environ, **env},
            capture_output=False,  # stream output directly
        )

        stop_mock_provider()

        if result.returncode not in (0, 1):
            print(f"[demo] agentdiff ci run exited with code {result.returncode}")
            sys.exit(result.returncode)

        # Read summary
        summary_path = output_dir / "summary.json"
        if summary_path.exists():
            import json
            summary = json.loads(summary_path.read_text())
            print(f"\n[demo] Verdict: {summary.get('verdict', '?').upper()}")
            for f in summary.get("findings", []):
                print(f"  Finding: {f.get('title')} [{f.get('verdict')}]")
                if f.get("cause_path"):
                    print(f"    Cause: {f.get('cause_path')}")
                if f.get("explanation"):
                    print(f"    Explanation: {f.get('explanation')[:120]}")

        print("\n[demo] Run uploaded to hosted API.")
        print("[demo] Open the dashboard → project → Runs to see the result.")
        print(f"[demo] Scenario: '{args.scenario}'")


if __name__ == "__main__":
    main()
