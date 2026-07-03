import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import click
from pydantic import ValidationError
from rich.console import Console

from agentdiff import compare as compare_engine, sampling, storage
from agentdiff.attribution.git_diff import GitRange
from agentdiff.cli.compare import (
    _failed_count,
    _load_test_cases,
    _validate_trajectory_quality,
    git_validation_error,
    resolve_baseline,
)
from agentdiff.config import load_config, thresholds_for_compare
from agentdiff.incident.findings import IncidentContext, build_incident_summary
from agentdiff.incident.github import GitHubClient, infer_pr_number
from agentdiff.incident.renderers import (
    render_postmortem,
    render_pr_check,
    render_slack_blocks,
    render_slack_payload,
)
from agentdiff.incident.slack import SlackClient
from agentdiff.incident.webhook import WebhookClient
from agentdiff.structure import structure_yaml

console = Console()

FailOn = Literal["fail", "warn", "never"]
Tier = Literal["hermetic", "live"]

_SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


@click.group("ci")
def ci_cmd() -> None:
    """CI gate and incident-brief commands."""


@ci_cmd.command("run")
@click.option(
    "--baseline",
    default="auto",
    help="Git ref for the good baseline, or 'auto' to infer one.",
)
@click.option("--candidate", default="working", help="Git ref, or 'working' for the candidate.")
@click.option("--project", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--test-cases", "test_cases_path", default=None, help="Path to test_cases.yaml.")
@click.option("--samples", type=int, default=None, help="Samples per test case per side.")
@click.option("--workers", type=int, default=None, help="Concurrent local sampling workers.")
@click.option("--output", "output_dir", default=None, help="CI artifact output directory.")
@click.option(
    "--tier",
    type=click.Choice(["hermetic", "live"]),
    default="hermetic",
    show_default=True,
    help="Hermetic replays a cassette; live makes real provider calls.",
)
@click.option("--cassette", "cassette_path", default=None, help="HTTP cassette path for hermetic replay.")
@click.option(
    "--cassette-mode",
    type=click.Choice(["record", "replay"]),
    default="replay",
    show_default=True,
    help="Cassette mode when --cassette is provided.",
)
@click.option(
    "--fail-on",
    type=click.Choice(["fail", "warn", "never"]),
    default="fail",
    show_default=True,
    help="Which AgentDiff verdict should fail the CI command.",
)
@click.option("--slack-token", envvar="SLACK_BOT_TOKEN", default=None, help="Slack bot token.")
@click.option("--slack-channel", envvar="AGENTDIFF_SLACK_CHANNEL", default=None, help="Slack channel ID.")
@click.option("--webhook-url", envvar="AGENTDIFF_WEBHOOK_URL", default=None, help="Generic JSON webhook URL.")
@click.option("--github-token", envvar="GITHUB_TOKEN", default=None, help="GitHub token for PR comments.")
@click.option("--github-repository", envvar="GITHUB_REPOSITORY", default=None, help="owner/repo for PR comments.")
@click.option("--github-pr-number", envvar="AGENTDIFF_GITHUB_PR_NUMBER", type=int, default=None)
@click.option("--github-event-path", envvar="GITHUB_EVENT_PATH", default=None)
@click.option("--detail-url", default=None, help="URL linked from Slack brief.")
@click.option("--min-live-samples", type=int, default=5, show_default=True)
@click.option(
    "--install-deps/--no-install-deps",
    default=None,
    help="Install dependencies before sampling git checkouts (defaults to config).",
)
@click.option(
    "--max-failure-rate",
    type=float,
    default=None,
    help="Fail if a side exceeds this sample failure rate (defaults to config).",
)
def ci_run_cmd(
    baseline: str,
    candidate: str,
    project: str,
    test_cases_path: str | None,
    samples: int | None,
    workers: int | None,
    output_dir: str | None,
    tier: Tier,
    cassette_path: str | None,
    cassette_mode: str,
    fail_on: FailOn,
    slack_token: str | None,
    slack_channel: str | None,
    webhook_url: str | None,
    github_token: str | None,
    github_repository: str | None,
    github_pr_number: int | None,
    github_event_path: str | None,
    detail_url: str | None,
    min_live_samples: int,
    install_deps: bool | None,
    max_failure_rate: float | None,
) -> None:
    """Run AgentDiff as a CI gate and write PR-check/postmortem artifacts."""
    root = Path(project).resolve()

    try:
        config = load_config(root)
    except ValidationError as exc:
        console.print(f"[red]Invalid .agentdiff/config.yaml: {exc}[/red]")
        raise SystemExit(1)

    if tier == "hermetic" and not cassette_path:
        console.print("[red]Hermetic tier requires --cassette pointing at a replay cassette.[/red]")
        raise SystemExit(1)
    if tier == "live" and cassette_path:
        console.print("[yellow]Ignoring --cassette because --tier live was selected.[/yellow]")
        cassette_path = None

    runner_module = config.runner.module
    if not runner_module:
        console.print("[red]config.yaml is missing runner.module — run `agentdiff init` first.[/red]")
        raise SystemExit(1)

    samples_per_case = samples or config.samples_per_case
    worker_count = workers or config.sampling.workers
    should_install_deps = config.sampling.install_deps if install_deps is None else install_deps
    allowed_failure_rate = (
        config.sampling.max_failure_rate
        if max_failure_rate is None else max_failure_rate
    )
    if not 0 <= allowed_failure_rate <= 1:
        console.print("[red]--max-failure-rate must be between 0 and 1.[/red]")
        raise SystemExit(1)

    structure = structure_yaml.load(root)
    if structure is None:
        console.print("[red]No .agentdiff/structure.yaml — run `agentdiff init` first.[/red]")
        raise SystemExit(1)

    test_cases = _load_test_cases(root, test_cases_path)
    input_count = len(test_cases)
    if not test_cases:
        comparison = compare_engine.ComparisonResult(test_case_comparisons=[], overall_verdict="pass")
        summary = build_incident_summary(comparison, input_count=0)
        ci_context = _build_context(
            github_repository, github_pr_number or infer_pr_number(github_event_path),
            baseline, candidate, tier,
        )
        out = _prepare_output(root, output_dir)
        _write_ci_artifacts(out, summary, comparison, None, {}, detail_url, ci_context)
        _write_github_outputs(out, summary)
        console.print("[yellow]No test cases found; wrote WARN CI artifacts.[/yellow]")
        raise SystemExit(_exit_code(summary.verdict, fail_on))

    baseline_ref, baseline_label, smoke_mode = resolve_baseline(root, baseline)
    git_error = git_validation_error(root, baseline_ref, candidate)
    if git_error:
        console.print(f"[red]{git_error}[/red]")
        raise SystemExit(1)

    out = _prepare_output(root, output_dir)
    baseline_jsonl = out / "baseline_trajectories.jsonl"
    candidate_jsonl = out / "candidate_trajectories.jsonl"
    candidate_ref = None if candidate == "working" else candidate
    cassette_mode_for_sampling = cassette_mode if cassette_path else None

    for tag, ref, jsonl in (
        ("baseline", baseline_ref, baseline_jsonl),
        ("candidate", candidate_ref, candidate_jsonl),
    ):
        console.print(f"[bold]CI sampling {tag}[/bold] (ref: {ref or 'working'}, tier: {tier})")
        try:
            sampling.sample_for_side(
                git_ref=ref,
                runner_module=runner_module,
                runner_callable=config.runner.callable,
                test_cases=test_cases,
                samples_per_case=samples_per_case,
                version_tag=tag,  # type: ignore[arg-type]
                output_path=jsonl,
                repo_root=root,
                install_deps=should_install_deps,
                capture=config.capture.model_dump(),
                workers=worker_count,
                cassette_path=cassette_path,
                cassette_mode=cassette_mode_for_sampling,
            )
        except Exception as exc:
            console.print(f"[red]{tag.capitalize()} sampling failed: {type(exc).__name__}: {exc}[/red]")
            raise SystemExit(1)

    baseline_set = storage.load_trajectory_set(baseline_jsonl, "baseline")
    candidate_set = storage.load_trajectory_set(candidate_jsonl, "candidate")
    for tag, ts in (("baseline", baseline_set), ("candidate", candidate_set)):
        _validate_trajectory_quality(tag, ts, allowed_failure_rate)

    test_case_ids = [tc["id"] for tc in test_cases]
    comparison = compare_engine.compare_all(
        baseline_set,
        candidate_set,
        structure,
        test_case_ids,
        thresholds=thresholds_for_compare(config),
    )

    attribution = None
    if not smoke_mode and baseline_ref is not None:
        from agentdiff.attribution import engine as attribution_engine
        attribution = attribution_engine.attribute_range(
            comparison=comparison,
            structure=structure,
            baseline_trajectories=baseline_set.trajectories,
            candidate_trajectories=candidate_set.trajectories,
            repo_root=root,
            git_range=GitRange(base_ref=baseline_ref, head_ref=candidate_ref),
            llm_client=None,
        )

    summary = build_incident_summary(
        comparison,
        attribution,
        input_count=input_count,
        min_live_samples=min_live_samples if tier == "live" else None,
    )
    resolved_pr_number = github_pr_number or infer_pr_number(github_event_path)
    ci_context = _build_context(
        github_repository, resolved_pr_number, baseline_label, candidate, tier,
    )
    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "baseline_ref": baseline_label,
        "candidate_ref": candidate,
        "tier": tier,
        "cassette": cassette_path,
        "samples_per_case": samples_per_case,
        "workers": worker_count,
        "baseline_trajectories": len(baseline_set.trajectories),
        "candidate_trajectories": len(candidate_set.trajectories),
        "baseline_failed": _failed_count(baseline_set),
        "candidate_failed": _failed_count(candidate_set),
        "thresholds": thresholds_for_compare(config),
    }
    _write_ci_artifacts(out, summary, comparison, attribution, meta, detail_url, ci_context)
    _write_github_outputs(out, summary)
    _deliver_integrations(
        out=out,
        summary=summary,
        context=ci_context,
        slack_token=slack_token,
        slack_channel=slack_channel,
        webhook_url=webhook_url,
        github_token=github_token,
        github_repository=github_repository,
        github_pr_number=resolved_pr_number,
        detail_url=detail_url,
    )

    # Opt-in upload to hosted API (only when both env vars are set)
    _api_url = os.environ.get("AGENTDIFF_API_URL")
    _api_key = os.environ.get("AGENTDIFF_API_KEY")
    if _api_url and _api_key:
        from collector import uploader as _uploader   # lazy: only needed for hosted upload
        _payload = _uploader.build_payload(
            idempotency_key=os.environ.get("GITHUB_SHA") or str(meta["timestamp"]),
            baseline_ref=baseline_label,
            candidate_ref=candidate,
            tier=tier,
            config=structure.model_dump() if hasattr(structure, "model_dump") else {},
            attribution=attribution.model_dump() if attribution is not None else None,
            baseline_trajs=[t.model_dump() for t in baseline_set.trajectories],
            candidate_trajs=[t.model_dump() for t in candidate_set.trajectories],
        )
        try:
            _uploader.upload(_api_url, _api_key, _payload)
            console.print("[green]AgentDiff run uploaded to hosted API[/green]")
        except Exception as _exc:
            console.print(
                f"[yellow]Upload failed (local artifacts still written): {_exc}[/yellow]"
            )

    console.print(f"\n[green]CI artifacts written[/green] → {out}")
    console.print(f"AgentDiff CI verdict: [bold]{summary.verdict.upper()}[/bold]")
    raise SystemExit(_exit_code(summary.verdict, fail_on))


def _build_context(
    repository: str | None,
    pr_number: int | None,
    baseline_ref: str | None,
    candidate_ref: str | None,
    tier: str,
) -> IncidentContext:
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ.get("GITHUB_RUN_ID")
    run_url = f"{server_url}/{repository}/actions/runs/{run_id}" if repository and run_id else None
    return IncidentContext(
        repository=repository,
        pr_number=pr_number,
        baseline_ref=baseline_ref,
        candidate_ref=candidate_ref,
        tier=tier,
        run_url=run_url,
        server_url=server_url,
    )


def _prepare_output(root: Path, output_dir: str | None) -> Path:
    if output_dir:
        out = Path(output_dir)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        out = root / ".agentdiff" / "ci" / timestamp
    out.mkdir(parents=True, exist_ok=True)
    return out


def _write_ci_artifacts(
    out: Path,
    summary,
    comparison,
    attribution,
    meta: dict,
    detail_url: str | None,
    context: IncidentContext | None = None,
) -> None:
    pr_check = render_pr_check(summary, context=context)
    (out / "agentdiff-ci.md").write_text(pr_check, encoding="utf-8")
    (out / "postmortem.md").write_text(render_postmortem(summary, context=context), encoding="utf-8")
    (out / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    (out / "metadata.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    (out / "comparison.json").write_text(comparison.model_dump_json(indent=2), encoding="utf-8")
    if attribution is not None:
        (out / "attribution.json").write_text(attribution.model_dump_json(indent=2), encoding="utf-8")
    (out / "slack_blocks.json").write_text(
        json.dumps(render_slack_blocks(summary, context=context, detail_url=detail_url), indent=2),
        encoding="utf-8",
    )
    (out / "slack_payload.json").write_text(
        json.dumps(render_slack_payload(summary, context=context, detail_url=detail_url), indent=2),
        encoding="utf-8",
    )
    _append_github_summary(pr_check)


def _append_github_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(markdown)
        f.write("\n")


def _write_github_outputs(out: Path, summary) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"verdict={summary.verdict}\n")
            f.write(f"artifact_dir={out}\n")
            f.write(f"summary_path={out / 'agentdiff-ci.md'}\n")


def _deliver_integrations(
    *,
    out: Path,
    summary,
    context: IncidentContext | None,
    slack_token: str | None,
    slack_channel: str | None,
    webhook_url: str | None,
    github_token: str | None,
    github_repository: str | None,
    github_pr_number: int | None,
    detail_url: str | None,
) -> None:
    artifacts = {
        "summary_path": str(out / "agentdiff-ci.md"),
        "postmortem_path": str(out / "postmortem.md"),
        "json_path": str(out / "summary.json"),
    }
    results = []
    if slack_token and slack_channel:
        results.append(
            SlackClient(slack_token).post_payload(
                slack_channel,
                render_slack_payload(summary, context=context, detail_url=detail_url),
            )
        )
    if webhook_url:
        results.append(WebhookClient().post_summary(webhook_url, summary, artifacts=artifacts))
    if github_token and github_repository and github_pr_number:
        pr_body = render_pr_check(summary, context=context)
        results.append(
            GitHubClient(github_token).upsert_pr_comment(
                repository=github_repository,
                pr_number=github_pr_number,
                body=pr_body,
            )
        )

    for result in results:
        if result.ok:
            target = f" → {result.url}" if result.url else ""
            console.print(f"[green]{result.integration} delivery succeeded[/green]{target}")
        else:
            console.print(
                f"[yellow]{result.integration} delivery failed; "
                f"PR check remains source of truth: {result.error}[/yellow]"
            )


def _exit_code(verdict: str, fail_on: FailOn) -> int:
    if fail_on == "never":
        return 0
    threshold = _SEVERITY[fail_on]
    return 1 if _SEVERITY[verdict] >= threshold else 0
