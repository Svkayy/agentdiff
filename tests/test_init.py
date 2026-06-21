"""Day 4 tests: AST walker, heuristic classifier, structure.yaml, agentdiff init CLI."""
from pathlib import Path

from click.testing import CliRunner

from agentdiff.structure.ast_walker import walk_project, CandidateFunction
from agentdiff.structure.heuristic_classifier import classify
from agentdiff.structure import structure_yaml
from agentdiff.cli.main import cli

FIXTURE = Path(__file__).parent / "fixtures" / "sample_projects" / "anthropic_simple"


# ---------------------------------------------------------------------------
# AST walker
# ---------------------------------------------------------------------------

def test_walker_finds_all_functions():
    candidates = walk_project(FIXTURE)
    names = {c.name for c in candidates}
    assert "research_agent" in names
    assert "web_search" in names
    assert "get_date" in names
    assert "main" in names


def test_walker_detects_llm_call():
    candidates = walk_project(FIXTURE)
    agent = next(c for c in candidates if c.name == "research_agent")
    assert agent.calls_llm is True
    assert agent.module_imports_llm_sdk is True


def test_walker_detects_tool_decorator():
    candidates = walk_project(FIXTURE)
    search = next(c for c in candidates if c.name == "web_search")
    assert search.has_agentdiff_tool_decorator is True


def test_walker_no_llm_in_main():
    candidates = walk_project(FIXTURE)
    main_fn = next(c for c in candidates if c.name == "main")
    assert main_fn.calls_llm is False


def test_walker_skips_venv(tmp_path):
    """Files inside .venv must be ignored."""
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "spam.py").write_text("def hidden(): pass")
    (tmp_path / "real.py").write_text("def visible(): pass")
    candidates = walk_project(tmp_path)
    names = {c.name for c in candidates}
    assert "visible" in names
    assert "hidden" not in names


# ---------------------------------------------------------------------------
# Heuristic classifier
# ---------------------------------------------------------------------------

def test_classifier_identifies_agent():
    candidates = walk_project(FIXTURE)
    doc = classify(candidates)
    agent_fns = {a.function for a in doc.agents}
    assert "research_agent" in agent_fns


def test_classifier_identifies_tools():
    candidates = walk_project(FIXTURE)
    doc = classify(candidates)
    tool_fns = {t.function for t in doc.tools}
    assert "web_search" in tool_fns
    assert "get_date" in tool_fns


def test_classifier_identifies_entry_point():
    candidates = walk_project(FIXTURE)
    doc = classify(candidates)
    ep_fns = {e.function for e in doc.entry_points}
    assert "main" in ep_fns


def test_classifier_no_agent_in_tools():
    candidates = walk_project(FIXTURE)
    doc = classify(candidates)
    tool_fns = {t.function for t in doc.tools}
    assert "research_agent" not in tool_fns


# ---------------------------------------------------------------------------
# structure.yaml round-trip
# ---------------------------------------------------------------------------

def test_structure_yaml_roundtrip(tmp_path):
    candidates = walk_project(FIXTURE)
    doc = classify(candidates)

    out_path = structure_yaml.save(doc, tmp_path)
    assert out_path.exists()

    loaded = structure_yaml.load(tmp_path)
    assert loaded is not None
    assert {a.function for a in loaded.agents} == {a.function for a in doc.agents}
    assert {t.function for t in loaded.tools} == {t.function for t in doc.tools}
    assert {e.function for e in loaded.entry_points} == {e.function for e in doc.entry_points}


def test_structure_yaml_is_human_readable(tmp_path):
    """YAML output must be plain text, not a blob."""
    candidates = walk_project(FIXTURE)
    doc = classify(candidates)
    path = structure_yaml.save(doc, tmp_path)
    text = path.read_text()
    assert "research_agent" in text
    assert "web_search" in text
    assert "version:" in text


def test_load_returns_none_when_missing(tmp_path):
    assert structure_yaml.load(tmp_path) is None


# ---------------------------------------------------------------------------
# CLI: agentdiff init
# ---------------------------------------------------------------------------

def test_cli_init_creates_structure_yaml(tmp_path):
    """The init command must create .agentdiff/structure.yaml in the scanned project."""
    import shutil
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(project), "--no-install-hook"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    yaml_path = project / ".agentdiff" / "structure.yaml"
    assert yaml_path.exists(), "structure.yaml was not created by agentdiff init"


def test_cli_init_end_to_end(tmp_path):
    """Copy fixture into tmp_path so we don't pollute the source tree."""
    import shutil
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(project), "--no-install-hook"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    yaml_path = project / ".agentdiff" / "structure.yaml"
    assert yaml_path.exists(), "structure.yaml was not created"

    doc = structure_yaml.load(project)
    assert doc is not None
    agent_fns = {a.function for a in doc.agents}
    tool_fns = {t.function for t in doc.tools}
    assert "research_agent" in agent_fns
    assert "web_search" in tool_fns
    assert "get_date" in tool_fns


def test_cli_init_output_contains_roles(tmp_path):
    import shutil
    project = tmp_path / "project"
    shutil.copytree(FIXTURE, project)

    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(project), "--no-install-hook"], catch_exceptions=False)
    assert "agent" in result.output
    assert "tool" in result.output


# ---------------------------------------------------------------------------
# AST walker — class method extraction
# ---------------------------------------------------------------------------

def test_walker_finds_class_llm_method(tmp_path):
    """A class method that calls an LLM must appear as ClassName.method_name."""
    (tmp_path / "agent.py").write_text(
        "import anthropic\n"
        "class MyAgent:\n"
        "    def run(self):\n"
        "        client = anthropic.Anthropic()\n"
        "        return client.messages.create(model='x', messages=[])\n"
        "    def helper(self):\n"
        "        return 'noop'\n"
    )
    candidates = walk_project(tmp_path)
    names = {c.name for c in candidates}
    assert "MyAgent.run" in names, "LLM-calling class method should be detected"
    assert "MyAgent.helper" not in names, "plain helper method should be excluded"


def test_walker_class_llm_method_has_class_name(tmp_path):
    """class_name field must be populated for class methods."""
    (tmp_path / "agent.py").write_text(
        "import openai\n"
        "class Bot:\n"
        "    def respond(self):\n"
        "        return openai.chat.completions.create(model='gpt-4', messages=[])\n"
    )
    candidates = walk_project(tmp_path)
    method = next((c for c in candidates if c.name == "Bot.respond"), None)
    assert method is not None
    assert method.class_name == "Bot"
    assert method.calls_llm is True


def test_walker_finds_class_tool_method(tmp_path):
    """A class method decorated with @agentdiff.tool must be included even without LLM call."""
    (tmp_path / "tools.py").write_text(
        "import agentdiff\n"
        "class MyTools:\n"
        "    @agentdiff.tool\n"
        "    def web_search(self, query):\n"
        "        return f'results for {query}'\n"
    )
    candidates = walk_project(tmp_path)
    names = {c.name for c in candidates}
    assert "MyTools.web_search" in names


def test_classifier_classifies_class_method_agent(tmp_path):
    """Heuristic classifier must label ClassName.method_name as agent when it calls LLM."""
    (tmp_path / "agent.py").write_text(
        "import anthropic\n"
        "class ResearchAgent:\n"
        "    def run(self):\n"
        "        client = anthropic.Anthropic()\n"
        "        return client.messages.create(model='x', messages=[])\n"
    )
    candidates = walk_project(tmp_path)
    doc = classify(candidates)
    agent_fns = {a.function for a in doc.agents}
    assert "ResearchAgent.run" in agent_fns


# ---------------------------------------------------------------------------
# LLM classifier — fallback and duplicate-key handling
# ---------------------------------------------------------------------------

def test_llm_classifier_fallback_on_no_json(tmp_path):
    """When response contains no JSON array, heuristic_doc is returned unchanged."""
    from agentdiff.structure.llm_classifier import _parse_response
    from agentdiff.structure.structure_yaml import StructureDoc, AgentEntry

    heuristic = StructureDoc(
        agents=[AgentEntry(name="my_agent", function="my_agent", file="a.py", line=1)]
    )
    candidates = [CandidateFunction(name="my_agent", file="a.py", line=1, is_async=False)]

    result = _parse_response("I cannot classify these functions.", candidates, heuristic)
    assert {a.function for a in result.agents} == {"my_agent"}


def test_llm_classifier_fallback_on_malformed_json(tmp_path):
    """When the extracted JSON array is malformed, heuristic_doc is returned unchanged."""
    from agentdiff.structure.llm_classifier import _parse_response
    from agentdiff.structure.structure_yaml import StructureDoc, AgentEntry

    heuristic = StructureDoc(
        agents=[AgentEntry(name="my_agent", function="my_agent", file="a.py", line=1)]
    )
    candidates = [CandidateFunction(name="my_agent", file="a.py", line=1, is_async=False)]

    result = _parse_response("[{broken json", candidates, heuristic)
    assert {a.function for a in result.agents} == {"my_agent"}


def test_llm_classifier_no_collision_on_duplicate_names():
    """Functions with identical names in different files must be classified independently."""
    from agentdiff.structure.llm_classifier import _parse_response
    from agentdiff.structure.structure_yaml import StructureDoc

    candidates = [
        CandidateFunction(name="run", file="agents/a.py", line=1, is_async=False),
        CandidateFunction(name="run", file="agents/b.py", line=5, is_async=False),
    ]
    heuristic = StructureDoc()

    raw = (
        '[{"function": "run", "file": "agents/a.py", "role": "agent", "name": "Agent A"}, '
        ' {"function": "run", "file": "agents/b.py", "role": "tool",  "name": "Tool B"}]'
    )
    result = _parse_response(raw, candidates, heuristic)

    assert len(result.agents) == 1, "exactly one agent expected"
    assert result.agents[0].file == "agents/a.py"
    assert len(result.tools) == 1, "exactly one tool expected"
    assert result.tools[0].file == "agents/b.py"


# ---------------------------------------------------------------------------
# structure.yaml + Tracer — inferred_agent wiring
# ---------------------------------------------------------------------------

def test_agent_names_for_functions_includes_simple_alias(tmp_path):
    """Class method agents expose a simple-name alias for call-stack lookup."""
    from agentdiff.structure.structure_yaml import StructureDoc, AgentEntry

    doc = StructureDoc(
        agents=[AgentEntry(name="Research Agent", function="ResearchAgent.run", file="agent.py", line=1)]
    )
    agent_map = doc.agent_names_for_functions()

    # Exact qualified name must be present.
    assert agent_map.get("ResearchAgent.run") == "Research Agent"
    # Simple name alias must also resolve — this is what the call stack provides.
    assert agent_map.get("run") == "Research Agent"


def test_tracer_populates_inferred_agent(tmp_path):
    """Tracer.record() sets inferred_agent on events whose call_stack contains a known agent."""
    from uuid import uuid4
    from agentdiff.capture.tracer import Tracer
    from agentdiff.capture.events import LLMRequestEvent, CanonicalLLMCall, CallSite, StackFrame
    from agentdiff.structure import structure_yaml
    from agentdiff.structure.structure_yaml import StructureDoc, AgentEntry

    # Write a structure.yaml with one agent.
    doc = StructureDoc(
        agents=[AgentEntry(name="Research Agent", function="research_agent", file="agent.py", line=1)]
    )
    structure_yaml.save(doc, tmp_path)

    tracer = Tracer(
        test_case_id="t1",
        version_tag="v1",
        input_data={},
        output_path=tmp_path / "out.jsonl",
        structure_root=tmp_path,
    )

    call_id = uuid4()
    event = LLMRequestEvent(
        call_id=call_id,
        canonical=CanonicalLLMCall(provider="anthropic"),
        captured_by="sdk_shim",
        callsite=CallSite(file="agent.py", function="research_agent", line=10),
        call_stack=[
            StackFrame(
                file="agent.py",
                function="research_agent",
                line=10,
                is_user_code=True,
                is_framework_internal=False,
                is_agentdiff_internal=False,
                is_sdk_internal=False,
            )
        ],
    )

    tracer.record(event)
    assert event.inferred_agent == "Research Agent"


def test_tracer_no_inferred_agent_when_no_structure_yaml(tmp_path):
    """When no structure.yaml exists, inferred_agent stays None — no crash."""
    from uuid import uuid4
    from agentdiff.capture.tracer import Tracer
    from agentdiff.capture.events import LLMRequestEvent, CanonicalLLMCall, CallSite, StackFrame

    tracer = Tracer(
        test_case_id="t2",
        version_tag="v1",
        input_data={},
        output_path=tmp_path / "out.jsonl",
        structure_root=tmp_path,  # no structure.yaml here
    )

    event = LLMRequestEvent(
        call_id=uuid4(),
        canonical=CanonicalLLMCall(provider="openai"),
        captured_by="http_shim",
        callsite=CallSite(file="main.py", function="main", line=1),
        call_stack=[
            StackFrame(
                file="main.py",
                function="main",
                line=1,
                is_user_code=True,
                is_framework_internal=False,
                is_agentdiff_internal=False,
                is_sdk_internal=False,
            )
        ],
    )

    tracer.record(event)
    assert event.inferred_agent is None
