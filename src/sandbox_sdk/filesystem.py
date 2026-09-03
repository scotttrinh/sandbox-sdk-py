"""Filesystem handle implementation for sandboxes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox_sdk.backend import SandboxBackend


class AsyncSandboxFilesystem:
    """Async filesystem facade for a sandbox."""

    def __init__(self, backend: SandboxBackend, sandbox_id: str) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id

    async def write_bytes(self, path: str, data: bytes) -> None:
        """Write raw bytes to a file in the sandbox."""
        await self._backend.write_bytes(self._sandbox_id, path, data)

    async def write_text(self, path: str, text: str, encoding: str = "utf-8") -> None:
        """Write text to a file in the sandbox."""
        await self._backend.write_bytes(self._sandbox_id, path, text.encode(encoding))

    async def read_bytes(self, path: str) -> bytes:
        """Read raw bytes from a file in the sandbox."""
        return await self._backend.read_bytes(self._sandbox_id, path)

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read text from a file in the sandbox."""
        data = await self._backend.read_bytes(self._sandbox_id, path)
        return data.decode(encoding)
