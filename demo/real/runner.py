"""AgentDiff runner for the demo real support-bot project.

Called by `agentdiff ci run` for each test case on each side. Invokes the
orchestrator and returns its result dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure agents/ is importable when this module is loaded from a git archive.
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.orchestrator import orchestrator  # noqa: E402 — needs sys.path set up first


def run(input: dict) -> dict:
    """Entry point for AgentDiff sampling."""
    return orchestrator(input)
