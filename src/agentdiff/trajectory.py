from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from agentdiff.capture.events import (
    Event,
    FrameworkEvent,
    LLMRequestEvent,
    MCPToolInvokedEvent,
    LocalToolInvokedEvent,
    StreamChunkEvent,
)


class Trajectory(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    test_case_id: str
    version_tag: Literal["baseline", "candidate"]

    input: dict[str, Any]
    final_output: str | None = None

    events: list[Event] = Field(default_factory=list)

    status: Literal["success", "failed", "incomplete"] = "success"
    error: str | None = None

    total_tokens: int = 0
    total_latency_ms: int = 0

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def agents_invoked(self) -> list[str]:
        names = {
            e.inferred_agent
            for e in self.events
            if hasattr(e, "inferred_agent") and e.inferred_agent
        }
        return sorted(names)

    def llm_calls(self, by_agent: str | None = None) -> list[LLMRequestEvent]:
        out = [e for e in self.events if isinstance(e, LLMRequestEvent)]
        if by_agent:
            out = [e for e in out if e.inferred_agent == by_agent]
        return out

    def tool_calls(self, by_agent: str | None = None) -> list[Event]:
        out = [
            e for e in self.events
            if isinstance(e, (MCPToolInvokedEvent, LocalToolInvokedEvent))
        ]
        if by_agent:
            out = [e for e in out if e.inferred_agent == by_agent]
        return out

    def framework_events(self, by_framework: str | None = None) -> list[FrameworkEvent]:
        out = [e for e in self.events if isinstance(e, FrameworkEvent)]
        if by_framework:
            out = [e for e in out if e.framework == by_framework]
        return out

    def stream_chunks(self, call_id: UUID | None = None) -> list[StreamChunkEvent]:
        out = [e for e in self.events if isinstance(e, StreamChunkEvent)]
        if call_id:
            out = [e for e in out if e.call_id == call_id]
        return out


class TrajectorySet(BaseModel):
    version_tag: Literal["baseline", "candidate"]
    trajectories: list[Trajectory]

    def for_test_case(self, test_case_id: str) -> list[Trajectory]:
        return [t for t in self.trajectories if t.test_case_id == test_case_id]
