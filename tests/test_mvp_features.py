import json

import yaml
from click.testing import CliRunner

from agentdiff.capture.events import FrameworkEvent
from agentdiff.capture.framework.base import record_framework_event
from agentdiff.capture.http.streaming import extract_stream_chunks
from agentdiff.capture.tracer import Tracer
from agentdiff.cli.main import cli
from agentdiff.storage import load_trajectory_set
from agentdiff.traffic import discover_test_cases


def test_streaming_sse_chunks_become_text_deltas():
    body = (
        b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    chunks = extract_stream_chunks("openai_chat", body)

    assert [c["text_delta"] for c in chunks] == ["Hel", "lo"]
    assert chunks[0]["metadata"]["provider"] == "openai_chat"


def test_framework_event_serializes_inside_trajectory(tmp_path):
    out = tmp_path / "traj.jsonl"
    with Tracer("tc", "baseline", {}, out):
        record_framework_event(
            framework="langgraph",
            kind="node_start",
            name="router",
            metadata={"step": 1},
        )

    ts = load_trajectory_set(out, "baseline")
    event = ts.trajectories[0].events[0]
    assert isinstance(event, FrameworkEvent)
    assert event.framework == "langgraph"
    assert event.kind == "node_start"
    assert event.name == "router"


def test_quickstart_infers_runner_and_writes_config(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("def run(input_data):\n    return 'ok'\n")

    result = CliRunner().invoke(cli, ["quickstart", str(project)], catch_exceptions=False)

    assert result.exit_code == 0
    config = yaml.safe_load((project / ".agentdiff" / "config.yaml").read_text())
    assert config["runner"] == {"module": "app", "callable": "run"}
    assert config["capture"]["langgraph"] is True
    assert (project / ".agentdiff" / "test_cases.yaml").exists()


def test_traffic_discovery_from_jsonl(tmp_path):
    source = tmp_path / "traffic.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps({"message": "Can you help me understand pricing?"}),
                json.dumps({"message": "Can you help me understand pricing?"}),
                json.dumps({"query": "Write a short onboarding email"}),
            ]
        )
    )

    cases = discover_test_cases(source, max_cases=10)

    assert len(cases) == 2
    assert cases[0]["tags"] == ["traffic", "support"]
    assert cases[1]["tags"] == ["traffic", "creative"]


def test_compare_auto_runs_working_tree_smoke_without_git(tmp_path):
    project = tmp_path / "proj"
    ad = project / ".agentdiff"
    ad.mkdir(parents=True)
    (project / "smoke_runner.py").write_text("def run(input_data):\n    return {'ok': True}\n")
    (ad / "structure.yaml").write_text("version: '1'\nagents: []\ntools: []\nentry_points: []\n")
    (ad / "config.yaml").write_text(
        "runner:\n"
        "  module: smoke_runner\n"
        "  callable: run\n"
        "samples_per_case: 1\n"
        "sampling:\n"
        "  install_deps: false\n"
        "  max_failure_rate: 0.0\n"
        "  workers: 1\n"
    )
    (ad / "test_cases.yaml").write_text("test_cases:\n  - id: tc\n    input: {}\n")

    result = CliRunner().invoke(
        cli,
        ["compare", "--baseline", "auto", "--samples", "1", "--project", str(project)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    reports = list((ad / "reports").glob("*/"))
    assert reports
    metadata = json.loads((reports[0] / "metadata.json").read_text())
    assert metadata["smoke_mode"] is True
    assert (reports[0] / "dashboard.html").exists()
