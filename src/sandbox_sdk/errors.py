"""Exceptions for Sandbox SDK."""

from __future__ import annotations


class SandboxError(Exception):
    """Base exception for all Sandbox SDK errors."""


class SandboxConnectionError(SandboxError):
    """Raised when connecting to a sandbox fails."""


class SandboxTimeoutError(SandboxError):
    """Raised when a sandbox operation times out."""


class SandboxPathNotFoundError(SandboxError):
    """Raised when a specified path does not exist in the sandbox."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Path not found in sandbox: {path}")


class SandboxFilesystemError(SandboxError):
    """Raised when a filesystem operation fails."""


class SandboxClosedError(SandboxError):
    """Raised when attempting an operation on a closed sandbox."""


class SandboxProcessError(SandboxError):
    """Raised when a sandbox process cannot be started or inspected."""
