"""File handle implementations modeled after Python stdlib file objects."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator, Iterator
from types import TracebackType
from typing import TYPE_CHECKING, Any

from sandbox_sdk.errors import SandboxClosedError, SandboxFilesystemError

if TYPE_CHECKING:
    from sandbox_sdk.backend import SandboxBackend


class AsyncSandboxFile(AsyncIterator[Any]):
    """Async file-like object supporting read/write operations and async context management."""

    def __init__(
        self,
        backend: SandboxBackend,
        sandbox_id: str,
        path: str,
        mode: str = "r",
        encoding: str = "utf-8",
    ) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id
        self._path = path
        self._mode = mode
        self._encoding = encoding
        self._closed = False
        self._buffer = io.BytesIO()

        # Parse mode
        self._is_binary = "b" in mode
        self._is_write = "w" in mode or "a" in mode or "+" in mode
        self._is_read = "r" in mode or "+" in mode

    @property
    def name(self) -> str:
        return self._path

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def closed(self) -> bool:
        return self._closed

    def readable(self) -> bool:
        return self._is_read and not self._closed

    def writable(self) -> bool:
        return self._is_write and not self._closed

    def seekable(self) -> bool:
        return not self._closed

    async def _ensure_loaded(self) -> None:
        """If reading or appending, load existing contents if needed."""
        if self._is_read or "a" in self._mode:
            if self._buffer.tell() == 0 and len(self._buffer.getvalue()) == 0:
                try:
                    data = await self._backend.read_bytes(self._sandbox_id, self._path)
                    self._buffer = io.BytesIO(data)
                    if "a" in self._mode:
                        self._buffer.seek(0, io.SEEK_END)
                    else:
                        self._buffer.seek(0)
                except Exception:
                    if "r" in self._mode and "+" not in self._mode:
                        raise

    async def read(self, size: int = -1) -> str | bytes:
        if self._closed:
            raise SandboxClosedError("I/O operation on closed file.")
        await self._ensure_loaded()
        data = self._buffer.read() if size < 0 else self._buffer.read(size)
        if self._is_binary:
            return data
        return data.decode(self._encoding)

    async def readline(self, size: int = -1) -> str | bytes:
        if self._closed:
            raise SandboxClosedError("I/O operation on closed file.")
        await self._ensure_loaded()
        line = self._buffer.readline() if size < 0 else self._buffer.readline(size)
        if self._is_binary:
            return line
        return line.decode(self._encoding)

    async def write(self, b: str | bytes) -> int:
        if self._closed:
            raise SandboxClosedError("I/O operation on closed file.")
        if not self._is_write:
            raise SandboxFilesystemError(f"File not open for writing (mode={self._mode})")

        if isinstance(b, str):
            if self._is_binary:
                raise TypeError("a bytes-like object is required, not 'str'")
            raw = b.encode(self._encoding)
        else:
            if not self._is_binary:
                raise TypeError("write() argument must be str, not bytes")
            raw = b

        return self._buffer.write(raw)

    async def flush(self) -> None:
        """Flush internal buffer to the remote sandbox."""
        if self._closed:
            raise SandboxClosedError("I/O operation on closed file.")
        if self._is_write:
            data = self._buffer.getvalue()
            await self._backend.write_bytes(self._sandbox_id, self._path, data)

    async def close(self) -> None:
        if not self._closed:
            try:
                if self._is_write:
                    await self.flush()
            finally:
                self._closed = True
                self._buffer.close()

    async def __aenter__(self) -> AsyncSandboxFile:
        await self._ensure_loaded()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __aiter__(self) -> AsyncSandboxFile:
        return self

    async def __anext__(self) -> str | bytes:
        line = await self.readline()
        if not line:
            raise StopAsyncIteration
        return line


class SyncSandboxFile(Iterator[Any]):
    """Synchronous file-like object supporting read/write operations and context management."""

    def __init__(
        self,
        async_file: AsyncSandboxFile,
    ) -> None:
        self._async_file = async_file

    @property
    def name(self) -> str:
        return self._async_file.name

    @property
    def mode(self) -> str:
        return self._async_file.mode

    @property
    def closed(self) -> bool:
        return self._async_file.closed

    def readable(self) -> bool:
        return self._async_file.readable()

    def writable(self) -> bool:
        return self._async_file.writable()

    def seekable(self) -> bool:
        return self._async_file.seekable()

    def read(self, size: int = -1) -> str | bytes:
        import anyio

        return anyio.run(self._async_file.read, size)

    def readline(self, size: int = -1) -> str | bytes:
        import anyio

        return anyio.run(self._async_file.readline, size)

    def write(self, b: str | bytes) -> int:
        import anyio

        return anyio.run(self._async_file.write, b)

    def flush(self) -> None:
        import anyio

        anyio.run(self._async_file.flush)

    def close(self) -> None:
        import anyio

        anyio.run(self._async_file.close)

    def __enter__(self) -> SyncSandboxFile:
        import anyio

        anyio.run(self._async_file.__aenter__)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        import anyio

        anyio.run(self._async_file.__aexit__, exc_type, exc_val, exc_tb)

    def __iter__(self) -> SyncSandboxFile:
        return self

    def __next__(self) -> str | bytes:
        line = self.readline()
        if not line:
            raise StopIteration
        return line
