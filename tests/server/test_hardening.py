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
