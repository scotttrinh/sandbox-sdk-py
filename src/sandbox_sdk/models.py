"""Models and value types for Sandbox SDK."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxConfig:
    """Generic configuration for creating or connecting to a sandbox."""

    image: str = "alpine:latest"
    name: str | None = None
    env: Mapping[str, str] | None = None
    timeout: float = 30.0


@dataclass(frozen=True)
class ProcessOptions:
    """Provider-neutral description of a process to execute."""

    args: tuple[str, ...]
    cwd: str | None = None
    env: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ProcessResult:
    """The captured result of a process, analogous to ``subprocess.CompletedProcess``."""

    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes

    def check_returncode(self) -> None:
        """Raise ``CalledProcessError`` when the process was unsuccessful."""
        if self.returncode:
            raise subprocess.CalledProcessError(
                self.returncode,
                self.args,
                output=self.stdout,
                stderr=self.stderr,
            )
