import contextvars
import itertools
import threading
from pathlib import Path

_active_tracer: contextvars.ContextVar["Tracer | None"] = contextvars.ContextVar(
    "agentdiff_active_tracer", default=None
)
_sdk_shim_marker: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "agentdiff_inside_sdk_shim", default=False
)
_flush_lock = threading.Lock()


def get_active_tracer() -> "Tracer | None":
    return _active_tracer.get()


def get_sdk_shim_marker() -> bool:
    return _sdk_shim_marker.get()


def set_sdk_shim_marker(value: bool) -> contextvars.Token:
    return _sdk_shim_marker.set(value)


def reset_sdk_shim_marker(token: contextvars.Token) -> None:
    _sdk_shim_marker.reset(token)


class Tracer:
    def __init__(
        self,
        test_case_id: str,
        version_tag: str,
        input_data: dict,
        output_path: Path,
        structure_root: Path | None = None,
    ):
        self.test_case_id = test_case_id
        self.version_tag = version_tag
        self.input_data = input_data
        self.output_path = Path(output_path)
        self._events: list = []
        self._sequence_counter = itertools.count()
        self._lock = threading.Lock()
        self._token: contextvars.Token | None = None
        self._final_output: str | None = None
        self._error: str | None = None
        self._status: str = "success"

        # Load structure.yaml so we can annotate LLM events with inferred_agent.
        try:
            from agentdiff.structure.structure_yaml import load_nearest
            doc = load_nearest(structure_root)
            self._agent_map: dict[str, str] = doc.agent_names_for_functions() if doc else {}
        except Exception:
            self._agent_map = {}

    def __enter__(self) -> "Tracer":
        self._token = _active_tracer.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self._status = "failed"
            self._error = f"{type(exc).__name__}: {exc}"
        if self._token is not None:
            _active_tracer.reset(self._token)
        try:
            self._flush()
        except Exception as flush_exc:  # noqa: BLE001
            # A flush failure (disk full, serialization edge case) must never
            # mask the runner's own exception or crash the sampling loop.
            print(f"[agentdiff] failed to write trajectory: {flush_exc}")

    def record(self, event) -> None:
        with self._lock:
            event.sequence = next(self._sequence_counter)
            # Tag http_shim events captured while an SDK shim is the outer wrapper.
            if getattr(event, "captured_by", None) == "http_shim":
                if _sdk_shim_marker.get():
                    object.__setattr__(event, "_superseded_by_sdk_shim", True)
            # Resolve inferred_agent to the structure.yaml *display name* by
            # walking the call stack for the first user-code frame that maps to a
            # known agent. This OVERRIDES the raw function name the shims pre-fill
            # via classify_call_stack — the display name is authoritative, and
            # compare/manifest both key on it. If no frame maps to a known agent
            # (or there is no structure.yaml), the shim's raw fallback is kept.
            if (
                self._agent_map
                and hasattr(event, "inferred_agent")
                and hasattr(event, "call_stack")
            ):
                for frame in event.call_stack:
                    if frame.is_user_code:
                        name = self._agent_map.get(frame.function)
                        if name:
                            event.inferred_agent = name
                            break
            self._events.append(event)

    def set_final_output(self, output: str | None) -> None:
        self._final_output = output

    def set_failed(self, error: str) -> None:
        """Mark this trajectory as failed with the exact ``error`` message.

        Unlike raising inside the ``with`` block (which ``__exit__`` formats
        as ``f"{type(exc).__name__}: {exc}"``), this sets the persisted error
        to exactly ``error`` -- for synthetic failures (e.g. a sample-level
        timeout/retry-budget message) that are not themselves an exception
        caught by ``__exit__``.
        """
        self._status = "failed"
        self._error = error

    def _flush(self) -> None:
        from agentdiff.trajectory import Trajectory

        dedup_events = [
            e for e in self._events
            if not getattr(e, "_superseded_by_sdk_shim", False)
        ]

        total_tokens = sum(
            e.canonical.usage.get("total_tokens", 0)
            for e in dedup_events
            if hasattr(e, "canonical") and e.canonical is not None
        )
        total_latency_ms = sum(
            e.latency_ms
            for e in dedup_events
            if hasattr(e, "latency_ms")
        )

        traj = Trajectory(
            test_case_id=self.test_case_id,
            version_tag=self.version_tag,  # type: ignore[arg-type]
            input=self.input_data,
            final_output=self._final_output,
            events=dedup_events,
            status=self._status,  # type: ignore[arg-type]
            error=self._error,
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
        )

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with _flush_lock:
            with open(self.output_path, "a") as f:
                f.write(traj.model_dump_json() + "\n")
