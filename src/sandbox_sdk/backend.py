"""Backend protocols defining capabilities of sandbox adapters."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from sandbox_sdk.models import ProcessOptions, ProcessOutputChunk, SandboxConfig


@runtime_checkable
class SandboxBackend(Protocol):
    """Low-level adapter protocol for sandbox environments.

    Implementations handle starting/connecting to environments (Docker, Vercel Sandbox, Modal, etc.)
    and performing low-level I/O operations asynchronously using AnyIO concurrency primitives.
    """

    async def start(self, config: SandboxConfig) -> str:
        """Start or connect to a sandbox instance.

        Returns:
            The unique identifier of the running sandbox.
        """
        ...

    async def stop(self, sandbox_id: str) -> None:
        """Stop and clean up the sandbox instance."""
        ...

    async def write_bytes(self, sandbox_id: str, path: str, data: bytes) -> None:
        """Write raw bytes to a file path in the sandbox."""
        ...

    async def read_bytes(self, sandbox_id: str, path: str) -> bytes:
        """Read raw bytes from a file path in the sandbox."""
        ...

    async def start_process(self, sandbox_id: str, options: ProcessOptions) -> str:
        """Start a process and return a provider-specific opaque identifier."""
        ...

    async def poll_process(self, sandbox_id: str, process_id: str) -> int | None:
        """Return the exit code, or ``None`` while the process is running."""
        ...

    async def read_process_output(
        self,
        sandbox_id: str,
        process_id: str,
        stream: Literal["stdout", "stderr"],
        offset: int,
        max_bytes: int,
    ) -> ProcessOutputChunk:
        """Read the next available chunk from a process output stream."""
        ...

    async def terminate_process(self, sandbox_id: str, process_id: str) -> None:
        """Request termination of a started process."""
        ...
