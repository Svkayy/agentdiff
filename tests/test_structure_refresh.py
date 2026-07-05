"""Tests for `agentdiff structure` refresh and structure_yaml.merge_structures."""
import shutil
from pathlib import Path

from click.testing import CliRunner

from agentdiff.cli.main import cli
from agentdiff.structure import structure_yaml
from agentdiff.structure.structure_yaml import (
    AgentEntry,
    EntryPointEntry,
    StructureDiff,
    StructureDoc,
    ToolEntry,
    merge_structures,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projects" / "anthropic_simple"


# ---------------------------------------------------------------------------
# merge_structures — unit tests
# ---------------------------------------------------------------------------

def test_merge_preserves_renamed_display_name_for_existing_agent():
    """A user-edited display name for a kept agent must survive the merge."""
    existing = StructureDoc(
        agents=[AgentEntry(name="My Renamed Agent", function="research_agent", file="agent.py", line=5)]
    )
    fresh = StructureDoc(
        agents=[AgentEntry(name="research_agent", function="research_agent", file="agent.py", line=5)]
    )

    merged, diff = merge_structures(existing, fresh)

    assert len(merged.agents) == 1
    assert merged.agents[0].name == "My Renamed Agent"
    assert merged.agents[0].function == "research_agent"
    assert "agent.py:research_agent" in diff.kept


def test_merge_adds_new_function_to_added():
    existing = StructureDoc(
        agents=[AgentEntry(name="research_agent", function="research_agent", file="agent.py", line=5)]
    )
    fresh = StructureDoc(
        agents=[
            AgentEntry(name="research_agent", function="research_agent", file="agent.py", line=5),
            AgentEntry(name="new_agent", function="new_agent", file="agent.py", line=20),
        ]
    )

    merged, diff = merge_structures(existing, fresh)

    merged_fns = {a.function for a in merged.agents}
    assert "new_agent" in merged_fns
    assert "agent.py:new_agent" in diff.added
    assert diff.added == ["agent.py:new_agent"]


def test_merge_drops_vanished_function_to_removed():
    existing = StructureDoc(
        agents=[
            AgentEntry(name="research_agent", function="research_agent", file="agent.py", line=5),
            AgentEntry(name="old_agent", function="old_agent", file="agent.py", line=30),
        ]
    )
    fresh = StructureDoc(
        agents=[AgentEntry(name="research_agent", function="research_agent", file="agent.py", line=5)]
    )

    merged, diff = merge_structures(existing, fresh)

    merged_fns = {a.function for a in merged.agents}
    assert "old_agent" not in merged_fns
    assert "agent.py:old_agent" in diff.removed


def test_merge_handles_tools_and_entry_points():
    existing = StructureDoc(
        tools=[ToolEntry(name="Searcher", function="web_search", file="tools.py", line=4)],
        entry_points=[EntryPointEntry(function="main", file="main.py", line=4)],
    )
    fresh = StructureDoc(
        tools=[ToolEntry(name="web_search", function="web_search", file="tools.py", line=4)],
        entry_points=[EntryPointEntry(function="main", file="main.py", line=4)],
    )

    merged, diff = merge_structures(existing, fresh)

    assert merged.tools[0].name == "Searcher"
    assert "tools.py:web_search" in diff.kept
    assert "main.py:main" in diff.kept


def test_merge_role_change_uses_fresh_classification():
    """If a function moves from tool to agent in the fresh scan, fresh role wins,
    but its identity-based edits (name) still carry over when the identity key matches."""
    existing = StructureDoc(
        tools=[ToolEntry(name="My Tool", function="do_thing", file="a.py", line=1)],
    )
    fresh = StructureDoc(
        agents=[AgentEntry(name="do_thing", function="do_thing", file="a.py", line=1)],
    )

    merged, diff = merge_structures(existing, fresh)

    assert len(merged.tools) == 0
    assert len(merged.agents) == 1
    assert "a.py:do_thing" in diff.kept


def test_structure_diff_dataclass_fields():
    diff = StructureDiff(added=["a"], removed=["b"], kept=["c"])
    assert diff.added == ["a"]
    assert diff.removed == ["b"]
    assert diff.kept == ["c"]


# ---------------------------------------------------------------------------
# CLI: agentdiff structure
# ---------------------------------------------------------------------------

def _init_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(project), "--no-install-hook"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return project


def test_cli_structure_refreshes_and_preserves_edits(tmp_path):
    project = _init_project(tmp_path)

    # Simulate a user editing the display name of the inferred agent.
    doc = structure_yaml.load(project)
    assert doc is not None
    doc.agents[0].name = "Custom Display Name"
    structure_yaml.save(doc, project)

    runner = CliRunner()
    result = runner.invoke(cli, ["structure", str(project)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    reloaded = structure_yaml.load(project)
    assert reloaded is not None
    agent = next(a for a in reloaded.agents if a.function == "research_agent")
    assert agent.name == "Custom Display Name"


def test_cli_structure_reports_added_removed_kept(tmp_path):
    project = _init_project(tmp_path)

    # Remove a tool function so it should be reported as removed, and add a new one.
    (project / "tools.py").write_text(
        "import agentdiff\n\n\n"
        "@agentdiff.tool\n"
        "def brand_new_tool(query: str) -> str:\n"
        "    \"\"\"A new tool.\"\"\"\n"
        "    return query\n"
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["structure", str(project)], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "added" in result.output.lower()
    assert "removed" in result.output.lower()
    assert "brand_new_tool" in result.output
    assert "web_search" in result.output  # reported as removed

    reloaded = structure_yaml.load(project)
    assert reloaded is not None
    tool_fns = {t.function for t in reloaded.tools}
    assert "brand_new_tool" in tool_fns
    assert "web_search" not in tool_fns


def test_cli_structure_dry_run_leaves_file_untouched(tmp_path):
    project = _init_project(tmp_path)
    yaml_path = project / ".agentdiff" / "structure.yaml"
    before = yaml_path.read_text()

    # Change source so a real refresh would change the file.
    (project / "tools.py").write_text(
        "import agentdiff\n\n\n"
        "@agentdiff.tool\n"
        "def another_new_tool(query: str) -> str:\n"
        "    \"\"\"A new tool.\"\"\"\n"
        "    return query\n"
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["structure", str(project), "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    after = yaml_path.read_text()
    assert before == after, "structure.yaml must be untouched by --dry-run"
    assert "another_new_tool" in result.output


def test_cli_structure_dry_run_reports_would_add(tmp_path):
    project = _init_project(tmp_path)
    (project / "tools.py").write_text(
        "import agentdiff\n\n\n"
        "@agentdiff.tool\n"
        "def another_new_tool(query: str) -> str:\n"
        "    \"\"\"A new tool.\"\"\"\n"
        "    return query\n"
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["structure", str(project), "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "dry" in result.output.lower() or "would" in result.output.lower()


def test_cli_structure_no_existing_structure_yaml_creates_one(tmp_path):
    """Running `agentdiff structure` with no prior structure.yaml behaves like a fresh scan."""
    project = tmp_path / "fresh_project"
    shutil.copytree(FIXTURE, project)

    runner = CliRunner()
    result = runner.invoke(cli, ["structure", str(project)], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    doc = structure_yaml.load(project)
    assert doc is not None
    assert any(a.function == "research_agent" for a in doc.agents)
