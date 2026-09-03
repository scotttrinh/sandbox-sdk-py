"""AnyIO-style asynchronous process handles and output streams."""

from __future__ import annotations

from types import TracebackType
from typing import Literal

from anyio import CancelScope, ClosedResourceError, EndOfStream
from anyio.abc import ByteReceiveStream

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.models import ProcessOptions, ProcessResult


class SandboxProcessOutputStream(ByteReceiveStream):
    """Incremental byte stream for process stdout or stderr."""

    def __init__(
        self,
        backend: SandboxBackend,
        sandbox_id: str,
        process_id: str,
        stream: Literal["stdout", "stderr"],
    ) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id
        self._process_id = process_id
        self._stream = stream
        self._offset = 0
        self._closed = False

    async def receive(self, max_bytes: int = 65536) -> bytes:
        """Receive available bytes, waiting until data or end-of-stream."""
        if self._closed:
            raise ClosedResourceError
        if max_bytes < 1:
            raise ValueError("max_bytes must be at least 1")
        chunk = await self._backend.read_process_output(
            self._sandbox_id,
            self._process_id,
            self._stream,
            self._offset,
            max_bytes,
        )
        self._offset += len(chunk.data)
        if not chunk.data and chunk.eof:
            raise EndOfStream
        return chunk.data

    async def aclose(self) -> None:
        """Close this local stream view without affecting the process."""
        self._closed = True


class AsyncSandboxProcess:
    """An AnyIO-style handle to a process running inside a sandbox."""

    def __init__(
        self,
        backend: SandboxBackend,
        sandbox_id: str,
        process_id: str,
        options: ProcessOptions,
        *,
        detached: bool,
    ) -> None:
        self._backend = backend
        self._sandbox_id = sandbox_id
        self._id = process_id
        self._options = options
        self._detached = detached
        self._returncode: int | None = None
        self._result: ProcessResult | None = None
        self._closed = False
        self._stdout = SandboxProcessOutputStream(backend, sandbox_id, process_id, "stdout")
        self._stderr = SandboxProcessOutputStream(backend, sandbox_id, process_id, "stderr")

    @property
    def id(self) -> str:
        """The backend's opaque process identifier."""
        return self._id

    @property
    def args(self) -> tuple[str, ...]:
        return self._options.args

    @property
    def detached(self) -> bool:
        return self._detached

    @property
    def returncode(self) -> int | None:
        return self._returncode

    @property
    def stdout(self) -> ByteReceiveStream:
        """The process standard-output byte stream."""
        return self._stdout

    @property
    def stderr(self) -> ByteReceiveStream:
        """The process standard-error byte stream."""
        return self._stderr

    async def poll(self) -> int | None:
        """Check whether the process has exited without waiting."""
        self._returncode = await self._backend.poll_process(self._sandbox_id, self._id)
        return self._returncode

    async def wait(self, timeout: float | None = None, *, check: bool = False) -> ProcessResult:
        """Wait for completion and return the complete captured output."""
        if self._result is None:
            result = await self._backend.wait_process(self._sandbox_id, self._id, timeout)
            self._result = ProcessResult(
                self._options.args, result.returncode, result.stdout, result.stderr
            )
            self._returncode = result.returncode
        if check:
            self._result.check_returncode()
        return self._result

    async def terminate(self) -> None:
        """Request graceful process termination."""
        if await self.poll() is None:
            await self._backend.terminate_process(self._sandbox_id, self._id)

    async def aclose(self) -> None:
        """Wait for the process and close its local output streams."""
        if self._closed:
            return
        try:
            await self.wait()
        except BaseException:
            with CancelScope(shield=True):
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
        if self._detached:
            return
        if exc_type is not None:
            with CancelScope(shield=True):
                await self.terminate()
                await self.aclose()
        else:
            await self.aclose()
