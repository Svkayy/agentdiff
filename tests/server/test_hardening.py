"""Tests for WP1 Tier-2 backend hardening (items 1-7)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from server import security
from server.db import get_session
from server.main import app
from server.models import ApiKey, Org, Project


# ── shared helpers ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_app_state():
    yield
    app.dependency_overrides.clear()
    app.state.enqueue = None
    app.state.redis_pool = None


@pytest_asyncio.fixture(loop_scope="session")
async def _project_and_key(session):
    org = Org(name="HardenOrg")
    project = Project(org=org, name="harden-project")
    full, prefix, kh = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=kh, prefix=prefix))
    await session.commit()
    return full, project


def _base_payload(**overrides):
    p = {
        "idempotency_key": str(uuid.uuid4()),
        "baseline_ref": "origin/main",
        "candidate_ref": "working",
        "tier": "hermetic",
        "config": {},
        "attribution": None,
        "trajectories": [{"side": "baseline", "test_case_id": "tc1", "payload": {}}],
    }
    p.update(overrides)
    return p


# ── Item 1: Ingest input caps ─────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_body_size_413(session, _project_and_key):
    """A request with Content-Length exceeding max_body_bytes returns 413."""
    full, _ = _project_and_key
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        # Spoof a huge Content-Length header without actually sending bytes.
        r = await c.post(
            "/v1/runs",
            json=_base_payload(),
            headers={
                "Authorization": f"Bearer {full}",
                "Content-Length": str(100 * 1024 * 1024),  # 100 MB
                "Origin": "http://localhost:5173",
            },
        )
    assert r.status_code == 413
    # CORS must be outermost: even a 413 from BodySizeMiddleware must carry
    # CORS and RequestID headers so a cross-origin dashboard can read the error.
    assert "access-control-allow-origin" in r.headers, (
        "413 response missing CORS header — middleware ordering is wrong"
    )
    assert "x-request-id" in r.headers, (
        "413 response missing X-Request-ID header — middleware ordering is wrong"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_trajectories_over_cap_422(session, _project_and_key):
    """A trajectories list with more than 5000 items is rejected with 422."""
    full, _ = _project_and_key
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None

    oversized = [
        {"side": "baseline", "test_case_id": f"tc{i}", "payload": {}}
        for i in range(5001)
    ]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/runs",
            json=_base_payload(idempotency_key="over-cap", trajectories=oversized),
            headers={"Authorization": f"Bearer {full}"},
        )
    assert r.status_code == 422


# ── Item 2: Rate limiting ─────────────────────────────────────────────────────

class _FakeRedis:
    """Minimal fake redis that tracks INCR per key and returns controlled counts."""

    def __init__(self, counter_start: int = 0):
        self._counters: dict[str, int] = {}
        self._counter_start = counter_start
        self.incr_calls: list[str] = []

    async def incr(self, key: str) -> int:
        self.incr_calls.append(key)
        self._counters[key] = self._counters.get(key, self._counter_start) + 1
        return self._counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass


class _RaisingRedis:
    async def incr(self, key: str) -> int:
        raise RuntimeError("redis down")

    async def expire(self, key: str, seconds: int) -> None:
        pass


@pytest.mark.asyncio(loop_scope="session")
async def test_rate_limit_under_limit_202(session, _project_and_key):
    """Under the rate limit → 202."""
    full, _ = _project_and_key
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None
    app.state.redis_pool = _FakeRedis(counter_start=0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/runs",
            json=_base_payload(idempotency_key="rl-under"),
            headers={"Authorization": f"Bearer {full}"},
        )
    assert r.status_code == 202


@pytest.mark.asyncio(loop_scope="session")
async def test_rate_limit_over_limit_429(session, _project_and_key):
    """Over the rate limit → 429."""
    full, _ = _project_and_key
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None
    # counter_start=60 so first incr returns 61, which exceeds the default limit of 60.
    app.state.redis_pool = _FakeRedis(counter_start=60)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/runs",
            json=_base_payload(idempotency_key="rl-over"),
            headers={"Authorization": f"Bearer {full}"},
        )
    assert r.status_code == 429


@pytest.mark.asyncio(loop_scope="session")
async def test_rate_limit_redis_raises_failopen_202(session, _project_and_key):
    """Redis raising during rate-limit check → fail-open → 202."""
    full, _ = _project_and_key
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = None
    app.state.redis_pool = _RaisingRedis()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/runs",
            json=_base_payload(idempotency_key="rl-fail-open"),
            headers={"Authorization": f"Bearer {full}"},
        )
    assert r.status_code == 202


# ── Item 3: Enqueue failure tolerance ────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_enqueue_failure_still_202(session, _project_and_key):
    """If enqueue raises, the run is still persisted and 202 is returned."""
    full, _ = _project_and_key
    app.dependency_overrides[get_session] = lambda: session

    def _raiser(run_id: str):
        raise RuntimeError("redis is gone")

    app.state.enqueue = _raiser

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/runs",
            json=_base_payload(idempotency_key="enq-fail"),
            headers={"Authorization": f"Bearer {full}"},
        )
    assert r.status_code == 202


# ── Item 4: Auth robustness – deleted project → 401 ─────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_deleted_project_returns_401(session):
    """ApiKey whose project_id no longer exists in the projects table → 401.

    The FK constraint prevents us from inserting a dangling api_key in the test
    DB. Instead we test the dependency directly with a mock session that returns
    a valid ApiKey row but then returns None for the subsequent Project lookup,
    which is exactly the code path that scalar_one_or_none() + 401 covers.
    """
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from server.deps import get_project_from_api_key

    full, prefix, kh = security.generate_api_key()

    # Fake ApiKey object that passes the prefix and verify check.
    fake_key = MagicMock()
    fake_key.revoked_at = None
    fake_key.key_hash = kh
    fake_key.last_used_at = None
    fake_key.project_id = "phantom-uuid"

    # Two-call mock: first returns [fake_key], second returns None (project).
    call_count = 0

    class _FakeResult:
        def __init__(self, value):
            self._value = value

        def scalars(self):
            r = MagicMock()
            r.all.return_value = self._value
            return r

        def scalar_one_or_none(self):
            return self._value

    class _FakeSession:
        async def execute(self, stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First query: ApiKey lookup by prefix.
                return _FakeResult([fake_key])
            else:
                # Second query: Project lookup — project was deleted.
                return _FakeResult(None)

        async def commit(self):
            pass

    with pytest.raises(HTTPException) as exc_info:
        await get_project_from_api_key(f"Bearer {full}", _FakeSession())

    assert exc_info.value.status_code == 401


# ── Item 5: CORS ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_cors_preflight_returns_acao_header():
    """OPTIONS preflight from the allowed origin returns Access-Control-Allow-Origin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.options(
            "/v1/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


# ── Item 6: Request IDs ───────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_request_id_generated_if_absent():
    """Response always contains X-Request-ID even when not provided."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert "x-request-id" in r.headers
    # Must be a valid UUID.
    import uuid
    uuid.UUID(r.headers["x-request-id"])


@pytest.mark.asyncio(loop_scope="session")
async def test_request_id_echoed_when_provided():
    """A supplied X-Request-ID is echoed back in the response."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health", headers={"x-request-id": "my-trace-id-123"})
    assert r.headers["x-request-id"] == "my-trace-id-123"


# ── Item 7: Fernet key rotation ───────────────────────────────────────────────

def test_encrypt_decrypt_single_key():
    """Basic encrypt/decrypt round-trip with a single key."""
    from server import crypto

    key = Fernet.generate_key().decode()
    ct = crypto._fernet(key).encrypt(b"hello").decode()
    assert crypto._fernet(key).decrypt(ct.encode()).decode() == "hello"


def test_key_rotation_old_ciphertext_decrypts_with_new_primary():
    """Encrypt with key A; then rotate (primary=B, fallback=A) and verify old ciphertext decrypts."""
    from server import crypto

    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()

    # Encrypt with A alone.
    ciphertext = crypto._fernet(key_a).encrypt(b"secret").decode()

    # Rotate: B is now primary, A is fallback.
    rotated = crypto._fernet(f"{key_b},{key_a}")
    plaintext = rotated.decrypt(ciphertext.encode()).decode()
    assert plaintext == "secret"


def test_key_rotation_new_encryptions_use_primary():
    """After rotation, new encryptions should be decryptable by B alone (primary key)."""
    from server import crypto

    key_a = Fernet.generate_key().decode()
    key_b = Fernet.generate_key().decode()

    rotated = crypto._fernet(f"{key_b},{key_a}")
    new_ciphertext = rotated.encrypt(b"new-secret").decode()

    # B alone should decrypt the new ciphertext.
    assert Fernet(key_b.encode()).decrypt(new_ciphertext.encode()).decode() == "new-secret"

    # A alone should NOT decrypt the new ciphertext.
    with pytest.raises(Exception):
        Fernet(key_a.encode()).decrypt(new_ciphertext.encode())


def test_public_encrypt_decrypt_unchanged():
    """Public encrypt/decrypt API still works end-to-end (uses settings key)."""
    from server import crypto

    ct = crypto.encrypt("test-value")
    assert crypto.decrypt(ct) == "test-value"


# ── Task 12: /health DB + Redis checks ────────────────────────────────────────

class _PingOkRedis:
    async def ping(self):
        return True


class _PingFailRedis:
    async def ping(self):
        raise RuntimeError("redis down")


@pytest.mark.asyncio(loop_scope="session")
async def test_health_ok_when_db_and_redis_up():
    """Both checks pass → status ok, HTTP 200."""
    app.state.redis_pool = _PingOkRedis()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"] == {"database": True, "redis": True}


@pytest.mark.asyncio(loop_scope="session")
async def test_health_degraded_when_db_ping_fails(monkeypatch):
    """DB ping monkeypatched to fail → status degraded, HTTP 503."""
    import server.main as main_mod

    async def _fail_db():
        return False

    monkeypatch.setattr(main_mod, "_check_database", _fail_db)
    app.state.redis_pool = _PingOkRedis()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] is False
    assert body["checks"]["redis"] is True


@pytest.mark.asyncio(loop_scope="session")
async def test_health_degraded_when_redis_ping_fails(monkeypatch):
    """Redis ping raising → status degraded, HTTP 503."""
    import server.main as main_mod

    async def _ok_db():
        return True

    monkeypatch.setattr(main_mod, "_check_database", _ok_db)
    app.state.redis_pool = _PingFailRedis()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 503
    assert r.json()["checks"]["redis"] is False


# ── Task 12: /metrics exposition ──────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_metrics_endpoint_exposes_counters():
    """/metrics returns Prometheus text with the canonical counters."""
    from server.metrics import METRICS

    METRICS.inc("agentdiff_runs_processed_total")
    METRICS.inc("agentdiff_quota_rejections_total")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/metrics")
    assert r.status_code == 200
    text = r.text
    assert "agentdiff_requests_total" in text
    assert "agentdiff_runs_processed_total" in text
    assert "agentdiff_drift_checks_total" in text
    assert "agentdiff_quota_rejections_total" in text
    # The request we just made is itself counted.
    assert 'agentdiff_requests_total{' in text


# ── Task 12: retention cron ───────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_retention_deletes_only_old_rows(session, monkeypatch):
    """Retention cron deletes rows past the window and keeps recent ones."""
    from contextlib import asynccontextmanager
    from datetime import datetime, timedelta, timezone

    from server.models import Finding, LiveTrajectory, Run, Trajectory
    from server.worker import cleanup_retention

    org = Org(name="RetOrg")
    project = Project(org=org, name="ret-project")
    session.add_all([org, project])
    await session.flush()

    now = datetime.now(timezone.utc)
    old_run = Run(
        project=project, idempotency_key="ret-old", baseline_ref="a",
        candidate_ref="b", tier="hermetic", config={}, status="done",
        created_at=now - timedelta(days=200),
    )
    new_run = Run(
        project=project, idempotency_key="ret-new", baseline_ref="a",
        candidate_ref="b", tier="hermetic", config={}, status="done",
        created_at=now - timedelta(days=1),
    )
    old_live = LiveTrajectory(
        project_id=project.id, payload={}, captured_at=now - timedelta(days=90),
    )
    new_live = LiveTrajectory(
        project_id=project.id, payload={}, captured_at=now - timedelta(days=1),
    )
    session.add_all([old_run, new_run, old_live, new_live])
    await session.flush()

    # Both runs have children (Trajectory + Finding rows) with NO
    # ON DELETE CASCADE on runs->trajectories / runs->findings FKs (see
    # migration b34c322917a3). A naive `delete(Run)` would violate these FKs
    # in production, since real runs always have children — the original
    # fixture (childless runs) masked this bug.
    old_traj = Trajectory(
        run=old_run, side="baseline", test_case_id="tc-1", payload={},
    )
    old_finding = Finding(
        run=old_run, test_case_id="tc-1", title="old finding", verdict="fail",
        metric="latency", impact_summary="old impact",
    )
    new_traj = Trajectory(
        run=new_run, side="baseline", test_case_id="tc-1", payload={},
    )
    new_finding = Finding(
        run=new_run, test_case_id="tc-1", title="new finding", verdict="fail",
        metric="latency", impact_summary="new impact",
    )
    session.add_all([old_traj, old_finding, new_traj, new_finding])
    await session.commit()
    old_run_id, new_run_id = old_run.id, new_run.id
    old_live_id, new_live_id = old_live.id, new_live.id
    old_traj_id, new_traj_id = old_traj.id, new_traj.id
    old_finding_id, new_finding_id = old_finding.id, new_finding.id

    @asynccontextmanager
    async def _factory():
        yield session

    # ctx has no redis → lease is auto-granted (single-process/test mode).
    await cleanup_retention({"session_factory": _factory})

    from sqlalchemy import select as _select

    remaining_runs = (
        await session.execute(_select(Run.id).where(Run.project_id == project.id))
    ).scalars().all()
    remaining_live = (
        await session.execute(
            _select(LiveTrajectory.id).where(LiveTrajectory.project_id == project.id)
        )
    ).scalars().all()
    remaining_traj_ids = (
        await session.execute(_select(Trajectory.id))
    ).scalars().all()
    remaining_finding_ids = (
        await session.execute(_select(Finding.id))
    ).scalars().all()

    assert old_run_id not in remaining_runs
    assert new_run_id in remaining_runs
    assert old_live_id not in remaining_live
    assert new_live_id in remaining_live
    assert old_traj_id not in remaining_traj_ids
    assert new_traj_id in remaining_traj_ids
    assert old_finding_id not in remaining_finding_ids
    assert new_finding_id in remaining_finding_ids


# ── Task 12: cron lease prevents double-fire ─────────────────────────────────

class _LeaseRedis:
    """Fake redis whose SET NX succeeds exactly once per key."""

    def __init__(self):
        self._held: set[str] = set()

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self._held:
            return None
        self._held.add(key)
        return True


@pytest.mark.asyncio(loop_scope="session")
async def test_cron_lease_prevents_double_fire(session):
    """Two invocations sharing a lease redis: only the first runs the body."""
    from contextlib import asynccontextmanager

    from server.worker import cleanup_retention

    calls = {"n": 0}

    @asynccontextmanager
    async def _counting_factory():
        calls["n"] += 1
        yield session

    lease = _LeaseRedis()
    ctx = {"session_factory": _counting_factory, "redis": lease}

    await cleanup_retention(ctx)
    await cleanup_retention(ctx)

    # First call acquires the lease and opens a session; second is skipped.
    assert calls["n"] == 1, "second invocation must not run the cron body"


# ── Task 12 Fold-in A: payload outputEvals populated ─────────────────────────

def test_run_engine_populates_output_evals():
    """run_engine assembles a payload whose outputEvals is non-empty.

    Fold-in A: process_run previously stored outputEvals: [].  With final
    outputs on the trajectories, the semantic/length checks run (judge is
    skipped, recorded in skipped_checks) and outputEvals is populated.
    """
    from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
    from agentdiff.trajectory import Trajectory as EngineTrajectory
    from server.engine_runner import run_engine

    structure = StructureDoc(
        agents=[AgentEntry(name="A", function="a", file="a.py", line=1)]
    )
    config = structure.model_dump()

    def _traj(tag, out):
        return {
            "side": tag,
            "test_case_id": "tc1",
            "payload": EngineTrajectory(
                test_case_id="tc1", version_tag=tag, input={}, final_output=out
            ).model_dump(mode="json"),
        }

    traj_data = [
        _traj("baseline", "hello world"),
        _traj("candidate", "hello world"),
    ]

    # Inject a fake embed via monkeypatch-free path: pass no llm_client, so the
    # judge is skipped; semantic may still be attempted.  We only assert that
    # an eval result exists for the test case.
    _verdict, _findings, payload = run_engine(config, None, traj_data, ["tc1"])
    assert payload["outputEvals"], "outputEvals must be populated by run_engine"
    assert payload["outputEvals"][0]["test_case_id"] == "tc1"
    # Judge is skipped server-side (no LLM client) — recorded, not silent.
    assert any(
        s["check"] == "judge"
        for s in payload["outputEvals"][0].get("skipped_checks", [])
    )


# ── Task 12 Fold-in B: compare runs once ─────────────────────────────────────

def test_run_engine_computes_comparison_once(monkeypatch):
    """run_engine calls compare_all exactly once (findings + payload reuse it)."""
    import server.engine_runner as er
    from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
    from agentdiff.trajectory import Trajectory as EngineTrajectory

    calls = {"n": 0}
    real_compare = er.compare_all

    def _spy(*args, **kwargs):
        calls["n"] += 1
        return real_compare(*args, **kwargs)

    monkeypatch.setattr(er, "compare_all", _spy)

    structure = StructureDoc(
        agents=[AgentEntry(name="A", function="a", file="a.py", line=1)]
    )
    config = structure.model_dump()
    traj_data = [
        {
            "side": side,
            "test_case_id": "tc1",
            "payload": EngineTrajectory(
                test_case_id="tc1", version_tag=side, input={}, final_output="x"
            ).model_dump(mode="json"),
        }
        for side in ("baseline", "candidate")
    ]

    er.run_engine(config, None, traj_data, ["tc1"])
    assert calls["n"] == 1, "compare_all must be computed exactly once per run"


# ── CORS origin regex (dev: dynamic localhost ports) ─────────────────────────

def _cors_test_app(origins: str, regex: str):
    """A minimal app wired with CORSMiddleware exactly as server.main does,
    driven by an explicit Settings instance."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from server.config import Settings

    settings = Settings(cors_origins=origins, cors_origin_regex=regex)
    app_ = FastAPI()
    app_.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    @app_.get("/ping")
    async def ping():  # pragma: no cover - route body irrelevant
        return {}

    return app_


def _preflight(client_app, origin: str):
    transport = ASGITransport(app=client_app)

    async def go():
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.options(
                "/ping",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )

    return go


@pytest.mark.asyncio(loop_scope="session")
async def test_cors_origin_regex_allows_dynamic_localhost_ports():
    """With the dev regex set, any localhost port passes preflight."""
    app_ = _cors_test_app(
        "http://localhost:5173", r"^http://(localhost|127\.0\.0\.1):\d+$"
    )
    r = await _preflight(app_, "http://localhost:64683")()
    assert r.headers.get("access-control-allow-origin") == "http://localhost:64683"


@pytest.mark.asyncio(loop_scope="session")
async def test_cors_origin_regex_still_rejects_foreign_origins():
    """The regex must not loosen CORS beyond localhost."""
    app_ = _cors_test_app(
        "http://localhost:5173", r"^http://(localhost|127\.0\.0\.1):\d+$"
    )
    r = await _preflight(app_, "http://evil.example.com")()
    assert r.headers.get("access-control-allow-origin") is None


@pytest.mark.asyncio(loop_scope="session")
async def test_cors_empty_regex_leaves_static_allowlist_only():
    """Default (empty) regex disables regex matching entirely — only the
    static allowlist passes, and dynamic ports are rejected."""
    app_ = _cors_test_app("http://localhost:5173", "")
    ok = await _preflight(app_, "http://localhost:5173")()
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = await _preflight(app_, "http://localhost:64683")()
    assert denied.headers.get("access-control-allow-origin") is None
