"""Static import-graph reachability used by attribution rule 5."""
from agentdiff.attribution.reachability import reachable_files


def test_follows_transitive_imports(tmp_path):
    (tmp_path / "agent.py").write_text("import helper\nimport os\n")
    (tmp_path / "helper.py").write_text("from deep import thing\n")
    (tmp_path / "deep.py").write_text("thing = 1\n")
    (tmp_path / "unrelated.py").write_text("x = 1\n")

    r = reachable_files(tmp_path, "agent.py")
    assert {"agent.py", "helper.py", "deep.py"} <= r
    assert "unrelated.py" not in r  # never imported
    assert "os.py" not in r          # stdlib doesn't resolve to a project file


def test_relative_imports(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "agent.py").write_text("from . import tools\nfrom .util import helper\n")
    (pkg / "tools.py").write_text("y = 1\n")
    (pkg / "util.py").write_text("def helper(): ...\n")

    r = reachable_files(tmp_path, "pkg/agent.py")
    assert {"pkg/agent.py", "pkg/tools.py", "pkg/util.py"} <= r


def test_from_import_submodule(tmp_path):
    (tmp_path / "agent.py").write_text("from mypkg import sub\n")
    pkg = tmp_path / "mypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "sub.py").write_text("z = 1\n")

    r = reachable_files(tmp_path, "agent.py")
    assert "mypkg/sub.py" in r


def test_missing_start_file(tmp_path):
    assert reachable_files(tmp_path, "nope.py") == set()


def test_cycle_terminates(tmp_path):
    (tmp_path / "a.py").write_text("import b\n")
    (tmp_path / "b.py").write_text("import a\n")
    r = reachable_files(tmp_path, "a.py")
    assert r == {"a.py", "b.py"}
