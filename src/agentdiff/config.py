"""Project configuration loading and defaults.

This module is intentionally small and typed: the CLI can evolve without each
command hand-parsing YAML into slightly different shapes.
"""
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class RunnerConfig(BaseModel):
    module: str | None = None
    callable: str = "run"


class SamplingConfig(BaseModel):
    install_deps: bool = True
    max_failure_rate: float = 0.0
    workers: int = 1

    @field_validator("max_failure_rate")
    @classmethod
    def _validate_rate(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("max_failure_rate must be between 0 and 1")
        return value

    @field_validator("workers")
    @classmethod
    def _validate_workers(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("workers must be positive")
        return value


class MetricThreshold(BaseModel):
    warn: float
    fail: float

    @field_validator("warn", "fail")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("thresholds must be non-negative")
        return value

    @model_validator(mode="after")
    def _warn_not_above_fail(self) -> "MetricThreshold":
        if self.warn > self.fail:
            raise ValueError("warn threshold must be less than or equal to fail")
        return self


class ThresholdConfig(BaseModel):
    agent_invocation_rate: MetricThreshold = Field(
        default_factory=lambda: MetricThreshold(warn=0.2, fail=0.5)
    )
    tool_usage_avg: MetricThreshold = Field(
        default_factory=lambda: MetricThreshold(warn=0.5, fail=1.0)
    )


class CaptureConfig(BaseModel):
    httpx: bool = True
    requests: bool = True
    aiohttp: bool = True
    grpc: bool = True
    openai_sdk: bool = True
    anthropic_sdk: bool = True
    mcp: bool = True
    langgraph: bool = True
    crewai: bool = True
    autogen: bool = True
    llamaindex: bool = True


class AgentDiffConfig(BaseModel):
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    samples_per_case: int = 20
    llm_provider: str = "anthropic"
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)

    @field_validator("samples_per_case")
    @classmethod
    def _positive_samples(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("samples_per_case must be positive")
        return value


def config_path(root: Path) -> Path:
    return Path(root) / ".agentdiff" / "config.yaml"


def load_raw_config(root: Path) -> dict[str, Any]:
    path = config_path(root)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(root: Path) -> AgentDiffConfig:
    return AgentDiffConfig.model_validate(load_raw_config(root))


def thresholds_for_compare(config: AgentDiffConfig) -> dict[str, float]:
    return {
        "agent_invocation_rate_warn": config.thresholds.agent_invocation_rate.warn,
        "agent_invocation_rate_fail": config.thresholds.agent_invocation_rate.fail,
        "tool_usage_avg_warn": config.thresholds.tool_usage_avg.warn,
        "tool_usage_avg_fail": config.thresholds.tool_usage_avg.fail,
    }
