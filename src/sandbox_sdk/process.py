"""AnyIO-style process handles with reconnecting remote operations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from types import TracebackType
from typing import Literal, TypeVar

import anyio
from anyio import ClosedResourceError, EndOfStream
from anyio.abc import ByteReceiveStream

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.errors import SandboxConnectionError, SandboxTimeoutError
from sandbox_sdk.models import ProcessOptions

T = TypeVar("T")


async def _with_reconnect(
    operation: Callable[[], Awaitable[T]],
    *,
    deadline: float,
    retry_interval: float,
) -> T:
    """Retry transient provider connection failures until a shared deadline."""
    while True:
        remaining = deadline - anyio.current_time()
        if remaining <= 0:
            raise SandboxTimeoutError("Timed out reconnecting to sandbox process")
        try:
            with anyio.fail_after(remaining):
                return await operation()
        except TimeoutError as err:
            raise SandboxTimeoutError("Timed out waiting for sandbox process") from err
        except SandboxConnectionError:
            await anyio.sleep(min(retry_interval, remaining))


class SandboxProcessOutputStream(ByteReceiveStream):
    """Reconnectable incremental byte stream for process stdout or stderr."""

    def __init__(
        self,
        backend: SandboxBackend,
        sandbox_id: str,
        process_id: str,
        stream: Literal["stdout", "stderr"],
        *,
        timeout: float,
        retry_interval: float,
    ) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id
        self._process_id = process_id
        self._stream = stream
        self._timeout = timeout
        self._retry_interval = retry_interval
        self._offset = 0
        self._closed = False

    async def receive(self, max_bytes: int = 65536) -> bytes:
        """Receive bytes, reconnecting after transient provider connection failures."""
        if self._closed:
            raise ClosedResourceError
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        deadline = anyio.current_time() + self._timeout

        async def _receive():
            return await self._backend.read_process_output(
                self._sandbox_id,
                self._process_id,
                self._stream,
                self._offset,
                max_bytes,
            )

        chunk = await _with_reconnect(
            _receive, deadline=deadline, retry_interval=self._retry_interval
        )
        self._offset += len(chunk.data)
        if not chunk.data and chunk.eof:
            raise EndOfStream
        return chunk.data

    async def aclose(self) -> None:
        """Close this local stream view without affecting the remote process."""
        self._closed = True


class AsyncSandboxProcess:
    """A reconnectable AnyIO-style handle to a long-running sandbox process."""

    def __init__(
        self,
        backend: SandboxBackend,
        sandbox_id: str,
        process_id: str,
        options: ProcessOptions,
        *,
        timeout: float,
        retry_interval: float,
    ) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id
        self._id = process_id
        self._options = options
        self._timeout = timeout
        self._retry_interval = retry_interval
        self._returncode: int | None = None
        self._closed = False
        stream_options = {"timeout": timeout, "retry_interval": retry_interval}
        self._stdout = SandboxProcessOutputStream(
            backend, sandbox_id, process_id, "stdout", **stream_options
        )
        self._stderr = SandboxProcessOutputStream(
            backend, sandbox_id, process_id, "stderr", **stream_options
        )

    @property
    def id(self) -> str:
        """The provider's opaque, reconnectable process identifier."""
        return self._id

    @property
    def args(self) -> tuple[str, ...]:
        return self._options.args

    @property
    def returncode(self) -> int | None:
        return self._returncode

    @property
    def stdout(self) -> ByteReceiveStream:
        return self._stdout

    @property
    def stderr(self) -> ByteReceiveStream:
        return self._stderr

    async def wait(self, timeout: float | None = None) -> int:
        """Wait for an exit code, reconnecting until the timeout expires."""
        if self._returncode is not None:
            return self._returncode
        deadline = anyio.current_time() + (self._timeout if timeout is None else timeout)
        while self._returncode is None:
            self._returncode = await _with_reconnect(
                lambda: self._backend.poll_process(self._sandbox_id, self._id),
                deadline=deadline,
                retry_interval=self._retry_interval,
            )
            if self._returncode is None:
                remaining = deadline - anyio.current_time()
                if remaining <= 0:
                    raise SandboxTimeoutError("Timed out waiting for sandbox process")
                await anyio.sleep(min(self._retry_interval, remaining))
        return self._returncode

    async def terminate(self) -> None:
        """Request graceful termination, reconnecting if necessary."""
        if self._returncode is not None:
            return
        deadline = anyio.current_time() + self._timeout
        await _with_reconnect(
            lambda: self._backend.terminate_process(self._sandbox_id, self._id),
            deadline=deadline,
            retry_interval=self._retry_interval,
        )

    async def aclose(self) -> None:
        """Wait for completion; on cancellation, terminate and reap the process."""
        if self._closed:
            return
        try:
            await self.wait()
        except BaseException:
            with anyio.CancelScope(shield=True):
                await self.terminate()
                await self.wait()
            raise
        finally:
            await self._stdout.aclose()
            await self._stderr.aclose()
            self._closed = True

    async def __aenter__(self) -> AsyncSandboxProcess:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            with anyio.CancelScope(shield=True):
                await self.terminate()
                await self.aclose()
        else:
            await self.aclose()


async def collect_stream(stream: ByteReceiveStream) -> bytes:
    """Collect a receive stream without assuming provider chunk boundaries."""
    chunks = bytearray()
    async for chunk in stream:
        chunks.extend(chunk)
    return bytes(chunks)


async def iter_stream(stream: ByteReceiveStream) -> AsyncIterator[bytes]:
    """Yield chunks from an AnyIO byte stream (primarily useful to sync bridges)."""
    async for chunk in stream:
        yield chunk
