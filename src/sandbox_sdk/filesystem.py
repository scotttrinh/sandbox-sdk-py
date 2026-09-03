"""Filesystem handle implementation and open() context managers for sandboxes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sandbox_sdk.file import AsyncSandboxFile

if TYPE_CHECKING:
    from sandbox_sdk.backend import SandboxBackend


class AsyncSandboxFilesystem:
    """Async filesystem facade modeled after Python stdlib file and path operations."""

    def __init__(self, backend: SandboxBackend, sandbox_id: str) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id

    def open(
        self,
        path: str,
        mode: str = "r",
        encoding: str = "utf-8",
    ) -> AsyncSandboxFile:
        """Open a file inside the sandbox.

        Returns an async context manager and file object supporting read/write/iteration:
        ```python
        async with sbx.fs.open("/workspace/data.txt", "w") as f:
            await f.write("hello")
        ```
        """
        return AsyncSandboxFile(
            backend=self._backend,
            sandbox_id=self._sandbox_id,
            path=path,
            mode=mode,
            encoding=encoding,
        )

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
