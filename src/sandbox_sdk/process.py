"""Popen-like asynchronous process handles."""

from __future__ import annotations

from types import TracebackType

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.models import ProcessOptions, ProcessResult


class AsyncSandboxProcess:
    """A handle to a process running inside a sandbox."""

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

    async def poll(self) -> int | None:
        """Check whether the process has exited without waiting."""
        self._returncode = await self._backend.poll_process(self._sandbox_id, self._id)
        return self._returncode

    async def wait(self, timeout: float | None = None, *, check: bool = False) -> ProcessResult:
        """Wait for completion and return captured stdout and stderr."""
        result = await self._backend.wait_process(self._sandbox_id, self._id, timeout)
        result = ProcessResult(self._options.args, result.returncode, result.stdout, result.stderr)
        self._returncode = result.returncode
        if check:
            result.check_returncode()
        return result

    async def terminate(self) -> None:
        """Request process termination."""
        await self._backend.terminate_process(self._sandbox_id, self._id)

    async def __aenter__(self) -> AsyncSandboxProcess:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if not self._detached and await self.poll() is None:
            await self.terminate()
            await self.wait()
