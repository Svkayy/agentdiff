"""Collect per-file unified diffs between baseline and candidate."""
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class GitRange:
    """A deploy/PR attribution boundary."""

    base_ref: str
    head_ref: str | None = None

    @property
    def candidate_arg(self) -> str:
        return self.head_ref or "working"


def collect_git_diff(
    baseline_ref: str,
    candidate_ref_or_working: str,
    repo_root: Path,
) -> dict[str, str]:
    """Return ``{file_path: unified_diff_text}`` for changed files.

    ``candidate_ref_or_working == "working"`` diffs the working tree against the
    baseline ref; otherwise diffs two refs.
    """
    repo_root = Path(repo_root)
    if candidate_ref_or_working == "working":
        names_cmd = ["git", "diff", "--name-only", baseline_ref]
        diff_cmd = ["git", "diff", baseline_ref, "--"]
    else:
        names_cmd = ["git", "diff", "--name-only", baseline_ref, candidate_ref_or_working]
        diff_cmd = ["git", "diff", baseline_ref, candidate_ref_or_working, "--"]

    try:
        names = subprocess.check_output(
            names_cmd, cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        ).splitlines()
    except subprocess.CalledProcessError:
        return {}

    out: dict[str, str] = {}
    for name in names:
        name = name.strip()
        if not name:
            continue
        try:
            diff_text = subprocess.check_output(
                diff_cmd + [name], cwd=repo_root, text=True, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            continue
        if diff_text.strip():
            out[name] = diff_text
    return out
