"""Loud capture degradation: enabled-but-unavailable shims warn once."""
import logging

import pytest

import agentdiff
from agentdiff.capture import AgentDiffCaptureWarning
from agentdiff.capture import activator
from agentdiff.capture.http import httpx_shim, provider_registry


def _reset_httpx_shim_state(monkeypatch):
    monkeypatch.setattr(httpx_shim, "_PATCHED", False)
    monkeypatch.setattr(httpx_shim, "_ORIGINALS", {})


def test_enabled_shim_unavailable_warns_once(monkeypatch):
    """httpx enabled but import fails -> exactly one AgentDiffCaptureWarning."""
    _reset_httpx_shim_state(monkeypatch)

    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("no httpx for you")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    with pytest.warns(AgentDiffCaptureWarning) as record:
        activator.install({"httpx": True})

    httpx_warnings = [w for w in record.list if "httpx" in str(w.message)]
    assert len(httpx_warnings) == 1


def test_disabled_shim_unavailable_does_not_warn(monkeypatch):
    """A shim the user explicitly disabled never warns, even if unavailable."""
    _reset_httpx_shim_state(monkeypatch)

    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("no httpx for you")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    with warnings_recorder() as record:
        activator.install({"httpx": False})

    assert not any("httpx" in str(w.message) for w in record)


def warnings_recorder():
    import warnings as _warnings
    return _warnings.catch_warnings(record=True)


def test_available_shim_installs_without_warning(monkeypatch):
    """httpx is actually importable in the test env -> no warning, install succeeds."""
    _reset_httpx_shim_state(monkeypatch)
    try:
        import httpx  # noqa: F401
    except ImportError:
        pytest.skip("httpx not installed in test env")

    with warnings_recorder() as record:
        activator.install({"httpx": True})

    assert not any("httpx" in str(w.message) for w in record)
    activator.uninstall()


def test_provider_registry_bad_regex_logs_skip(tmp_path, caplog):
    """A malformed custom provider regex is skipped and logged, never raised."""
    ad_dir = tmp_path / ".agentdiff"
    ad_dir.mkdir()
    (ad_dir / "providers.yaml").write_text(
        "providers:\n"
        "  - name: broken_provider\n"
        "    url_pattern: \"([unclosed\"\n"
    )

    with caplog.at_level(logging.WARNING, logger="agentdiff.capture.http.provider_registry"):
        added = provider_registry.load_custom_providers(tmp_path)

    assert added == 0
    assert any("broken_provider" in rec.message for rec in caplog.records)


def test_record_session_prints_overwrite_warning(tmp_path, capsys):
    """agentdiff.record() truncating an existing capture file prints a loud warning."""
    import agentdiff.capture.session as session

    session._RESET_SEEN.clear()
    with agentdiff.record("mycap", project_root=tmp_path):
        pass
    capsys.readouterr()

    session._RESET_SEEN.clear()  # force the truncation path again in this process
    with agentdiff.record("mycap", project_root=tmp_path):
        pass
    out = capsys.readouterr().out

    path = session.captures_dir(tmp_path) / "mycap.jsonl"
    assert "Overwriting existing capture" in out
    assert "mycap" in out
    assert str(path) in out
