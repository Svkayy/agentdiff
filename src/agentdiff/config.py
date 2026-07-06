"""Project configuration loading and defaults.

This module is intentionally small and typed: the CLI can evolve without each
command hand-parsing YAML into slightly different shapes.
"""
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class RunnerConfig(BaseModel):
    module: str | None = None
    callable: str = "run"


class SamplingConfig(BaseModel):
    install_deps: bool = True
    max_failure_rate: float = 0.0
    workers: int = 1
    timeout_seconds: float = 300.0
    retries: int = 1
    retry_backoff_seconds: float = 2.0

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

    @field_validator("timeout_seconds")
    @classmethod
    def _non_negative_timeout(cls, value: float) -> float:
        if value < 0:
            raise ValueError("timeout_seconds must be non-negative")
        return value

    @field_validator("retries")
    @classmethod
    def _non_negative_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retries must be non-negative")
        return value

    @field_validator("retry_backoff_seconds")
    @classmethod
    def _non_negative_retry_backoff(cls, value: float) -> float:
        if value < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
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
    latency_ms: MetricThreshold = Field(
        default_factory=lambda: MetricThreshold(warn=1000, fail=5000)
    )
    tokens: MetricThreshold = Field(
        default_factory=lambda: MetricThreshold(warn=200, fail=1000)
    )
    error_rate: MetricThreshold = Field(
        default_factory=lambda: MetricThreshold(warn=0.1, fail=0.25)
    )


class RedactionConfig(BaseModel):
    mode: Literal["standard", "strict", "off"] = "standard"
    patterns: list[str] = Field(default_factory=list)
    redact_fields: list[str] = Field(default_factory=list)
    capture_raw_bodies: bool = False


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
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)


class StatsConfig(BaseModel):
    correction: Literal["benjamini_hochberg", "none"] = "benjamini_hochberg"
    alpha: float = 0.05
    min_samples_warn: int = 5

    @field_validator("alpha")
    @classmethod
    def _alpha_in_range(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("alpha must be greater than 0 and less than or equal to 1")
        return value


class OutputEvalThresholds(BaseModel):
    semantic_fail: float = 0.70
    semantic_warn: float = 0.85
    length_fail: float = 0.50
    length_warn: float = 0.80
    structural_fail: float = 0.70
    structural_warn: float = 0.90
    judge_fail: float = 2.0
    judge_warn: float = 3.5


class AgentDiffConfig(BaseModel):
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    samples_per_case: int = 20
    llm_provider: str = "anthropic"
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    stats: StatsConfig = Field(default_factory=StatsConfig)
    output_eval: OutputEvalThresholds = Field(default_factory=OutputEvalThresholds)

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
        "latency_ms_warn": config.thresholds.latency_ms.warn,
        "latency_ms_fail": config.thresholds.latency_ms.fail,
        "tokens_warn": config.thresholds.tokens.warn,
        "tokens_fail": config.thresholds.tokens.fail,
        "error_rate_warn": config.thresholds.error_rate.warn,
        "error_rate_fail": config.thresholds.error_rate.fail,
    }
