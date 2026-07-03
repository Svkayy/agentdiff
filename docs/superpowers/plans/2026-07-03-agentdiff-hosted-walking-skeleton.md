# AgentDiff Hosted Walking Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn AgentDiff from a pip tool into the walking skeleton of a multi-tenant hosted SaaS: a CI collector POSTs a run to a containerized FastAPI + arq + Postgres + Redis backend, which stores it, runs the engine server-side, posts a Slack brief, and serves it to a Clerk-authed React dashboard.

**Architecture:** Out-of-band observability plane. A thin CI collector reuses the existing `capture/` + attribution code, then uploads trajectories + a precomputed `AttributionResult` to `POST /v1/runs`. The API (in-house API-key auth) stores the run and enqueues an arq job. The worker runs `compare_all` + `build_incident_summary` (no git needed server-side), writes findings, and posts Slack. The dashboard reads via Clerk-JWT-authed endpoints. Tenant boundary is the project; every query is project-scoped.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async (asyncpg), Alembic, arq (Redis), argon2-cffi, PyJWT (Clerk JWKS), Pydantic v2, Docker/docker-compose, existing React/Vite dashboard, pytest + pytest-asyncio + httpx.AsyncClient + fakeredis.

## Global Constraints

- Python 3.11. Reuse the existing engine (`compare`, `stats`, `attribution`, `incident/`) unchanged — never fork it.
- Attribution runs client-side (CI has git); the server never needs the customer's repo.
- Degrade, never swallow: a failed run is visible (`status=failed`, error stored, shown in dashboard); Slack/webhook failures never fail the run.
- Multi-tenant isolation: every data query is scoped by `project_id` (project → `org_id`). Cross-tenant access returns 404, never another tenant's data.
- Ingest auth = in-house project API keys (`adk_` prefix, argon2-hashed). Dashboard auth = Clerk JWT. Never mix them.
- Secrets (Slack bot token) encrypted at rest; never logged.
- All new IDs are UUID v4. All timestamps UTC.

---

## Phase 1 — Ingestion path

Deliverable: a CI collector can authenticate with a project API key and POST a run; the API validates, stores trajectories + attribution, and enqueues a job. Testable end to end at the API boundary, including cross-tenant isolation.

### Task 1.1: Server scaffolding, config, async DB session, compose infra

**Files:**
- Create: `server/__init__.py`, `server/config.py`, `server/db.py`
- Create: `docker-compose.yml`
- Modify: `pyproject.toml` (add deps + optional-dependencies group `server`)
- Test: `tests/server/__init__.py`, `tests/server/conftest.py`, `tests/server/test_db.py`

**Interfaces:**
- Produces: `server.config.Settings` (pydantic-settings) with `database_url: str`, `redis_url: str`, `clerk_jwks_url: str`, `clerk_issuer: str`, `secret_encryption_key: str`. `server.db.Base` (DeclarativeBase), `server.db.engine`, `server.db.async_session` (async_sessionmaker), `server.db.get_session()` FastAPI dependency yielding `AsyncSession`.

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add an optional group:

```toml
[project.optional-dependencies]
server = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "arq>=0.25",
  "argon2-cffi>=23.1",
  "pyjwt[crypto]>=2.8",
  "pydantic-settings>=2.2",
  "cryptography>=42",
]
server-dev = [
  "pytest-asyncio>=0.23",
  "fakeredis>=2.21",
  "httpx>=0.27",
]
```

Install: `pip install -e ".[server,server-dev]"`

- [ ] **Step 2: Write config**

`server/config.py`:

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTDIFF_", extra="ignore")

    database_url: str = "postgresql+asyncpg://agentdiff:agentdiff@localhost:5432/agentdiff"
    redis_url: str = "redis://localhost:6379"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    # 32-byte urlsafe base64 Fernet key for encrypting Slack tokens at rest.
    secret_encryption_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: Write DB module**

`server/db.py`:

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from server.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session
```

- [ ] **Step 4: Write docker-compose infra (postgres + redis for now)**

`docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: agentdiff
      POSTGRES_PASSWORD: agentdiff
      POSTGRES_DB: agentdiff
    ports: ["5432:5432"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentdiff"]
      interval: 5s
      timeout: 5s
      retries: 10
  redis:
    image: redis:7
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10
```

- [ ] **Step 5: Write the test conftest (async engine + rollback per test)**

`tests/server/conftest.py`:

```python
import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db import Base
import server.models  # noqa: F401  (registers all tables on Base.metadata)

TEST_DB_URL = "postgresql+asyncpg://agentdiff:agentdiff@localhost:5432/agentdiff_test"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _engine():
    engine = create_async_engine(TEST_DB_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(_engine) -> AsyncSession:
    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
```

Create the test database first: `docker compose up -d postgres && docker compose exec postgres createdb -U agentdiff agentdiff_test`

- [ ] **Step 6: Write a DB connectivity test**

`tests/server/test_db.py`:

```python
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_session_connects(session):
    result = await session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
```

- [ ] **Step 7: Run it (fails until models import resolves), then passes**

Run: `pytest tests/server/test_db.py -v`
Expected after Task 1.2 exists: PASS. (This test also proves `server.models` imports cleanly.)

- [ ] **Step 8: Commit**

```bash
git add server/ docker-compose.yml pyproject.toml tests/server/
git commit -m "feat(server): scaffolding, async db session, compose infra"
```

### Task 1.2: SQLAlchemy models + Alembic initial migration

**Files:**
- Create: `server/models.py`
- Create: `server/migrations/` (Alembic env), `alembic.ini`
- Test: `tests/server/test_models.py`

**Interfaces:**
- Produces: models `Org, User, Project, ApiKey, SlackConfig, Run, Trajectory, Finding` on `server.db.Base`. `Run.status` in {"pending","processing","done","failed"}. `Run` has `attribution: dict | None` (JSONB) and `config: dict` (JSONB). `Trajectory.payload: dict` (JSONB). `Finding` mirrors `agentdiff.incident.findings.IncidentFinding` fields.

- [ ] **Step 1: Write the failing test**

`tests/server/test_models.py`:

```python
import uuid
import pytest
from server.models import Org, Project, ApiKey, Run, Trajectory, Finding


@pytest.mark.asyncio
async def test_run_persists_with_trajectories_and_findings(session):
    org = Org(name="Acme")
    project = Project(org=org, name="support-bot")
    run = Run(
        project=project,
        idempotency_key="idem-1",
        baseline_ref="origin/main",
        candidate_ref="working",
        tier="hermetic",
        config={"agents": []},
        status="pending",
    )
    run.trajectories.append(Trajectory(side="baseline", test_case_id="tc1", payload={"events": []}))
    session.add(run)
    await session.commit()

    assert isinstance(run.id, uuid.UUID)
    assert run.status == "pending"
    assert run.trajectories[0].side == "baseline"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/server/test_models.py -v`
Expected: FAIL (ImportError: cannot import name 'Org').

- [ ] **Step 3: Write the models**

`server/models.py`:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from server.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    clerk_org_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=_now)
    projects: Mapped[list["Project"]] = relationship(back_populates="org")
    users: Mapped[list["User"]] = relationship(back_populates="org")


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=_now)
    org: Mapped[Org] = relationship(back_populates="users")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=_now)
    org: Mapped[Org] = relationship(back_populates="projects")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="project")
    slack_config: Mapped["SlackConfig | None"] = relationship(back_populates="project", uselist=False)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    key_hash: Mapped[str] = mapped_column(Text)
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    project: Mapped[Project] = relationship(back_populates="api_keys")


class SlackConfig(Base):
    __tablename__ = "slack_configs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), unique=True)
    channel_id: Mapped[str] = mapped_column(String(64))
    bot_token_encrypted: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=True)
    project: Mapped[Project] = relationship(back_populates="slack_config")


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    baseline_ref: Mapped[str] = mapped_column(String(255))
    candidate_ref: Mapped[str] = mapped_column(String(255))
    tier: Mapped[str] = mapped_column(String(16))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    attribution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    project: Mapped[Project] = relationship()
    trajectories: Mapped[list["Trajectory"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    findings: Mapped[list["Finding"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Trajectory(Base):
    __tablename__ = "trajectories"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    side: Mapped[str] = mapped_column(String(16))
    test_case_id: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB)
    run: Mapped[Run] = relationship(back_populates="trajectories")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    test_case_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(64))
    impact_summary: Mapped[str] = mapped_column(Text)
    cause_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    cause_rule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cause_hunk: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    run: Mapped[Run] = relationship(back_populates="findings")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/server/test_models.py tests/server/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Initialize Alembic for real deploys**

Run: `alembic init server/migrations`
Edit `alembic.ini` `sqlalchemy.url` to empty and set it from env in `server/migrations/env.py`:

```python
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from server.config import get_settings
from server.db import Base
import server.models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_online():
    connectable = create_async_engine(get_settings().database_url)

    async def do_run():
        async with connectable.connect() as conn:
            await conn.run_sync(lambda c: context.configure(connection=c, target_metadata=target_metadata))
            await conn.run_sync(lambda _: context.run_migrations())

    asyncio.run(do_run())


run_migrations_online()
```

Generate the initial migration: `alembic revision --autogenerate -m "initial schema"`

- [ ] **Step 6: Commit**

```bash
git add server/models.py server/migrations/ alembic.ini tests/server/test_models.py
git commit -m "feat(server): data model + initial alembic migration"
```

### Task 1.3: API-key generation, hashing, and the auth dependency

**Files:**
- Create: `server/security.py`, `server/deps.py`
- Test: `tests/server/test_apikey_auth.py`

**Interfaces:**
- Produces: `security.generate_api_key() -> tuple[str, str, str]` returning `(full_key, prefix, key_hash)` where `full_key` starts with `adk_`. `security.verify_api_key(full_key, key_hash) -> bool`. `deps.get_project_from_api_key(authorization, session) -> Project` (FastAPI dependency) raising `HTTPException(401)` on missing/bad/revoked key; touches `last_used_at`.

- [ ] **Step 1: Write the failing test**

`tests/server/test_apikey_auth.py`:

```python
import pytest
from fastapi import HTTPException
from server import security
from server.deps import get_project_from_api_key
from server.models import Org, Project, ApiKey


def test_generate_and_verify_roundtrip():
    full, prefix, key_hash = security.generate_api_key()
    assert full.startswith("adk_")
    assert full.startswith(prefix)
    assert security.verify_api_key(full, key_hash) is True
    assert security.verify_api_key("adk_wrong", key_hash) is False


@pytest.mark.asyncio
async def test_dependency_resolves_project(session):
    org = Org(name="Acme"); project = Project(org=org, name="p")
    full, prefix, key_hash = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=key_hash, prefix=prefix))
    await session.commit()

    resolved = await get_project_from_api_key(f"Bearer {full}", session)
    assert resolved.id == project.id


@pytest.mark.asyncio
async def test_dependency_rejects_bad_key(session):
    with pytest.raises(HTTPException) as exc:
        await get_project_from_api_key("Bearer adk_nope", session)
    assert exc.value.status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/server/test_apikey_auth.py -v`
Expected: FAIL (ModuleNotFoundError: server.security).

- [ ] **Step 3: Implement security + deps**

`server/security.py`:

```python
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def generate_api_key() -> tuple[str, str, str]:
    body = secrets.token_urlsafe(32)
    full = f"adk_{body}"
    prefix = full[:12]
    return full, prefix, _ph.hash(full)


def verify_api_key(full_key: str, key_hash: str) -> bool:
    try:
        return _ph.verify(key_hash, full_key)
    except VerifyMismatchError:
        return False
    except Exception:
        return False
```

`server/deps.py`:

```python
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import security
from server.db import get_session
from server.models import ApiKey, Project


async def get_project_from_api_key(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Project:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    full = authorization.removeprefix("Bearer ").strip()
    prefix = full[:12]
    rows = (await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))).scalars().all()
    for key in rows:
        if key.revoked_at is None and security.verify_api_key(full, key.key_hash):
            key.last_used_at = datetime.now(timezone.utc)
            await session.commit()
            return (await session.execute(select(Project).where(Project.id == key.project_id))).scalar_one()
    raise HTTPException(status_code=401, detail="invalid api key")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/server/test_apikey_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/security.py server/deps.py tests/server/test_apikey_auth.py
git commit -m "feat(server): api-key generation, hashing, auth dependency"
```

### Task 1.4: Ingest endpoint `POST /v1/runs` (schemas, persistence, idempotency, enqueue seam)

**Files:**
- Create: `server/schemas.py`, `server/routes/__init__.py`, `server/routes/ingest.py`, `server/main.py`
- Test: `tests/server/test_ingest.py`

**Interfaces:**
- Consumes: `deps.get_project_from_api_key`, models.
- Produces: `POST /v1/runs` accepting `RunUpload` → `202 {"run_id": str, "status": "pending"}`. `RunUpload = {idempotency_key, baseline_ref, candidate_ref, tier, config: dict, attribution: dict | None, trajectories: [{side, test_case_id, payload}]}`. App exposes `app.state.enqueue(run_id: str)` (awaitable) — a seam the worker task fills in Phase 2; default is a no-op so Phase 1 tests run without Redis.

- [ ] **Step 1: Write the failing test**

`tests/server/test_ingest.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from server.main import app
from server.db import get_session
from server import security
from server.models import Org, Project, ApiKey


@pytest.fixture
def payload():
    return {
        "idempotency_key": "idem-1", "baseline_ref": "origin/main",
        "candidate_ref": "working", "tier": "hermetic", "config": {"agents": []},
        "attribution": None,
        "trajectories": [{"side": "baseline", "test_case_id": "tc1", "payload": {"events": []}}],
    }


@pytest.fixture
async def api_key(session):
    org = Org(name="Acme"); project = Project(org=org, name="p")
    full, prefix, kh = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=kh, prefix=prefix))
    await session.commit()
    return full, project.id


@pytest.mark.asyncio
async def test_post_run_returns_202_and_persists(session, api_key, payload):
    full, project_id = api_key
    app.dependency_overrides[get_session] = lambda: session
    enqueued = []
    app.state.enqueue = lambda rid: enqueued.append(rid)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/v1/runs", json=payload, headers={"Authorization": f"Bearer {full}"})
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    assert enqueued == [r.json()["run_id"]]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_same_run(session, api_key, payload):
    full, _ = api_key
    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = lambda rid: None
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r1 = await c.post("/v1/runs", json=payload, headers={"Authorization": f"Bearer {full}"})
        r2 = await c.post("/v1/runs", json=payload, headers={"Authorization": f"Bearer {full}"})
    assert r1.json()["run_id"] == r2.json()["run_id"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bad_key_rejected(session, payload):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/v1/runs", json=payload, headers={"Authorization": "Bearer adk_no"})
    assert r.status_code == 401
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/server/test_ingest.py -v`
Expected: FAIL (ModuleNotFoundError: server.main).

- [ ] **Step 3: Write schemas**

`server/schemas.py`:

```python
from pydantic import BaseModel, Field


class TrajectoryIn(BaseModel):
    side: str
    test_case_id: str
    payload: dict


class RunUpload(BaseModel):
    idempotency_key: str
    baseline_ref: str
    candidate_ref: str
    tier: str = "hermetic"
    config: dict = Field(default_factory=dict)
    attribution: dict | None = None
    trajectories: list[TrajectoryIn]


class RunAccepted(BaseModel):
    run_id: str
    status: str
```

- [ ] **Step 4: Write the ingest route**

`server/routes/ingest.py`:

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db import get_session
from server.deps import get_project_from_api_key
from server.models import Project, Run, Trajectory
from server.schemas import RunAccepted, RunUpload

router = APIRouter()


@router.post("/v1/runs", status_code=202, response_model=RunAccepted)
async def create_run(
    body: RunUpload,
    request: Request,
    project: Project = Depends(get_project_from_api_key),
    session: AsyncSession = Depends(get_session),
) -> RunAccepted:
    existing = (
        await session.execute(
            select(Run).where(
                Run.project_id == project.id, Run.idempotency_key == body.idempotency_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return RunAccepted(run_id=str(existing.id), status=existing.status)

    run = Run(
        project_id=project.id, idempotency_key=body.idempotency_key,
        baseline_ref=body.baseline_ref, candidate_ref=body.candidate_ref,
        tier=body.tier, config=body.config, attribution=body.attribution, status="pending",
    )
    for t in body.trajectories:
        run.trajectories.append(Trajectory(side=t.side, test_case_id=t.test_case_id, payload=t.payload))
    session.add(run)
    await session.commit()

    await _maybe_enqueue(request, str(run.id))
    return RunAccepted(run_id=str(run.id), status="pending")


async def _maybe_enqueue(request: Request, run_id: str) -> None:
    enqueue = getattr(request.app.state, "enqueue", None)
    if enqueue is None:
        return
    result = enqueue(run_id)
    if hasattr(result, "__await__"):
        await result
```

- [ ] **Step 5: Write the app**

`server/main.py`:

```python
from fastapi import FastAPI
from server.routes import ingest

app = FastAPI(title="AgentDiff Hosted")
app.state.enqueue = None
app.include_router(ingest.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

`server/routes/__init__.py`: empty file.

- [ ] **Step 6: Run to verify it passes**

Run: `pytest tests/server/test_ingest.py -v`
Expected: PASS (all three).

- [ ] **Step 7: Commit**

```bash
git add server/schemas.py server/routes/ server/main.py tests/server/test_ingest.py
git commit -m "feat(server): POST /v1/runs ingest with idempotency + enqueue seam"
```

---

## Phase 2 — Processing path

Deliverable: an enqueued run is processed by the arq worker — the engine runs server-side, findings are written, status/verdict set, and a Slack brief posts when configured. Testable by calling the task directly and via an ingest→process→read-back e2e.

### Task 2.1: arq worker wiring + real enqueue

**Files:**
- Create: `server/worker.py`
- Modify: `server/main.py` (wire `app.state.enqueue` to the arq pool on startup)
- Test: `tests/server/test_worker_enqueue.py`

**Interfaces:**
- Produces: `worker.WorkerSettings` (arq) with `functions=[process_run]`, `redis_settings` from `settings.redis_url`. `worker.make_enqueue(pool)` → an async `enqueue(run_id)` calling `pool.enqueue_job("process_run", run_id)`. `worker.process_run(ctx, run_id: str)` (body filled in Task 2.2).

- [ ] **Step 1: Write the failing test (enqueue uses fakeredis)**

`tests/server/test_worker_enqueue.py`:

```python
import pytest
from fakeredis import aioredis as fakeredis_aio
from arq import ArqRedis
from server.worker import make_enqueue


@pytest.mark.asyncio
async def test_enqueue_puts_job(monkeypatch):
    fake = fakeredis_aio.FakeRedis()
    pool = ArqRedis(connection_pool=fake.connection_pool)
    enqueue = make_enqueue(pool)
    job = await enqueue("run-123")
    assert job is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/server/test_worker_enqueue.py -v`
Expected: FAIL (ModuleNotFoundError: server.worker).

- [ ] **Step 3: Write the worker skeleton + enqueue**

`server/worker.py`:

```python
from arq.connections import RedisSettings

from server.config import get_settings


def make_enqueue(pool):
    async def enqueue(run_id: str):
        return await pool.enqueue_job("process_run", run_id)

    return enqueue


async def process_run(ctx, run_id: str) -> None:
    # Body implemented in Task 2.2.
    return None


class WorkerSettings:
    functions = [process_run]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
```

- [ ] **Step 4: Wire enqueue into the app lifespan**

Replace `server/main.py` with:

```python
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from server.config import get_settings
from server.routes import ingest
from server.worker import make_enqueue


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    app.state.enqueue = make_enqueue(pool)
    yield
    await pool.aclose()


app = FastAPI(title="AgentDiff Hosted", lifespan=lifespan)
app.state.enqueue = None
app.include_router(ingest.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/server/test_worker_enqueue.py tests/server/test_ingest.py -v`
Expected: PASS (ingest tests still pass — they override `app.state.enqueue`).

- [ ] **Step 6: Commit**

```bash
git add server/worker.py server/main.py tests/server/test_worker_enqueue.py
git commit -m "feat(server): arq worker wiring + real enqueue via app lifespan"
```

### Task 2.2: `process_run` runs the engine server-side and writes findings

**Files:**
- Modify: `server/worker.py` (`process_run` body + a `run_engine` helper)
- Create: `server/engine_runner.py`
- Test: `tests/server/test_worker.py`

**Interfaces:**
- Consumes: `agentdiff.storage.load_trajectory_set` shape (build `TrajectorySet` from stored trajectories), `agentdiff.compare.compare_all`, `agentdiff.incident.findings.build_incident_summary`, `agentdiff.attribution.engine.AttributionResult`, `agentdiff.structure.structure_yaml` doc validation.
- Produces: `engine_runner.process_run_sync(run_row, trajectory_rows) -> tuple[str, list[dict]]` returning `(verdict, finding_dicts)`. `worker.process_run(ctx, run_id)` loads the run, calls the helper, writes findings, sets status/verdict/error.

- [ ] **Step 1: Write the failing test**

`tests/server/test_worker.py` builds a run whose baseline fires an agent and candidate does not, then asserts findings are written. (Reuses the fixture shape from the engine's own tests.)

```python
import pytest
from sqlalchemy import select
from server.models import Org, Project, Run, Trajectory, Finding
from server.worker import process_run


def _traj(side, fired):
    # Minimal trajectory payload the engine's TrajectorySet loader accepts:
    # one test case "tc1" where agent "fact_checker" fires (fired=True) or not.
    events = []
    if fired:
        events.append({"type": "agent_invocation", "agent": "fact_checker", "function": "fact_checker"})
    return {"schema_version": 1, "test_case_id": "tc1", "version": side, "events": events}


@pytest.mark.asyncio
async def test_process_run_writes_findings(session):
    org = Org(name="Acme"); project = Project(org=org, name="p")
    config = {"agents": [{"name": "Fact Checker", "function": "fact_checker"}]}
    run = Run(project=project, idempotency_key="i", baseline_ref="main",
              candidate_ref="working", tier="hermetic", config=config, status="pending")
    for s, fired in (("baseline", True), ("baseline", True), ("candidate", False), ("candidate", False)):
        run.trajectories.append(Trajectory(side=s, test_case_id="tc1", payload=_traj(s, fired)))
    session.add(run); await session.commit()

    class Ctx(dict): pass
    await process_run({"session_factory": _factory(session)}, str(run.id))

    await session.refresh(run)
    findings = (await session.execute(select(Finding).where(Finding.run_id == run.id))).scalars().all()
    assert run.status == "done"
    assert run.verdict in {"warn", "fail"}
    assert any("fact" in f.test_case_id or f.metric == "invocation_rate" for f in findings)


def _factory(session):
    # In tests we inject the open session; production uses async_session().
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def factory():
        yield session
    return factory
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/server/test_worker.py -v`
Expected: FAIL (`process_run` returns None, writes nothing).

- [ ] **Step 3: Write the engine runner**

`server/engine_runner.py`:

```python
from agentdiff.compare import compare_all
from agentdiff.incident.findings import build_incident_summary
from agentdiff.trajectory import Trajectory as EngineTrajectory, TrajectorySet
from agentdiff.structure.structure_yaml import StructureDoc
from agentdiff.attribution.engine import AttributionResult


def _to_set(rows, side: str) -> TrajectorySet:
    trajs = [EngineTrajectory.model_validate(r.payload) for r in rows if r.side == side]
    return TrajectorySet(version=side, trajectories=trajs)


def process_run_sync(run_row, trajectory_rows) -> tuple[str, list[dict]]:
    structure = StructureDoc.model_validate(run_row.config)
    baseline = _to_set(trajectory_rows, "baseline")
    candidate = _to_set(trajectory_rows, "candidate")
    test_case_ids = sorted({r.test_case_id for r in trajectory_rows})
    comparison = compare_all(baseline, candidate, structure, test_case_ids)

    attribution = None
    if run_row.attribution:
        attribution = AttributionResult.model_validate(run_row.attribution)

    summary = build_incident_summary(comparison, attribution, input_count=len(test_case_ids))
    finding_dicts = [f.model_dump() for f in summary.findings]
    return summary.verdict, finding_dicts
```

Note: `run_row.config` is exactly the `StructureDoc.model_dump()` the collector produced (Task 3.3), so `StructureDoc.model_validate(run_row.config)` is a lossless round-trip — no new parser needed.

- [ ] **Step 4: Fill in `process_run`**

Replace `process_run` in `server/worker.py`:

```python
from sqlalchemy import select

from server.db import async_session
from server.engine_runner import process_run_sync
from server.models import Finding, Run, Trajectory
from server.notify import maybe_post_slack  # added in Task 2.3


def _session_factory(ctx):
    return ctx.get("session_factory", async_session)


async def process_run(ctx, run_id: str) -> None:
    factory = _session_factory(ctx)
    async with factory() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.status = "processing"
        await session.commit()
        rows = (await session.execute(select(Trajectory).where(Trajectory.run_id == run.id))).scalars().all()
        try:
            verdict, findings = process_run_sync(run, rows)
        except Exception as exc:  # engine failure is visible, not silent
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            await session.commit()
            return
        for fd in findings:
            session.add(Finding(run_id=run.id, **fd))
        run.status = "done"
        run.verdict = verdict
        await session.commit()
        await maybe_post_slack(session, run, findings, verdict)
```

Note: import `maybe_post_slack` only after Task 2.3 creates `server/notify.py`. To keep Task 2.2 independently green, temporarily define a no-op `async def maybe_post_slack(*a, **k): return None` in `server/notify.py` now and flesh it out in 2.3.

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/server/test_worker.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add server/engine_runner.py server/worker.py server/notify.py tests/server/test_worker.py
git commit -m "feat(server): process_run runs engine server-side, writes findings"
```

### Task 2.3: Slack notification from the worker (degrade, never swallow)

**Files:**
- Create: `server/notify.py` (real body), `server/crypto.py`
- Test: `tests/server/test_slack_worker.py`

**Interfaces:**
- Consumes: `agentdiff.incident.findings.IncidentSummary/IncidentFinding`, `agentdiff.incident.renderers.render_slack_payload`, `agentdiff.incident.slack.SlackClient`, `SlackConfig` model.
- Produces: `crypto.encrypt(plaintext) -> str`, `crypto.decrypt(token) -> str` (Fernet). `notify.maybe_post_slack(session, run, finding_dicts, verdict) -> None` — posts when a `SlackConfig` exists, is enabled, and verdict in {"warn","fail"}; any Slack error is logged and swallowed (never raised).

- [ ] **Step 1: Write the failing test**

`tests/server/test_slack_worker.py`:

```python
import pytest
from server.models import Org, Project, SlackConfig, Run
from server import crypto, notify


class _RecordingSlack:
    def __init__(self, token, **kw): self.posted = []
    def post_payload(self, channel, message):
        self.posted.append((channel, message))
        from agentdiff.incident.delivery import DeliveryResult
        return DeliveryResult(ok=True, integration="slack")


class _FailingSlack:
    def __init__(self, token, **kw): pass
    def post_payload(self, channel, message):
        raise RuntimeError("slack exploded")


@pytest.mark.asyncio
async def test_slack_posts_on_fail(session, monkeypatch):
    org = Org(name="A"); project = Project(org=org, name="p")
    session.add(SlackConfig(project=project, channel_id="C1",
                            bot_token_encrypted=crypto.encrypt("xoxb-t"), enabled=True))
    run = Run(project=project, idempotency_key="i", baseline_ref="m",
              candidate_ref="w", tier="hermetic", config={}, status="done", verdict="fail")
    session.add(run); await session.commit()
    rec = _RecordingSlack("x")
    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: rec)

    findings = [{"test_case_id": "tc1", "title": "Fact Checker invocation changed",
                 "verdict": "fail", "metric": "invocation_rate",
                 "impact_summary": "fired 100% -> 0%", "cause_path": "a.py",
                 "cause_rule": "code_change", "cause_hunk": None, "explanation": None}]
    await notify.maybe_post_slack(session, run, findings, "fail")
    assert len(rec.posted) == 1


@pytest.mark.asyncio
async def test_slack_failure_is_swallowed(session, monkeypatch):
    org = Org(name="A"); project = Project(org=org, name="p")
    session.add(SlackConfig(project=project, channel_id="C1",
                            bot_token_encrypted=crypto.encrypt("xoxb-t"), enabled=True))
    run = Run(project=project, idempotency_key="i2", baseline_ref="m",
              candidate_ref="w", tier="hermetic", config={}, status="done", verdict="fail")
    session.add(run); await session.commit()
    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _FailingSlack(token))
    # Must not raise.
    await notify.maybe_post_slack(session, run, [], "fail")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/server/test_slack_worker.py -v`
Expected: FAIL (server.crypto missing / notify is a no-op).

- [ ] **Step 3: Write crypto + notify**

`server/crypto.py`:

```python
from cryptography.fernet import Fernet
from server.config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().secret_encryption_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
```

`server/notify.py` (replace the no-op):

```python
import logging

from sqlalchemy import select

from agentdiff.incident.findings import IncidentFinding, IncidentSummary
from agentdiff.incident.renderers import render_slack_payload
from agentdiff.incident.slack import SlackClient

from server import crypto
from server.models import SlackConfig

log = logging.getLogger("agentdiff.notify")


async def maybe_post_slack(session, run, finding_dicts, verdict) -> None:
    if verdict not in {"warn", "fail"}:
        return
    cfg = (
        await session.execute(select(SlackConfig).where(SlackConfig.project_id == run.project_id))
    ).scalar_one_or_none()
    if cfg is None or not cfg.enabled:
        return
    summary = IncidentSummary(
        verdict=verdict,
        findings=[IncidentFinding.model_validate(fd) for fd in finding_dicts],
    )
    payload = render_slack_payload(summary)
    try:
        token = crypto.decrypt(cfg.bot_token_encrypted)
        SlackClient(token).post_payload(cfg.channel_id, payload)
    except Exception as exc:  # degrade, never swallow the RUN — but never raise
        log.warning("slack delivery failed for run %s: %s", run.id, type(exc).__name__)
```

For tests, set `AGENTDIFF_SECRET_ENCRYPTION_KEY` to a valid Fernet key in `tests/server/conftest.py` (add: `os.environ.setdefault("AGENTDIFF_SECRET_ENCRYPTION_KEY", Fernet.generate_key().decode())` at import top).

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/server/test_slack_worker.py -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add server/crypto.py server/notify.py tests/server/test_slack_worker.py tests/server/conftest.py
git commit -m "feat(server): worker Slack notification with encrypted token, degrade on failure"
```

### Task 2.4: End-to-end ingest → process → read-back

**Files:**
- Test: `tests/server/test_e2e.py`

**Interfaces:**
- Consumes: everything above. Calls `create_run` via HTTP with an inline enqueue that invokes `process_run` synchronously, then asserts findings persisted and status `done`.

- [ ] **Step 1: Write the e2e test**

`tests/server/test_e2e.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from server.main import app
from server.db import get_session
from server.worker import process_run
from server import security
from server.models import Org, Project, ApiKey, Run, Finding


@pytest.mark.asyncio
async def test_ingest_to_findings(session):
    org = Org(name="Acme"); project = Project(org=org, name="p")
    full, prefix, kh = security.generate_api_key()
    session.add(ApiKey(project=project, key_hash=kh, prefix=prefix)); await session.commit()

    async def inline_enqueue(run_id):
        await process_run({"session_factory": _factory(session)}, run_id)

    app.dependency_overrides[get_session] = lambda: session
    app.state.enqueue = inline_enqueue
    body = {
        "idempotency_key": "e2e-1", "baseline_ref": "main", "candidate_ref": "working",
        "tier": "hermetic", "config": {"agents": [{"name": "Fact Checker", "function": "fact_checker"}]},
        "attribution": None,
        "trajectories": [
            {"side": "baseline", "test_case_id": "tc1",
             "payload": {"schema_version": 1, "test_case_id": "tc1", "version": "baseline",
                         "events": [{"type": "agent_invocation", "agent": "fact_checker", "function": "fact_checker"}]}},
            {"side": "candidate", "test_case_id": "tc1",
             "payload": {"schema_version": 1, "test_case_id": "tc1", "version": "candidate", "events": []}},
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/v1/runs", json=body, headers={"Authorization": f"Bearer {full}"})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
    assert run.status == "done"
    findings = (await session.execute(select(Finding).where(Finding.run_id == run_id))).scalars().all()
    assert len(findings) >= 1
    app.dependency_overrides.clear()


def _factory(session):
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def factory():
        yield session
    return factory
```

- [ ] **Step 2: Run it**

Run: `pytest tests/server/test_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/server/test_e2e.py
git commit -m "test(server): end-to-end ingest -> process -> findings"
```

---

## Phase 3 — Product surface

Deliverable: a Clerk-authed dashboard user sees runs/findings scoped to their project; the CI collector uploads; docker-compose brings all five services up. Testable via read-endpoint auth + isolation tests, a collector unit test, and a compose smoke.

### Task 3.1: Clerk JWT verification dependency

**Files:**
- Create: `server/clerk.py`
- Modify: `server/deps.py` (`get_user_ctx`)
- Test: `tests/server/test_clerk_auth.py`

**Interfaces:**
- Produces: `clerk.verify_token(token, jwks, issuer) -> dict` (claims) raising `ValueError` on bad token. `deps.get_user_ctx(authorization, session) -> tuple[User, Org]` — verifies the Clerk JWT, upserts `Org` (by `clerk_org_id`) and `User` (by `clerk_user_id`) on first sight, returns them. `HTTPException(401)` on invalid token.

- [ ] **Step 1: Write the failing test (sign a token with a local RSA key)**

`tests/server/test_clerk_auth.py`:

```python
import jwt, pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from server import clerk
from server.deps import get_user_ctx
from fastapi import HTTPException


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


def test_verify_token_ok():
    priv, pub = _keypair()
    token = jwt.encode({"sub": "user_1", "org_id": "org_1", "iss": "https://clerk.test"},
                       priv, algorithm="RS256")
    claims = clerk.verify_token(token, jwks_pubkey=pub, issuer="https://clerk.test")
    assert claims["sub"] == "user_1"


def test_verify_token_bad_issuer():
    priv, pub = _keypair()
    token = jwt.encode({"sub": "u", "iss": "https://evil"}, priv, algorithm="RS256")
    with pytest.raises(ValueError):
        clerk.verify_token(token, jwks_pubkey=pub, issuer="https://clerk.test")


@pytest.mark.asyncio
async def test_get_user_ctx_upserts(session, monkeypatch):
    priv, pub = _keypair()
    token = jwt.encode({"sub": "user_9", "org_id": "org_9", "email": "a@b.co",
                        "iss": "https://clerk.test"}, priv, algorithm="RS256")
    monkeypatch.setattr(clerk, "load_jwks_pubkey", lambda url: pub)
    monkeypatch.setenv("AGENTDIFF_CLERK_ISSUER", "https://clerk.test")
    user, org = await get_user_ctx(f"Bearer {token}", session)
    assert user.clerk_user_id == "user_9"
    assert org.clerk_org_id == "org_9"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/server/test_clerk_auth.py -v`
Expected: FAIL (server.clerk missing).

- [ ] **Step 3: Implement clerk verification**

`server/clerk.py`:

```python
import jwt


def load_jwks_pubkey(jwks_url: str) -> str:
    # Fetch the Clerk signing key. Isolated here so tests monkeypatch it with a
    # local public key instead of hitting the network.
    from jwt import PyJWKClient
    return PyJWKClient(jwks_url).get_signing_keys()[0].key


def verify_token(token: str, jwks_pubkey, issuer: str) -> dict:
    try:
        return jwt.decode(
            token, jwks_pubkey, algorithms=["RS256"], issuer=issuer,
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        raise ValueError(str(exc)) from exc
```

Add to `server/deps.py`:

```python
from server import clerk
from server.config import get_settings
from server.models import Org, User


async def get_user_ctx(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> tuple[User, Org]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    settings = get_settings()
    try:
        pub = clerk.load_jwks_pubkey(settings.clerk_jwks_url)
        claims = clerk.verify_token(token, pub, settings.clerk_issuer)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid clerk token") from exc

    clerk_org_id = claims.get("org_id") or f"personal_{claims['sub']}"
    org = (await session.execute(select(Org).where(Org.clerk_org_id == clerk_org_id))).scalar_one_or_none()
    if org is None:
        org = Org(clerk_org_id=clerk_org_id, name=claims.get("org_slug", "personal"))
        session.add(org); await session.flush()
    user = (await session.execute(select(User).where(User.clerk_user_id == claims["sub"]))).scalar_one_or_none()
    if user is None:
        user = User(org_id=org.id, clerk_user_id=claims["sub"], email=claims.get("email", ""))
        session.add(user)
    await session.commit()
    return user, org
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/server/test_clerk_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/clerk.py server/deps.py tests/server/test_clerk_auth.py
git commit -m "feat(server): Clerk JWT verification + user/org upsert dependency"
```

### Task 3.2: Read endpoints + Slack config endpoint (project-scoped, isolation-tested)

**Files:**
- Create: `server/routes/reads.py`
- Modify: `server/main.py` (include router)
- Test: `tests/server/test_reads.py`, `tests/server/test_isolation.py`

**Interfaces:**
- Consumes: `deps.get_user_ctx`, models, `crypto.encrypt`.
- Produces: `GET /v1/projects` → projects in caller's org. `GET /v1/projects/{id}/runs` → runs (404 if project not in org). `GET /v1/runs/{id}` → run + findings (404 if not in org). `PUT /v1/projects/{id}/slack` body `{channel_id, bot_token}` → stores encrypted config.

- [ ] **Step 1: Write the failing tests (reads + isolation)**

`tests/server/test_reads.py` asserts a user sees their org's project and its runs. `tests/server/test_isolation.py` asserts user in org A gets 404 for a run in org B. Both override `get_user_ctx` to return a seeded `(user, org)`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from server.main import app
from server.db import get_session
from server.deps import get_user_ctx
from server.models import Org, Project, Run


async def _client(session, user_ctx):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = lambda: user_ctx
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_lists_only_own_org_runs(session):
    orgA = Org(name="A"); pA = Project(org=orgA, name="pa")
    runA = Run(project=pA, idempotency_key="a", baseline_ref="m", candidate_ref="w",
               tier="hermetic", config={}, status="done", verdict="pass")
    orgB = Org(name="B"); pB = Project(org=orgB, name="pb")
    session.add_all([runA, pB]); await session.commit()

    from server.models import User
    userA = User(org_id=orgA.id, clerk_user_id="ua", email="a@a")
    session.add(userA); await session.commit()

    async with await _client(session, (userA, orgA)) as c:
        r = await c.get(f"/v1/projects/{pA.id}/runs")
        assert r.status_code == 200
        assert len(r.json()) == 1
        # Cross-org project -> 404
        r2 = await c.get(f"/v1/projects/{pB.id}/runs")
        assert r2.status_code == 404
    app.dependency_overrides.clear()
```

`tests/server/test_isolation.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from server.main import app
from server.db import get_session
from server.deps import get_user_ctx
from server.models import Org, Project, Run, User


@pytest.mark.asyncio
async def test_cannot_read_other_orgs_run(session):
    orgA = Org(name="A"); userA = User(org=orgA, clerk_user_id="ua", email="a@a")
    orgB = Org(name="B"); pB = Project(org=orgB, name="pb")
    runB = Run(project=pB, idempotency_key="b", baseline_ref="m", candidate_ref="w",
               tier="hermetic", config={}, status="done", verdict="fail")
    session.add_all([userA, runB]); await session.commit()

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_user_ctx] = lambda: (userA, orgA)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/v1/runs/{runB.id}")
    assert r.status_code == 404
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/server/test_reads.py tests/server/test_isolation.py -v`
Expected: FAIL (routes missing).

- [ ] **Step 3: Write the read routes**

`server/routes/reads.py`:

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server import crypto
from server.db import get_session
from server.deps import get_user_ctx
from server.models import Finding, Org, Project, Run, SlackConfig, User

router = APIRouter()


async def _own_project(session, org: Org, project_id: uuid.UUID) -> Project:
    project = (await session.execute(
        select(Project).where(Project.id == project_id, Project.org_id == org.id)
    )).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("/v1/projects")
async def list_projects(ctx=Depends(get_user_ctx), session: AsyncSession = Depends(get_session)):
    _user, org = ctx
    rows = (await session.execute(select(Project).where(Project.org_id == org.id))).scalars().all()
    return [{"id": str(p.id), "name": p.name} for p in rows]


@router.get("/v1/projects/{project_id}/runs")
async def list_runs(project_id: uuid.UUID, ctx=Depends(get_user_ctx),
                    session: AsyncSession = Depends(get_session)):
    _user, org = ctx
    project = await _own_project(session, org, project_id)
    rows = (await session.execute(select(Run).where(Run.project_id == project.id))).scalars().all()
    return [{"id": str(r.id), "status": r.status, "verdict": r.verdict,
             "baseline_ref": r.baseline_ref, "candidate_ref": r.candidate_ref} for r in rows]


@router.get("/v1/runs/{run_id}")
async def get_run(run_id: uuid.UUID, ctx=Depends(get_user_ctx),
                  session: AsyncSession = Depends(get_session)):
    _user, org = ctx
    run = (await session.execute(
        select(Run).join(Project).where(Run.id == run_id, Project.org_id == org.id)
    )).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    findings = (await session.execute(select(Finding).where(Finding.run_id == run.id))).scalars().all()
    return {
        "id": str(run.id), "status": run.status, "verdict": run.verdict, "error": run.error,
        "findings": [{"test_case_id": f.test_case_id, "title": f.title, "verdict": f.verdict,
                      "metric": f.metric, "impact_summary": f.impact_summary,
                      "cause_path": f.cause_path, "cause_rule": f.cause_rule} for f in findings],
    }


class SlackConfigIn(BaseModel):
    channel_id: str
    bot_token: str


@router.put("/v1/projects/{project_id}/slack")
async def set_slack(project_id: uuid.UUID, body: SlackConfigIn, ctx=Depends(get_user_ctx),
                    session: AsyncSession = Depends(get_session)):
    _user, org = ctx
    project = await _own_project(session, org, project_id)
    cfg = (await session.execute(
        select(SlackConfig).where(SlackConfig.project_id == project.id)
    )).scalar_one_or_none()
    enc = crypto.encrypt(body.bot_token)
    if cfg is None:
        session.add(SlackConfig(project_id=project.id, channel_id=body.channel_id,
                                bot_token_encrypted=enc, enabled=True))
    else:
        cfg.channel_id = body.channel_id; cfg.bot_token_encrypted = enc; cfg.enabled = True
    await session.commit()
    return {"status": "ok"}
```

Add to `server/main.py`: `from server.routes import ingest, reads` and `app.include_router(reads.router)`.

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/server/test_reads.py tests/server/test_isolation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/routes/reads.py server/main.py tests/server/test_reads.py tests/server/test_isolation.py
git commit -m "feat(server): project-scoped read endpoints + slack config, isolation-tested"
```

### Task 3.3: CI collector uploader (capture + attribute + upload)

**Files:**
- Create: `collector/__init__.py`, `collector/uploader.py`
- Test: `tests/collector/__init__.py`, `tests/collector/test_uploader.py`

**Interfaces:**
- Consumes: existing `agentdiff.storage.load_trajectory_set`, `agentdiff.attribution.engine.AttributionResult` (already computed by `ci run`). This task only builds + POSTs the payload; it does not re-run capture.
- Produces: `uploader.build_payload(idempotency_key, baseline_ref, candidate_ref, tier, config, attribution, baseline_trajs, candidate_trajs) -> dict`. `uploader.upload(api_url, api_key, payload, *, post_fn=None) -> dict` POSTing to `{api_url}/v1/runs` with `Authorization: Bearer {api_key}`; `post_fn` injectable for tests.

- [ ] **Step 1: Write the failing test**

`tests/collector/test_uploader.py`:

```python
from collector import uploader


def test_build_payload_shapes_sides():
    baseline = [{"test_case_id": "tc1", "version": "baseline", "events": []}]
    candidate = [{"test_case_id": "tc1", "version": "candidate", "events": []}]
    payload = uploader.build_payload(
        "idem-1", "origin/main", "working", "hermetic", {"agents": []},
        attribution={"attributions": []}, baseline_trajs=baseline, candidate_trajs=candidate,
    )
    sides = {t["side"] for t in payload["trajectories"]}
    assert sides == {"baseline", "candidate"}
    assert payload["idempotency_key"] == "idem-1"
    assert payload["attribution"] == {"attributions": []}


def test_upload_posts_with_bearer():
    calls = []
    def fake_post(url, json, headers):
        calls.append((url, json, headers))
        class R:
            status_code = 202
            def json(self): return {"run_id": "r1", "status": "pending"}
        return R()
    out = uploader.upload("https://api.test", "adk_key", {"trajectories": []}, post_fn=fake_post)
    assert out["run_id"] == "r1"
    assert calls[0][0] == "https://api.test/v1/runs"
    assert calls[0][2]["Authorization"] == "Bearer adk_key"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/collector/test_uploader.py -v`
Expected: FAIL (collector.uploader missing).

- [ ] **Step 3: Implement the uploader**

`collector/uploader.py`:

```python
from typing import Any, Callable


def build_payload(idempotency_key, baseline_ref, candidate_ref, tier, config,
                  attribution, baseline_trajs, candidate_trajs) -> dict[str, Any]:
    trajectories = (
        [{"side": "baseline", "test_case_id": t["test_case_id"], "payload": t} for t in baseline_trajs]
        + [{"side": "candidate", "test_case_id": t["test_case_id"], "payload": t} for t in candidate_trajs]
    )
    return {
        "idempotency_key": idempotency_key, "baseline_ref": baseline_ref,
        "candidate_ref": candidate_ref, "tier": tier, "config": config,
        "attribution": attribution, "trajectories": trajectories,
    }


def upload(api_url: str, api_key: str, payload: dict, *, post_fn: Callable | None = None) -> dict:
    def _default_post(url, json, headers):
        import httpx
        return httpx.post(url, json=json, headers=headers, timeout=30)

    post = post_fn or _default_post
    resp = post(f"{api_url.rstrip('/')}/v1/runs", json=payload,
                headers={"Authorization": f"Bearer {api_key}"})
    if resp.status_code >= 300:
        raise RuntimeError(f"agentdiff upload failed: HTTP {resp.status_code}")
    return resp.json()
```

`collector/__init__.py`: empty.

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/collector/test_uploader.py -v`
Expected: PASS.

- [ ] **Step 5: Wire it into the CI CLI (opt-in upload)**

In `src/agentdiff/cli/ci.py`, after artifacts are written and if `AGENTDIFF_API_URL` + `AGENTDIFF_API_KEY` are set, build the payload from the run's trajectory JSONL + `attribution` and call `uploader.upload`. Show the added block:

```python
import os
from collector import uploader

api_url = os.environ.get("AGENTDIFF_API_URL")
api_key = os.environ.get("AGENTDIFF_API_KEY")
if api_url and api_key:
    payload = uploader.build_payload(
        idempotency_key=os.environ.get("GITHUB_SHA", meta["timestamp"]),
        baseline_ref=baseline_label, candidate_ref=candidate, tier=tier,
        config=structure.model_dump() if hasattr(structure, "model_dump") else {},
        attribution=attribution.model_dump() if attribution is not None else None,
        baseline_trajs=[t.model_dump() for t in baseline_set.trajectories],
        candidate_trajs=[t.model_dump() for t in candidate_set.trajectories],
    )
    try:
        uploader.upload(api_url, api_key, payload)
        console.print("[green]AgentDiff run uploaded to hosted API[/green]")
    except Exception as exc:
        console.print(f"[yellow]Upload failed (local artifacts still written): {exc}[/yellow]")
```

- [ ] **Step 6: Run to verify existing CLI tests still pass**

Run: `pytest tests/collector/ tests/test_ci_cli.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add collector/ tests/collector/ src/agentdiff/cli/ci.py
git commit -m "feat(collector): CI uploader posts trajectories + attribution to hosted API"
```

### Task 3.4: Dashboard wired to the API via Clerk

**Files:**
- Create: `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`
- Modify: `frontend/src/main.tsx` (wrap in `ClerkProvider`), `frontend/package.json` (add `@clerk/clerk-react`, `vitest`)
- Test: `frontend/src/lib/api.test.ts` (vitest)

**Interfaces:**
- Produces: `api.fetchRuns(projectId, getToken) -> Promise<Run[]>` and `api.fetchRun(runId, getToken)` that call the API with `Authorization: Bearer <clerk jwt>` from Clerk's `getToken()`.

- [ ] **Step 1: Add deps + vitest config**

`frontend/package.json`: add `"@clerk/clerk-react": "^5"` to dependencies and `"vitest": "^2"` to devDependencies; add script `"test": "vitest run"`. Run: `npm install`.

- [ ] **Step 2: Write the failing test**

`frontend/src/lib/api.test.ts`:

```ts
import { describe, it, expect, vi } from "vitest";
import { fetchRuns } from "./api";

describe("fetchRuns", () => {
  it("sends the clerk bearer token", async () => {
    const calls: any[] = [];
    vi.stubGlobal("fetch", async (url: string, opts: any) => {
      calls.push({ url, opts });
      return { ok: true, json: async () => [{ id: "r1" }] } as any;
    });
    const getToken = async () => "jwt-abc";
    const runs = await fetchRuns("proj-1", getToken);
    expect(runs).toEqual([{ id: "r1" }]);
    expect(calls[0].url).toContain("/v1/projects/proj-1/runs");
    expect(calls[0].opts.headers.Authorization).toBe("Bearer jwt-abc");
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: FAIL (cannot find ./api).

- [ ] **Step 4: Implement the API client**

`frontend/src/lib/api.ts`:

```ts
const API_URL = import.meta.env.VITE_AGENTDIFF_API_URL ?? "http://localhost:8000";

type GetToken = () => Promise<string | null>;

async function authed(path: string, getToken: GetToken) {
  const token = await getToken();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export function fetchRuns(projectId: string, getToken: GetToken) {
  return authed(`/v1/projects/${projectId}/runs`, getToken);
}

export function fetchRun(runId: string, getToken: GetToken) {
  return authed(`/v1/runs/${runId}`, getToken);
}
```

- [ ] **Step 5: Wrap the app in ClerkProvider**

`frontend/src/main.tsx` — wrap `<App/>`:

```tsx
import { ClerkProvider } from "@clerk/clerk-react";

const KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
// ...existing render, wrapped:
// <ClerkProvider publishableKey={KEY}><App /></ClerkProvider>
```

- [ ] **Step 6: Run to verify it passes + build**

Run: `cd frontend && npx vitest run src/lib/api.test.ts && npm run build`
Expected: test PASS, build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/main.tsx frontend/package.json
git commit -m "feat(dashboard): Clerk-authed API client + provider"
```

### Task 3.5: Full docker-compose (five services) + Dockerfiles + smoke

**Files:**
- Create: `server/Dockerfile`, `frontend/Dockerfile`
- Modify: `docker-compose.yml` (add `api`, `worker`, `dashboard`)
- Test: `tests/server/test_compose_config.py` (validates compose parses + declares five services)

**Interfaces:**
- Produces: `docker compose up` starting `postgres`, `redis`, `api` (uvicorn), `worker` (arq), `dashboard`. `api` runs Alembic migrations on start.

- [ ] **Step 1: Write server Dockerfile**

`server/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY server ./server
COPY collector ./collector
COPY alembic.ini ./
RUN pip install --no-cache-dir -e ".[server]"
CMD ["sh", "-c", "alembic upgrade head && uvicorn server.main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 2: Write frontend Dockerfile**

`frontend/Dockerfile`:

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

- [ ] **Step 3: Extend docker-compose with api/worker/dashboard**

Append to `docker-compose.yml` services:

```yaml
  api:
    build: { context: ., dockerfile: server/Dockerfile }
    environment:
      AGENTDIFF_DATABASE_URL: postgresql+asyncpg://agentdiff:agentdiff@postgres:5432/agentdiff
      AGENTDIFF_REDIS_URL: redis://redis:6379
      AGENTDIFF_SECRET_ENCRYPTION_KEY: ${AGENTDIFF_SECRET_ENCRYPTION_KEY}
      AGENTDIFF_CLERK_JWKS_URL: ${AGENTDIFF_CLERK_JWKS_URL}
      AGENTDIFF_CLERK_ISSUER: ${AGENTDIFF_CLERK_ISSUER}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    ports: ["8000:8000"]
  worker:
    build: { context: ., dockerfile: server/Dockerfile }
    command: arq server.worker.WorkerSettings
    environment:
      AGENTDIFF_DATABASE_URL: postgresql+asyncpg://agentdiff:agentdiff@postgres:5432/agentdiff
      AGENTDIFF_REDIS_URL: redis://redis:6379
      AGENTDIFF_SECRET_ENCRYPTION_KEY: ${AGENTDIFF_SECRET_ENCRYPTION_KEY}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
  dashboard:
    build: { context: ., dockerfile: frontend/Dockerfile }
    ports: ["5173:80"]
    depends_on: [api]
```

- [ ] **Step 4: Write the compose-config test**

`tests/server/test_compose_config.py`:

```python
import subprocess


def test_compose_declares_five_services():
    out = subprocess.run(["docker", "compose", "config", "--services"],
                         capture_output=True, text=True, check=True).stdout
    services = set(out.split())
    assert {"postgres", "redis", "api", "worker", "dashboard"} <= services
```

- [ ] **Step 5: Run the smoke**

Run: `pytest tests/server/test_compose_config.py -v`
Then manual smoke: `AGENTDIFF_SECRET_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())") docker compose up --build -d && sleep 20 && curl -fsS localhost:8000/health`
Expected: `{"status":"ok"}`.

- [ ] **Step 6: Commit**

```bash
git add server/Dockerfile frontend/Dockerfile docker-compose.yml tests/server/test_compose_config.py
git commit -m "feat(deploy): five-service docker-compose + Dockerfiles + smoke"
```

---

## Final verification

- [ ] Run the full server suite: `pytest tests/server tests/collector -v` — all green.
- [ ] Run the existing engine suite: `pytest tests -q` — still 210+ passing, unchanged.
- [ ] `docker compose up --build` — all five services healthy; `curl localhost:8000/health` returns ok.
- [ ] Manual end-to-end: create an org/project/API key row, run the CLI with `AGENTDIFF_API_URL`/`AGENTDIFF_API_KEY` set against a repo with a seeded regression, confirm a run appears `done` with findings via `GET /v1/runs/{id}`.
