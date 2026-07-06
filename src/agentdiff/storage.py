"""Trajectory storage.

The Tracer writes trajectories incrementally (one JSON object per line) via
``Trajectory.model_dump_json()``. JSONL remains the streaming capture format;
SQLite is the structured run artifact written after comparison.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Literal, Protocol

from agentdiff.trajectory import Trajectory, TrajectorySet

#: Schema version written to new/legacy databases by this version of AgentDiff.
#: Bump this when `_init_schema` changes in a way that requires migration.
CURRENT_SCHEMA_VERSION = 1


class StorageVersionError(RuntimeError):
    """Raised when a local SQLite artifact was written by a newer AgentDiff.

    A DB with a schema_version greater than this build understands cannot be
    read safely (older code may not know about newer columns/tables), so we
    refuse to open it rather than risk silently corrupting or misreading it.
    """

    def __init__(self, db_version: int, supported_version: int):
        self.db_version = db_version
        self.supported_version = supported_version
        super().__init__(
            f"This SQLite artifact was written by a newer version of AgentDiff "
            f"(schema version {db_version}), but this install only supports "
            f"schema version {supported_version}. Upgrade AgentDiff to read it."
        )


class TrajectorySink(Protocol):
    """Write and read trajectory sets for one capture environment."""

    def append(self, trajectory: Trajectory) -> None:
        ...

    def load(self, version_tag: Literal["baseline", "candidate"]) -> TrajectorySet:
        ...


class JsonlTrajectorySink:
    """CI-friendly trajectory sink backed by one JSONL file per side."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, version_tag: Literal["baseline", "candidate"]) -> Path:
        return self.root / f"{version_tag}.jsonl"

    def append(self, trajectory: Trajectory) -> None:
        append_trajectory(self.path_for(trajectory.version_tag), trajectory)

    def load(self, version_tag: Literal["baseline", "candidate"]) -> TrajectorySet:
        return load_trajectory_set(self.path_for(version_tag), version_tag)


def load_trajectory_set(
    filepath: Path,
    version_tag: Literal["baseline", "candidate"],
) -> TrajectorySet:
    """Load all trajectories from a JSONL file into a TrajectorySet.

    Skips blank lines and lines that fail to parse (a partially-written final
    line, for instance) rather than aborting the whole load.
    """
    trajectories: list[Trajectory] = []
    path = Path(filepath)
    if not path.exists():
        return TrajectorySet(version_tag=version_tag, trajectories=[])

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                trajectories.append(Trajectory.model_validate(data))
            except (json.JSONDecodeError, ValueError):
                # Tolerate a corrupt/half-written line; keep the rest.
                continue

    return TrajectorySet(version_tag=version_tag, trajectories=trajectories)


def append_trajectory(filepath: Path, traj: Trajectory) -> None:
    """Append a single trajectory as one JSONL line. Used by tests and tools."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(traj.model_dump_json() + "\n")


def write_run_store(
    db_path: Path,
    *,
    metadata: dict[str, Any],
    baseline_set: TrajectorySet,
    candidate_set: TrajectorySet,
    comparison=None,
    output_evals: list[Any] | None = None,
    attribution=None,
) -> Path:
    """Write a queryable SQLite artifact for one AgentDiff compare run."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        run_id = str(metadata.get("run_id") or metadata.get("timestamp") or "latest")
        conn.execute(
            "insert or replace into runs(run_id, metadata_json) values (?, ?)",
            (run_id, json.dumps(metadata, default=str)),
        )
        conn.execute("delete from trajectories where run_id = ?", (run_id,))
        conn.execute("delete from events where run_id = ?", (run_id,))
        conn.execute("delete from artifacts where run_id = ?", (run_id,))

        for side in (baseline_set, candidate_set):
            for traj in side.trajectories:
                conn.execute(
                    """
                    insert into trajectories(
                        run_id, trajectory_id, version_tag, test_case_id, status,
                        final_output, total_tokens, total_latency_ms, trajectory_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        str(traj.run_id),
                        traj.version_tag,
                        traj.test_case_id,
                        traj.status,
                        traj.final_output,
                        traj.total_tokens,
                        traj.total_latency_ms,
                        traj.model_dump_json(),
                    ),
                )
                for event in traj.events:
                    conn.execute(
                        """
                        insert into events(
                            run_id, trajectory_id, version_tag, test_case_id,
                            sequence, event_type, event_json
                        ) values (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            str(traj.run_id),
                            traj.version_tag,
                            traj.test_case_id,
                            getattr(event, "sequence", 0),
                            getattr(event, "event_type", type(event).__name__),
                            event.model_dump_json(),
                        ),
                    )

        _write_artifact(conn, run_id, "comparison", comparison)
        _write_artifact(conn, run_id, "output_evals", output_evals or [])
        _write_artifact(conn, run_id, "attribution", attribution)
        conn.commit()
    return path


def load_trajectory_set_from_sqlite(
    db_path: Path,
    version_tag: Literal["baseline", "candidate"],
    run_id: str | None = None,
) -> TrajectorySet:
    """Load trajectories for one side from a SQLite run artifact."""
    path = Path(db_path)
    if not path.exists():
        return TrajectorySet(version_tag=version_tag, trajectories=[])
    with _connect(path) as conn:
        if run_id is None:
            row = conn.execute(
                "select run_id from runs order by rowid desc limit 1"
            ).fetchone()
            if row is None:
                return TrajectorySet(version_tag=version_tag, trajectories=[])
            run_id = row[0]
        rows = conn.execute(
            """
            select trajectory_json from trajectories
            where run_id = ? and version_tag = ?
            order by rowid
            """,
            (run_id, version_tag),
        ).fetchall()
    return TrajectorySet(
        version_tag=version_tag,
        trajectories=[Trajectory.model_validate_json(row[0]) for row in rows],
    )


def read_artifact(
    db_path: Path,
    name: str,
    run_id: str | None = None,
) -> Any | None:
    """Read a named run artifact (``comparison`` / ``output_evals`` / ``attribution``).

    Returns the JSON-decoded payload, or ``None`` if the database, the run, or the
    named artifact is absent (or was stored as JSON ``null``). ``run_id=None``
    selects the most recently written run.

    The graph layer consumes this rather than re-querying SQLite directly, so
    schema knowledge stays in storage.py (the module that writes the artifacts).
    """
    path = Path(db_path)
    if not path.exists():
        return None
    with _connect(path) as conn:
        if run_id is None:
            row = conn.execute(
                "select run_id from runs order by rowid desc limit 1"
            ).fetchone()
            if row is None:
                return None
            run_id = row[0]
        row = conn.execute(
            "select payload_json from artifacts where run_id = ? and name = ?",
            (run_id, name),
        ).fetchone()
    if row is None or row[0] is None:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None


def _connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and the schema version guard.

    Every connection to a local AgentDiff artifact DB goes through this
    function so that:

    - the journal mode is always WAL (better concurrent read/write behavior
      for a file that may be tailed while a run is still writing), and
    - we refuse to open a DB written by a newer AgentDiff than this install
      understands, rather than risk misreading an unfamiliar schema.

    A pre-existing DB with no ``schema_version`` table (written by an
    AgentDiff version that predates schema versioning) is grandfathered in
    as version 1 rather than treated as an error, so old report directories
    stay readable.
    """
    conn = sqlite3.connect(path)
    conn.execute("pragma journal_mode=WAL")
    _init_schema(conn)
    _check_schema_version(conn)
    conn.commit()
    return conn


def _check_schema_version(conn: sqlite3.Connection) -> None:
    row = conn.execute("select version from schema_version").fetchone()
    if row is None:
        # schema_version table exists (created by _init_schema) but is empty:
        # a legacy DB from before version tracking existed. Grandfather it in.
        conn.execute(
            "insert into schema_version(version) values (?)", (CURRENT_SCHEMA_VERSION,)
        )
        return
    db_version = row[0]
    if db_version > CURRENT_SCHEMA_VERSION:
        raise StorageVersionError(db_version, CURRENT_SCHEMA_VERSION)


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists runs (
            run_id text primary key,
            metadata_json text not null
        );
        create table if not exists trajectories (
            run_id text not null,
            trajectory_id text not null,
            version_tag text not null,
            test_case_id text not null,
            status text not null,
            final_output text,
            total_tokens integer not null,
            total_latency_ms integer not null,
            trajectory_json text not null,
            primary key (run_id, trajectory_id)
        );
        create table if not exists events (
            run_id text not null,
            trajectory_id text not null,
            version_tag text not null,
            test_case_id text not null,
            sequence integer not null,
            event_type text not null,
            event_json text not null
        );
        create index if not exists idx_events_lookup
            on events(run_id, version_tag, test_case_id, event_type);
        create table if not exists artifacts (
            run_id text not null,
            name text not null,
            payload_json text not null,
            primary key (run_id, name)
        );
        create table if not exists schema_version (
            version integer not null
        );
        """
    )


def _write_artifact(conn: sqlite3.Connection, run_id: str, name: str, payload: Any) -> None:
    if payload is None:
        data = "null"
    elif hasattr(payload, "model_dump_json"):
        data = payload.model_dump_json()
    else:
        items = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in payload
        ] if isinstance(payload, list) else payload
        data = json.dumps(items, default=str)
    conn.execute(
        "insert or replace into artifacts(run_id, name, payload_json) values (?, ?, ?)",
        (run_id, name, data),
    )
