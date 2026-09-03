"""Models and value types for Sandbox SDK."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxConfig:
    """Generic configuration for creating or connecting to a sandbox."""

    image: str = "alpine:latest"
    name: str | None = None
    env: Mapping[str, str] | None = None
    timeout: float = 30.0
