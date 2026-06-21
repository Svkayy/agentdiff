"""Trajectory storage.

The Tracer writes trajectories incrementally (one JSON object per line) via
``Trajectory.model_dump_json()``. JSONL remains the streaming capture format;
SQLite is the structured run artifact written after comparison.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from agentdiff.trajectory import Trajectory, TrajectorySet


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
    with sqlite3.connect(path) as conn:
        _init_schema(conn)
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
    with sqlite3.connect(path) as conn:
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
