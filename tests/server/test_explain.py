"""Tests for server/explain.py — LLM explanation wiring."""
from __future__ import annotations

import pytest

from server import explain as explain_mod


# ---------------------------------------------------------------------------
# Fake LLM client
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self, text: str = "Fake explanation."):
        self.calls: list[tuple[str, str]] = []
        self._text = text

    def complete(self, system: str, prompt: str, max_tokens: int = 200) -> str:
        self.calls.append((system, prompt))
        return self._text


class _RaisingClient:
    def complete(self, system: str, prompt: str, max_tokens: int = 200) -> str:
        raise RuntimeError("fake LLM error")


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _finding(verdict="fail", cause_path="agents/fact_checker.py"):
    return {
        "test_case_id": "tc1",
        "title": "Fact Checker invocation changed",
        "verdict": verdict,
        "metric": "invocation_rate",
        "impact_summary": "Fact Checker fired 100% on baseline and 0% on candidate (-100%).",
        "statistical_evidence": None,
        "cause_path": cause_path,
        "cause_rule": "code_change",
        "cause_hunk": "@@ -20,6 +20,7 @@\n+    return draft  # skip",
        "explanation": "Rule-based explanation.",
    }


class _RunCI:
    kind = "ci"


class _RunDrift:
    kind = "drift"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explanations_written_to_first_3_nonpass_findings(monkeypatch):
    """Fake client explanations are written into the first 3 non-pass findings."""
    fake = _FakeClient("LLM explanation.")

    def fake_make_client(api_key, model=None):
        return fake

    monkeypatch.setattr(explain_mod, "_make_client", fake_make_client)
    # Patch get_settings to return a settings-like object with a key set
    from server import config as cfg_mod

    class _FakeSettings:
        anthropic_api_key = "sk-ant-fake"
        llm_model = ""

    monkeypatch.setattr(cfg_mod, "get_settings", lambda: _FakeSettings())

    findings = [
        _finding(verdict="pass", cause_path=None),  # skipped — pass verdict
        _finding(verdict="fail"),
        _finding(verdict="fail"),
        _finding(verdict="fail"),
        _finding(verdict="fail"),  # 4th non-pass → over limit
    ]

    await explain_mod.explain_findings(findings, run=_RunCI())

    # First finding is pass → explanation stays unchanged (None / was not set)
    assert findings[0]["explanation"] is None or findings[0]["explanation"] == "Rule-based explanation."
    # findings[1..3] should have LLM explanation
    assert findings[1]["explanation"] == "LLM explanation."
    assert findings[2]["explanation"] == "LLM explanation."
    assert findings[3]["explanation"] == "LLM explanation."
    # findings[4] should NOT be updated (over the 3-finding cap)
    assert findings[4]["explanation"] == "Rule-based explanation."


@pytest.mark.asyncio
async def test_no_key_leaves_dicts_untouched(monkeypatch):
    """When no API key is configured, finding dicts are not touched."""
    from server import config as cfg_mod

    class _NoKey:
        anthropic_api_key = ""
        llm_model = ""

    monkeypatch.setattr(cfg_mod, "get_settings", lambda: _NoKey())

    findings = [_finding()]
    original_explanation = findings[0]["explanation"]

    await explain_mod.explain_findings(findings, run=_RunCI())

    assert findings[0]["explanation"] == original_explanation


@pytest.mark.asyncio
async def test_raising_client_swallowed_others_still_processed(monkeypatch):
    """If one finding's LLM call raises, the error is swallowed; others still run."""
    call_count = 0

    def fake_explain_one(finding_dict, client, *, is_drift):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("first call fails")
        finding_dict["explanation"] = "LLM explanation."

    monkeypatch.setattr(explain_mod, "_explain_one", fake_explain_one)

    def fake_make_client(api_key, model=None):
        return _RaisingClient()

    monkeypatch.setattr(explain_mod, "_make_client", fake_make_client)

    from server import config as cfg_mod

    class _HasKey:
        anthropic_api_key = "sk-ant-fake"
        llm_model = ""

    monkeypatch.setattr(cfg_mod, "get_settings", lambda: _HasKey())

    findings = [_finding(), _finding()]

    await explain_mod.explain_findings(findings, run=_RunCI())

    # Second finding should have been processed despite first failing
    assert findings[1]["explanation"] == "LLM explanation."


@pytest.mark.asyncio
async def test_failure_does_not_consume_cap(monkeypatch):
    """A raising _explain_one must NOT decrement the success cap.

    Scenario: 4 findings, first raises, next three succeed.
    All three successes should be written (cap=3 counts only successes).
    """
    call_count = 0
    success_count = 0

    def fake_explain_one(finding_dict, client, *, is_drift):
        nonlocal call_count, success_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("first call fails")
        finding_dict["explanation"] = "LLM explanation."
        success_count += 1

    monkeypatch.setattr(explain_mod, "_explain_one", fake_explain_one)

    def fake_make_client(api_key, model=None):
        return _RaisingClient()

    monkeypatch.setattr(explain_mod, "_make_client", fake_make_client)

    from server import config as cfg_mod

    class _HasKey:
        anthropic_api_key = "sk-ant-fake"
        llm_model = ""

    monkeypatch.setattr(cfg_mod, "get_settings", lambda: _HasKey())

    # 4 fail-verdict findings: first call raises, next three succeed
    findings = [_finding(), _finding(), _finding(), _finding()]

    await explain_mod.explain_findings(findings, run=_RunCI())

    # All three successful calls must have written their explanation
    assert findings[1]["explanation"] == "LLM explanation."
    assert findings[2]["explanation"] == "LLM explanation."
    assert findings[3]["explanation"] == "LLM explanation."
    # Cap was not exhausted by the failure → exactly 3 successes
    assert success_count == 3


@pytest.mark.asyncio
async def test_drift_narrative_path(monkeypatch):
    """Drift findings (no cause_path) are still explained with drift context."""
    fake = _FakeClient("Drift explanation.")

    def fake_make_client(api_key, model=None):
        return fake

    monkeypatch.setattr(explain_mod, "_make_client", fake_make_client)

    from server import config as cfg_mod

    class _HasKey:
        anthropic_api_key = "sk-ant-fake"
        llm_model = ""

    monkeypatch.setattr(cfg_mod, "get_settings", lambda: _HasKey())

    drift_finding = {
        "test_case_id": "live_traffic",
        "title": "Fact Checker invocation changed",
        "verdict": "warn",
        "metric": "invocation_rate",
        "impact_summary": "Fact Checker fired 80% on baseline and 40% on candidate (-40%).",
        "statistical_evidence": None,
        "cause_path": None,
        "cause_rule": None,
        "cause_hunk": None,
        "explanation": "No attributable code change in this window.",
    }

    await explain_mod.explain_findings([drift_finding], run=_RunDrift())

    assert drift_finding["explanation"] == "Drift explanation."
