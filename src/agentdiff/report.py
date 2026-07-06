"""Markdown report generation.

Sections:
  1. Header — refs, sample math, overall verdict.
  2. Side-by-side — traditional output eval vs AgentDiff behavioral verdict.
  3. Behavioral findings — invocation rates, tool usage, behavioral overlap.
  4. Causal attribution — likely changed file and diff hunk.
  5. Reproduction command.
"""
from typing import Any

from agentdiff.compare import ComparisonResult, TestCaseComparison
from agentdiff.output_eval import OutputEvalResult

_LABEL = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


def _esc_md_table_cell(text: str) -> str:
    """Escape `|` so free-text can't fracture a Markdown table row."""
    return text.replace("|", "\\|")


def _fmt_p(p_value: float | None, significant: bool) -> str:
    if p_value is None:
        return "n/a"
    marker = "*" if significant else ""
    if p_value < 0.001:
        return f"<0.001{marker}"
    return f"{p_value:.3f}{marker}"


def _fmt_p_adjusted(
    p_value: float | None,
    adjusted_p_value: float | None,
    significant: bool,
    low_power: bool,
) -> str:
    """Render adjusted p (BH-corrected) with the raw p alongside, plus a
    low-power marker (`!`) when the delta's per-side sample size fell below
    ``min_samples_warn`` — a `*` still marks significance at the adjusted p.
    """
    adjusted = _fmt_p(adjusted_p_value, significant)
    raw = _fmt_p(p_value, significant) if p_value != adjusted_p_value else None
    text = f"{adjusted} (raw {raw})" if raw is not None else adjusted
    return f"{text} !" if low_power else text


def render_report(
    comparison: ComparisonResult,
    output_evals: list[OutputEvalResult],
    meta: dict[str, Any],
    attribution=None,
) -> str:
    evals_by_id = {e.test_case_id: e for e in output_evals}
    lines: list[str] = []

    _header(lines, comparison, meta)
    _run_quality(lines, meta)
    _warnings_section(lines, comparison)
    _summary_table(lines, comparison, evals_by_id)
    _output_eval_details(lines, output_evals)
    _behavioral_findings(lines, comparison)
    _attribution_section(lines, attribution)
    _repro(lines, meta)

    return "\n".join(lines) + "\n"


def _header(lines: list[str], comparison: ComparisonResult, meta: dict[str, Any]) -> None:
    lines.append("# AgentDiff Report")
    lines.append("")
    lines.append(f"- **Generated:** {meta.get('timestamp', 'unknown')}")
    lines.append(f"- **Baseline:** `{meta.get('baseline_ref', 'main')}`")
    lines.append(f"- **Candidate:** `{meta.get('candidate_ref', 'working')}`")
    lines.append(f"- **Samples per case:** {meta.get('samples_per_case', '?')}")
    lines.append(f"- **Test cases:** {len(comparison.test_case_comparisons)}")
    lines.append(f"- **Overall verdict:** **{_LABEL[comparison.overall_verdict]}**")
    if meta.get("sqlite_store"):
        lines.append(f"- **SQLite store:** `{meta['sqlite_store']}`")
    lines.append("")


def _run_quality(lines: list[str], meta: dict[str, Any]) -> None:
    lines.append("## Run Quality")
    lines.append("")
    baseline_total = meta.get("baseline_trajectories")
    candidate_total = meta.get("candidate_trajectories")
    baseline_failed = meta.get("baseline_failed")
    candidate_failed = meta.get("candidate_failed")
    max_failure_rate = meta.get("max_failure_rate")
    lines.append("| Side | Trajectories | Failed | Failure budget |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| baseline | {baseline_total if baseline_total is not None else 'n/a'} "
        f"| {baseline_failed if baseline_failed is not None else 'n/a'} "
        f"| {_fmt_pct(max_failure_rate)} |"
    )
    lines.append(
        f"| candidate | {candidate_total if candidate_total is not None else 'n/a'} "
        f"| {candidate_failed if candidate_failed is not None else 'n/a'} "
        f"| {_fmt_pct(max_failure_rate)} |"
    )
    thresholds = meta.get("thresholds") or {}
    if thresholds:
        lines.append("")
        lines.append(
            "**Behavior thresholds:** "
            f"agent invocation warn/fail = "
            f"{thresholds.get('agent_invocation_rate_warn', 'n/a')}/"
            f"{thresholds.get('agent_invocation_rate_fail', 'n/a')}; "
            f"tool usage warn/fail = "
            f"{thresholds.get('tool_usage_avg_warn', 'n/a')}/"
            f"{thresholds.get('tool_usage_avg_fail', 'n/a')}; "
            f"latency (ms) warn/fail = "
            f"{thresholds.get('latency_ms_warn', 'n/a')}/"
            f"{thresholds.get('latency_ms_fail', 'n/a')}; "
            f"tokens warn/fail = "
            f"{thresholds.get('tokens_warn', 'n/a')}/"
            f"{thresholds.get('tokens_fail', 'n/a')}; "
            f"error rate warn/fail = "
            f"{thresholds.get('error_rate_warn', 'n/a')}/"
            f"{thresholds.get('error_rate_fail', 'n/a')}."
        )
    lines.append("")


def _warnings_section(lines: list[str], comparison: ComparisonResult) -> None:
    if not comparison.warnings:
        return
    lines.append("## Warnings")
    lines.append("")
    for w in comparison.warnings:
        lines.append(f"- {w}")
    lines.append("")


def _summary_table(
    lines: list[str],
    comparison: ComparisonResult,
    evals_by_id: dict[str, OutputEvalResult],
) -> None:
    lines.append("## Summary: Traditional Eval vs AgentDiff")
    lines.append("")
    lines.append(
        "The central claim: traditional output evaluation can report PASS while "
        "internal behavior has changed. Compare the two rightmost columns."
    )
    lines.append("")
    lines.append("| Test case | Traditional output eval | AgentDiff behavioral |")
    lines.append("|---|---|---|")
    for tcc in comparison.test_case_comparisons:
        ev = evals_by_id.get(tcc.test_case_id)
        trad = _LABEL[ev.verdict] if ev else "n/a"
        beh = _LABEL[tcc.overall_verdict]
        lines.append(f"| `{tcc.test_case_id}` | {trad} | {beh} |")
    lines.append("")


def _output_eval_details(lines: list[str], output_evals: list[OutputEvalResult]) -> None:
    lines.append("## Output Evaluation Details")
    lines.append("")
    if not output_evals:
        lines.append("_No output evaluations were produced._")
        lines.append("")
        return
    lines.append("| Test case | Kind | Semantic | Structural | Length | Judge | Notes | Skipped checks |")
    lines.append("|---|---|---:|---:|---:|---:|---|---|")
    for ev in output_evals:
        notes = _esc_md_table_cell("; ".join(ev.notes)) if ev.notes else ""
        skipped = (
            _esc_md_table_cell(
                "; ".join(f"{c['check']} ({c['reason']})" for c in ev.skipped_checks)
            )
            if ev.skipped_checks
            else ""
        )
        lines.append(
            f"| `{ev.test_case_id}` | {ev.output_kind} "
            f"| {_fmt_float(ev.semantic_similarity)} "
            f"| {_fmt_float(ev.structural_similarity)} "
            f"| {_fmt_float(ev.length_ratio)} "
            f"| {_fmt_float(ev.judge_score)} "
            f"| {notes} "
            f"| {skipped} |"
        )
    if any(ev.skipped_checks for ev in output_evals):
        lines.append("")
        lines.append(
            "_Some checks above were skipped (missing dependency, no LLM credential, "
            "or judge error) — a PASS/WARN/FAIL verdict may not reflect every signal. "
            "See the Skipped checks column._"
        )
    lines.append("")


def _behavioral_findings(lines: list[str], comparison: ComparisonResult) -> None:
    lines.append("## Behavioral Findings")
    lines.append("")
    for tcc in comparison.test_case_comparisons:
        _test_case_block(lines, tcc)


def _test_case_block(lines: list[str], tcc: TestCaseComparison) -> None:
    lines.append(f"### `{tcc.test_case_id}` — {_LABEL[tcc.overall_verdict]}")
    lines.append("")

    if tcc.agent_invocation_deltas:
        lines.append("**Agent invocation rates**")
        lines.append("")
        lines.append("| Agent | Baseline | Candidate | Delta | p-value (adjusted) | Verdict |")
        lines.append("|---|---|---|---|---|---|")
        for d in tcc.agent_invocation_deltas:
            lines.append(
                f"| {d.agent_name} "
                f"| {d.baseline_rate:.0%} ({d.baseline_count}/{d.baseline_total}) "
                f"| {d.candidate_rate:.0%} ({d.candidate_count}/{d.candidate_total}) "
                f"| {d.delta:+.0%} "
                f"| {_fmt_p_adjusted(d.p_value, d.adjusted_p_value, d.significant, d.low_power)} "
                f"| {_LABEL[d.verdict]} |"
            )
        lines.append("")

    if tcc.tool_usage_deltas:
        lines.append("**Tool usage (avg per trajectory)**")
        lines.append("")
        lines.append("| Tool | Baseline | Candidate | Delta | p-value (adjusted) | Verdict |")
        lines.append("|---|---|---|---|---|---|")
        for td in tcc.tool_usage_deltas:
            lines.append(
                f"| {td.tool_name} | {td.baseline_avg:.2f} | {td.candidate_avg:.2f} "
                f"| {td.delta:+.2f} "
                f"| {_fmt_p_adjusted(td.p_value, td.adjusted_p_value, td.significant, td.low_power)} "
                f"| {_LABEL[td.verdict]} |"
            )
        lines.append("")

    if tcc.run_metric_deltas:
        lines.append("**Runtime deltas**")
        lines.append("")
        lines.append("| Metric | Baseline | Candidate | Delta | p-value (adjusted) | Verdict |")
        lines.append("|---|---|---|---|---|---|")
        for rd in tcc.run_metric_deltas:
            lines.append(
                f"| {rd.metric} | {rd.baseline_mean:.2f} | {rd.candidate_mean:.2f} "
                f"| {rd.delta:+.2f} "
                f"| {_fmt_p_adjusted(rd.p_value, rd.adjusted_p_value, rd.significant, rd.low_power)} "
                f"| {_LABEL[rd.verdict]} |"
            )
        lines.append("")

    if tcc.behavioral_overlap is not None:
        lines.append(
            f"**Tool-set overlap (Jaccard):** {tcc.behavioral_overlap:.2f}"
        )
        lines.append("")

    if (
        not tcc.agent_invocation_deltas
        and not tcc.tool_usage_deltas
        and not tcc.run_metric_deltas
    ):
        lines.append("_No agents or tools observed for this test case._")
        lines.append("")


def _attribution_section(lines: list[str], attribution) -> None:
    lines.append("## Causal Attribution")
    lines.append("")
    lines.append(
        "Each non-passing behavioral delta is mapped to the specific changed file "
        "(and where possible, the diff hunk) that most likely caused it."
    )
    lines.append("")

    if attribution is None or not attribution.attributions:
        lines.append("_No behavioral deltas required attribution (all agents stable)._")
        lines.append("")
        return

    for ba in attribution.attributions:
        lines.append(f"### {ba.agent_name} — {ba.delta_summary} ({_LABEL.get(ba.verdict, ba.verdict.upper())})")
        lines.append("")
        if ba.primary is None:
            lines.append("_No code or prompt change matched this delta "
                         "(it may be non-determinism or an unobserved dependency)._")
            lines.append("")
            continue

        p = ba.primary
        low_conf_label = " (low-confidence heuristic)" if p.confidence == "low" else ""
        lines.append(
            f"- **Primary cause:** `{p.target_path}` "
            f"(rule: `{p.rule}`, confidence {p.weight:.0%} [{p.confidence}]){low_conf_label}"
        )
        lines.append(f"- {p.reason}")
        if ba.explanation:
            lines.append(f"- _{ba.explanation}_")
        if p.hunk:
            lines.append("")
            lines.append("```diff")
            lines.append(p.hunk.strip()[:1500])
            lines.append("```")
        if ba.alternatives:
            alts = ", ".join(
                f"`{a.target_path}` ({a.rule}, {a.weight:.0%})" for a in ba.alternatives
            )
            lines.append("")
            lines.append(f"Alternatives considered: {alts}")
        lines.append("")


def _repro(lines: list[str], meta: dict[str, Any]) -> None:
    lines.append("## Reproduction")
    lines.append("")
    lines.append("```bash")
    cmd = f"agentdiff compare --baseline {meta.get('baseline_arg') or meta.get('baseline_ref', 'auto')}"
    if meta.get("candidate_ref", "working") != "working":
        cmd += f" --candidate {meta.get('candidate_ref')}"
    if meta.get("samples_per_case"):
        cmd += f" --samples {meta.get('samples_per_case')}"
    lines.append(cmd)
    lines.append("```")


def _fmt_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"
