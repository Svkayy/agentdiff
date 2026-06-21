"""Ambient capture: record trajectories from your own code, no Runner.

    import agentdiff
    with agentdiff.record("before"):
        run_my_agent(...)        # however you normally call your agent

Each ``with`` block records one trajectory into
``.agentdiff/captures/<name>.jsonl``. The first use of a given name in a process
truncates that file (so re-running a script starts fresh); later uses of the same
name in the same process append (so you can loop for multiple samples).

Structure is auto-inferred on first use so captured agents get real names without
a separate ``agentdiff init``.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from agentdiff.capture.tracer import Tracer

# Capture files truncated once per (process, path) so repeated script runs start
# clean while in-process loops accumulate.
_RESET_SEEN: set[str] = set()


def captures_dir(project_root: str | Path) -> Path:
    return Path(project_root) / ".agentdiff" / "captures"


def _ensure_structure(root: Path) -> Path:
    """Make sure a structure.yaml exists so agents resolve to real names.

    Best-effort: if inference fails the Tracer simply falls back to raw function
    names. Returns the root to use as the Tracer's ``structure_root``.
    """
    from agentdiff.structure import structure_yaml
    from agentdiff.structure.ast_walker import walk_project
    from agentdiff.structure.heuristic_classifier import classify

    root = Path(root)
    if structure_yaml.load(root) is not None:
        return root
    try:
        structure_yaml.save(classify(walk_project(root)), root)
    except Exception as exc:  # noqa: BLE001 — inference is optional
        print(f"[agentdiff] structure inference skipped: {type(exc).__name__}: {exc}")
    return root


@contextmanager
def record(
    name: str,
    *,
    case: str = "capture",
    project_root: str | Path = ".",
) -> Iterator[Tracer]:
    """Record one trajectory of the wrapped agent code into a named capture.

    ``case`` ties trajectories together across captures: ``before`` and ``after``
    must share a case id to be compared (the default is fine for a single agent).
    """
    import agentdiff

    agentdiff.install()
    root = Path(project_root)
    structure_root = _ensure_structure(root)
    path = captures_dir(root) / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    key = str(path.resolve())
    if key not in _RESET_SEEN:
        path.write_text("", encoding="utf-8")
        _RESET_SEEN.add(key)

    with Tracer(
        test_case_id=case,
        version_tag="baseline",
        input_data={},
        output_path=path,
        structure_root=structure_root,
    ) as tracer:
        yield tracer
