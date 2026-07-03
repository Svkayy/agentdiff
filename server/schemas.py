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
    trajectories: list[TrajectoryIn] = Field(max_length=5000)


class RunAccepted(BaseModel):
    run_id: str
    status: str
