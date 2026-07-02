"""Common delivery result models for incident integrations."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeliveryResult:
    ok: bool
    integration: str
    error: str | None = None
    url: str | None = None
