"""Traditional output evaluator.

Compares baseline vs candidate final outputs with three metrics and combines
them into a PASS/WARN/FAIL verdict:
  - semantic similarity (sentence-transformers cosine, optional extra)
  - LLM judge (1-5 equivalence score, optional)
  - length consistency (shorter/longer ratio)

This is the "traditional eval" half of the report's headline side-by-side row.
The point of AgentDiff is that this can say PASS while behavior has drifted.
"""
import json
from typing import Any, Callable, Literal

import numpy as np
from pydantic import BaseModel, Field

from agentdiff.llm_client import LLMClient

Verdict = Literal["pass", "warn", "fail"]
OutputKind = Literal["text", "structured", "empty"]

_SEM_FAIL = 0.70
_SEM_WARN = 0.85
_LEN_FAIL = 0.50
_LEN_WARN = 0.80
_STRUCT_FAIL = 0.70
_STRUCT_WARN = 0.90

_MISSING = object()

_JUDGE_SYSTEM = (
    "You compare two AI agent outputs (a baseline and a candidate) and rate how "
    "equivalent they are in meaning and usefulness on a 1-5 scale, where 5 means "
    "fully equivalent and 1 means completely different. Respond with ONLY the integer."
)

# Lazily-loaded singleton embedding model.
_MODEL = None


class OutputEvalResult(BaseModel):
    test_case_id: str
    output_kind: OutputKind = "text"
    semantic_similarity: float | None = None  # text outputs
    structural_similarity: float | None = None  # structured (dict/list) outputs
    changed_keys: list[str] = Field(default_factory=list)  # structured: differing paths
    judge_score: float | None = None  # 1-5
    length_ratio: float | None = None
    verdict: Verdict = "pass"
    notes: list[str] = []


def _get_model():
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "semantic similarity requires the optional embeddings extra: "
                "install `agentdiff[embeddings]`"
            ) from e
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL


def _default_embed(texts: list[str]) -> np.ndarray:
    return np.asarray(_get_model().encode(texts))


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _representative(outputs: list[str]) -> str:
    """Pick a representative output: the first non-empty, else ''."""
    for o in outputs:
        if o and o.strip():
            return o
    return ""


def _as_structured(text: str) -> Any:
    """Parse text as JSON and return it only if it's a dict or list, else None.

    Runner dict/list returns are JSON-serialized into final_output by the sampler,
    so this recovers structured outputs for a real structural diff.
    """
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, (dict, list)) else None


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts/lists into {dotted_path: leaf_value}."""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix or "<root>"] = obj
    return out


def _structural_compare(a: Any, b: Any) -> tuple[float, list[str]]:
    """Return (similarity 0-1, sorted list of differing leaf paths).

    Similarity = matching leaves / union of leaf paths. A path counts as matching
    only if present on both sides with equal values.
    """
    fa, fb = _flatten(a), _flatten(b)
    all_paths = set(fa) | set(fb)
    if not all_paths:
        return 1.0, []
    matching = sum(
        1 for p in all_paths if p in fa and p in fb and fa[p] == fb[p]
    )
    changed = sorted(
        p for p in all_paths if fa.get(p, _MISSING) != fb.get(p, _MISSING)
    )
    return matching / len(all_paths), changed


def _structural_verdict(similarity: float) -> tuple[Verdict, list[str]]:
    if similarity < _STRUCT_FAIL:
        return "fail", [f"structural similarity {similarity:.2f} below {_STRUCT_FAIL}"]
    if similarity < _STRUCT_WARN:
        return "warn", [f"structural similarity {similarity:.2f} below {_STRUCT_WARN}"]
    return "pass", []


def _length_ratio(a: str, b: str) -> float:
    la, lb = len(a), len(b)
    if la == 0 and lb == 0:
        return 1.0
    hi = max(la, lb)
    if hi == 0:
        return 1.0
    return min(la, lb) / hi


def _combine_verdict(
    semantic: float | None, judge: float | None, length: float | None
) -> tuple[Verdict, list[str]]:
    notes: list[str] = []
    verdicts: list[Verdict] = []

    if semantic is not None:
        if semantic < _SEM_FAIL:
            verdicts.append("fail")
            notes.append(f"semantic similarity {semantic:.2f} below {_SEM_FAIL}")
        elif semantic < _SEM_WARN:
            verdicts.append("warn")
            notes.append(f"semantic similarity {semantic:.2f} below {_SEM_WARN}")
        else:
            verdicts.append("pass")

    if judge is not None:
        if judge <= 2:
            verdicts.append("fail")
            notes.append(f"judge equivalence score {judge:.1f}/5")
        elif judge <= 3.5:
            verdicts.append("warn")
            notes.append(f"judge equivalence score {judge:.1f}/5")
        else:
            verdicts.append("pass")

    if length is not None:
        if length < _LEN_FAIL:
            verdicts.append("fail")
            notes.append(f"length ratio {length:.2f} below {_LEN_FAIL}")
        elif length < _LEN_WARN:
            verdicts.append("warn")
            notes.append(f"length ratio {length:.2f} below {_LEN_WARN}")
        else:
            verdicts.append("pass")

    severity = {"pass": 0, "warn": 1, "fail": 2}
    worst: Verdict = "pass"
    for v in verdicts:
        if severity[v] > severity[worst]:
            worst = v
    return worst, notes


def evaluate_output(
    test_case_id: str,
    baseline_outputs: list[str],
    candidate_outputs: list[str],
    llm_client: LLMClient | None = None,
    embed_fn: Callable[[list[str]], np.ndarray] | None = None,
) -> OutputEvalResult:
    """Evaluate output equivalence for one test case.

    ``embed_fn`` lets callers/tests inject embeddings instead of loading the
    sentence-transformers model. ``llm_client`` enables the optional judge.
    """
    b_repr = _representative(baseline_outputs)
    c_repr = _representative(candidate_outputs)

    # Nothing to compare (purely side-effecting agents) — behavioral findings only.
    if not b_repr and not c_repr:
        return OutputEvalResult(
            test_case_id=test_case_id,
            output_kind="empty",
            verdict="pass",
            notes=["no output to compare"],
        )

    # Structured outputs (Runner returned a dict/list) get a real structural diff
    # rather than text semantic similarity.
    b_struct, c_struct = _as_structured(b_repr), _as_structured(c_repr)
    if b_struct is not None and c_struct is not None:
        similarity, changed = _structural_compare(b_struct, c_struct)
        verdict, notes = _structural_verdict(similarity)
        judge: float | None = None
        if llm_client is not None:
            judge = _run_judge(llm_client, b_repr, c_repr)
            if judge is not None:
                jv, jnotes = _combine_verdict(None, judge, None)
                notes += jnotes
                verdict = max([verdict, jv], key=lambda v: {"pass": 0, "warn": 1, "fail": 2}[v])
        if changed:
            notes.append(f"{len(changed)} differing key(s)")
        return OutputEvalResult(
            test_case_id=test_case_id,
            output_kind="structured",
            structural_similarity=similarity,
            changed_keys=changed[:50],
            judge_score=judge,
            verdict=verdict,
            notes=notes,
        )

    embed = embed_fn or _default_embed
    semantic: float | None = None
    try:
        vecs = embed([b_repr, c_repr])
        semantic = _cosine(np.asarray(vecs[0]), np.asarray(vecs[1]))
    except Exception as e:  # noqa: BLE001
        print(f"[agentdiff] semantic similarity failed: {type(e).__name__}: {e}")

    length = _length_ratio(b_repr, c_repr)

    judge: float | None = None
    if llm_client is not None:
        judge = _run_judge(llm_client, b_repr, c_repr)

    verdict, notes = _combine_verdict(semantic, judge, length)
    return OutputEvalResult(
        test_case_id=test_case_id,
        semantic_similarity=semantic,
        judge_score=judge,
        length_ratio=length,
        verdict=verdict,
        notes=notes,
    )


def _run_judge(client: LLMClient, baseline: str, candidate: str) -> float | None:
    prompt = (
        f"BASELINE OUTPUT:\n{baseline}\n\n"
        f"CANDIDATE OUTPUT:\n{candidate}\n\n"
        "How equivalent are these (1-5)? Respond with only the integer."
    )
    raw = client.complete(_JUDGE_SYSTEM, prompt, max_tokens=8).strip()
    for token in raw.replace("/", " ").split():
        try:
            val = float(token)
            if 1 <= val <= 5:
                return val
        except ValueError:
            continue
    return None
