"""Regression tests for the code-review patches:

1. Tracer resolves inferred_agent to the structure.yaml display name (overriding
   the raw function name the shims pre-fill).
2. The requests adapter exposes `.url` so URL-keyed parsers work under `requests`.
3. providers.yaml custom patterns are loaded into the registry.
"""
import json
from uuid import uuid4

from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent, StackFrame
from agentdiff.capture.http import provider_registry
from agentdiff.capture.http.canonical import build_canonical_from_http
from agentdiff.capture.http.requests_shim import _RequestsRequestAdapter
from agentdiff.capture.tracer import Tracer
from agentdiff.storage import load_trajectory_set
from agentdiff.structure import structure_yaml
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc


# --- 1. inferred_agent display-name resolution -----------------------------

def _user_frame(function: str) -> StackFrame:
    return StackFrame(
        file="a.py", function=function, line=1,
        is_user_code=True, is_framework_internal=False,
        is_agentdiff_internal=False, is_sdk_internal=False,
    )


def test_tracer_resolves_display_name_over_raw_function(tmp_path):
    # structure.yaml gives the agent a display name distinct from its function.
    structure_yaml.save(
        StructureDoc(agents=[
            AgentEntry(name="RouterAgent", function="route_query", file="a.py", line=1)
        ]),
        tmp_path,
    )

    out = tmp_path / "out.jsonl"
    with Tracer("tc", "baseline", {}, output_path=out, structure_root=tmp_path) as tracer:
        event = LLMRequestEvent(
            call_id=uuid4(),
            canonical=CanonicalLLMCall(provider="anthropic"),
            captured_by="sdk_shim",
            callsite=CallSite(file="a.py", function="route_query", line=1),
            call_stack=[_user_frame("route_query")],
            inferred_agent="route_query",  # raw value the shim pre-fills
        )
        tracer.record(event)
        # Overridden to the display name even though it was already non-None.
        assert event.inferred_agent == "RouterAgent"

    # And it survives serialization so compare/manifest see the display name.
    ts = load_trajectory_set(out, "baseline")
    assert ts.trajectories[0].agents_invoked() == ["RouterAgent"]


def test_tracer_keeps_raw_fallback_when_no_match(tmp_path):
    structure_yaml.save(
        StructureDoc(agents=[
            AgentEntry(name="RouterAgent", function="route_query", file="a.py", line=1)
        ]),
        tmp_path,
    )
    out = tmp_path / "out.jsonl"
    with Tracer("tc", "baseline", {}, output_path=out, structure_root=tmp_path) as tracer:
        event = LLMRequestEvent(
            call_id=uuid4(),
            canonical=CanonicalLLMCall(provider="anthropic"),
            captured_by="sdk_shim",
            callsite=CallSite(file="a.py", function="some_helper", line=1),
            call_stack=[_user_frame("some_helper")],
            inferred_agent="some_helper",
        )
        tracer.record(event)
        # No agent maps to 'some_helper' → the shim's raw value is preserved.
        assert event.inferred_agent == "some_helper"


# --- 2. requests adapter exposes .url --------------------------------------

class _FakePrepared:
    def __init__(self, url, body):
        self.url = url
        self.body = body


def test_requests_adapter_exposes_url_for_gemini():
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent"
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}).encode()
    adapter = _RequestsRequestAdapter(_FakePrepared(url, body))

    assert adapter.url == url
    canonical = build_canonical_from_http("gemini", adapter, response=None)
    assert canonical.provider == "gemini"
    assert canonical.model == "gemini-1.5-pro"  # parsed from the URL


# --- 3. providers.yaml custom patterns -------------------------------------

def test_load_custom_providers(tmp_path):
    ad = tmp_path / ".agentdiff"
    ad.mkdir()
    (ad / "providers.yaml").write_text(
        "providers:\n"
        "  - name: acme_llm_test\n"
        '    url_pattern: "^https://api\\\\.acme-test\\\\.com/v1/generate"\n'
    )
    added = provider_registry.load_custom_providers(tmp_path)
    assert added == 1
    assert provider_registry.match_provider("https://api.acme-test.com/v1/generate") == "acme_llm_test"
    # Idempotent: loading again registers nothing new.
    assert provider_registry.load_custom_providers(tmp_path) == 0


def test_load_custom_providers_missing_file(tmp_path):
    assert provider_registry.load_custom_providers(tmp_path) == 0
