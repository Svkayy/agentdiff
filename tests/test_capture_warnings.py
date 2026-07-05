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

    try:
        with pytest.warns(AgentDiffCaptureWarning) as record:
            activator.install({"httpx": True})

        httpx_warnings = [w for w in record.list if "httpx" in str(w.message)]
        assert len(httpx_warnings) == 1
    finally:
        # Clear the process-wide warned-shims dedupe so this test's warning
        # doesn't silence the same warning in a later test.
        activator.uninstall()


def test_second_install_in_process_does_not_rewarn(monkeypatch):
    """Important 3 regression test.

    compare/ci call ``activator.install()`` once for baseline and once for
    candidate in the same process. Before the dedupe fix, each call warns
    independently, so the same AgentDiffCaptureWarning fires twice per run.
    After the fix, a shim that already warned once in this process must stay
    silent on a second ``install()`` call — until ``agentdiff.uninstall()``
    clears the dedupe state, at which point it's fair game to warn again
    (e.g. for test isolation, or a genuinely new capture session).
    """
    _reset_httpx_shim_state(monkeypatch)

    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("no httpx for you")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    try:
        with pytest.warns(AgentDiffCaptureWarning) as record:
            activator.install({"httpx": True})
        httpx_warnings = [w for w in record.list if "httpx" in str(w.message)]
        assert len(httpx_warnings) == 1

        # Second install() call in the same process: no new warning.
        with warnings_recorder() as record2:
            activator.install({"httpx": True})
        assert not any("httpx" in str(w.message) for w in record2)

        # uninstall() clears the dedupe state -> warns again afterward.
        activator.uninstall()
        with pytest.warns(AgentDiffCaptureWarning) as record3:
            activator.install({"httpx": True})
        httpx_warnings_again = [w for w in record3.list if "httpx" in str(w.message)]
        assert len(httpx_warnings_again) == 1
    finally:
        activator.uninstall()


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

    try:
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
    finally:
        # agentdiff.record() calls agentdiff.install(); leaving shims patched
        # (in particular httpx_shim._PATCHED left True) leaks into later
        # tests that monkeypatch httpx.Client.send directly and expect
        # a fresh, unpatched install() to wrap their fake send — a stale
        # _PATCHED=True short-circuits install() and never wraps it.
        agentdiff.uninstall()
