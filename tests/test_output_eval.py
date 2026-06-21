"""Day 6: traditional output evaluator (with injected embeddings to avoid model load)."""
import json

import numpy as np

from agentdiff.output_eval import evaluate_output


def _fake_embed(mapping):
    """Return an embed_fn that maps known strings to fixed vectors."""
    def embed(texts):
        return np.asarray([mapping.get(t, np.zeros(3)) for t in texts], dtype=float)
    return embed


def test_identical_outputs_pass():
    embed = _fake_embed({"same text": np.array([1.0, 0.0, 0.0])})
    res = evaluate_output(
        "tc", ["same text"], ["same text"], embed_fn=embed
    )
    assert res.semantic_similarity == 1.0
    assert res.length_ratio == 1.0
    assert res.verdict == "pass"


def test_different_outputs_fail():
    embed = _fake_embed({
        "the sky is blue": np.array([1.0, 0.0, 0.0]),
        "bananas are yellow": np.array([0.0, 1.0, 0.0]),
    })
    res = evaluate_output(
        "tc", ["the sky is blue"], ["bananas are yellow"], embed_fn=embed
    )
    assert res.semantic_similarity == 0.0
    assert res.verdict == "fail"


def test_empty_outputs_pass_with_note():
    res = evaluate_output("tc", ["", ""], ["", ""])
    assert res.verdict == "pass"
    assert res.output_kind == "empty"
    assert any("no output" in n for n in res.notes)


# --- structured (dict/list) outputs ----------------------------------------

def test_structured_identical_pass():
    out = json.dumps({"decision": "accept", "score": 0.9, "tags": ["a", "b"]})
    res = evaluate_output("tc", [out], [out])
    assert res.output_kind == "structured"
    assert res.structural_similarity == 1.0
    assert res.changed_keys == []
    assert res.verdict == "pass"


def test_structured_all_values_changed_fail():
    b = json.dumps({"a": 1, "b": 2, "c": 3})
    c = json.dumps({"a": 9, "b": 8, "c": 7})
    res = evaluate_output("tc", [b], [c])
    assert res.output_kind == "structured"
    assert res.structural_similarity == 0.0
    assert set(res.changed_keys) == {"a", "b", "c"}
    assert res.verdict == "fail"


def test_structured_partial_change_warn():
    b = json.dumps({"a": 1, "b": 2, "c": 3, "d": 4, "e": 5})
    c = json.dumps({"a": 1, "b": 2, "c": 3, "d": 4, "e": 99})  # 1/5 changed → 0.8
    res = evaluate_output("tc", [b], [c])
    assert res.output_kind == "structured"
    assert abs(res.structural_similarity - 0.8) < 1e-9
    assert res.changed_keys == ["e"]
    assert res.verdict == "warn"


def test_structured_nested_and_lists():
    b = json.dumps({"user": {"name": "x"}, "items": [1, 2, 3]})
    c = json.dumps({"user": {"name": "y"}, "items": [1, 2, 3]})  # only user.name differs
    res = evaluate_output("tc", [b], [c])
    assert res.output_kind == "structured"
    assert res.changed_keys == ["user.name"]
    assert res.verdict == "warn"


def test_length_mismatch_drives_warn_or_fail():
    # Same direction semantically (cos=1) but candidate much shorter.
    embed = _fake_embed({
        "a much longer baseline answer here": np.array([1.0, 0.0, 0.0]),
        "short": np.array([1.0, 0.0, 0.0]),
    })
    res = evaluate_output(
        "tc",
        ["a much longer baseline answer here"],
        ["short"],
        embed_fn=embed,
    )
    assert res.semantic_similarity == 1.0
    assert res.length_ratio < 0.5
    assert res.verdict == "fail"


def test_judge_score_used_when_client_present():
    class FakeClient:
        def complete(self, system, prompt, max_tokens=8):
            return "5"

    embed = _fake_embed({"x": np.array([1.0, 0.0, 0.0])})
    res = evaluate_output(
        "tc", ["x"], ["x"], llm_client=FakeClient(), embed_fn=embed
    )
    assert res.judge_score == 5.0
    assert res.verdict == "pass"


def test_judge_low_score_fails():
    class FakeClient:
        def complete(self, system, prompt, max_tokens=8):
            return "1"

    embed = _fake_embed({"x": np.array([1.0, 0.0, 0.0])})
    res = evaluate_output(
        "tc", ["x"], ["x"], llm_client=FakeClient(), embed_fn=embed
    )
    assert res.judge_score == 1.0
    assert res.verdict == "fail"
