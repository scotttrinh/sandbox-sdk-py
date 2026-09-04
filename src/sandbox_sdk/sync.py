"""Synchronous Sandbox interface and context managers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import TracebackType

import anyio
from anyio.abc import ByteReceiveStream

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.client import AsyncSandbox
from sandbox_sdk.client import connect as async_connect
from sandbox_sdk.errors import SandboxClosedError
from sandbox_sdk.file import SyncSandboxFile
from sandbox_sdk.models import ProcessResult
from sandbox_sdk.process import AsyncSandboxProcess


class SyncSandboxProcessOutputStream:
    """Synchronous view of an AnyIO-style process output stream."""

    def __init__(self, async_stream: ByteReceiveStream) -> None:
        self._async_stream = async_stream

    def receive(self, max_bytes: int = 65536) -> bytes:
        """Receive available bytes, raising ``anyio.EndOfStream`` at EOF."""
        return anyio.run(self._async_stream.receive, max_bytes)

    def close(self) -> None:
        anyio.run(self._async_stream.aclose)

    def __iter__(self) -> Iterator[bytes]:
        while True:
            try:
                yield self.receive()
            except anyio.EndOfStream:
                return

    def __enter__(self) -> SyncSandboxProcessOutputStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


class SyncSandboxProcess:
    """Synchronous Popen-like handle for a sandbox process."""

    def __init__(self, async_process: AsyncSandboxProcess) -> None:
        self._async_process = async_process
        self._stdout = SyncSandboxProcessOutputStream(async_process.stdout)
        self._stderr = SyncSandboxProcessOutputStream(async_process.stderr)

    @property
    def id(self) -> str:
        return self._async_process.id

    @property
    def args(self) -> tuple[str, ...]:
        return self._async_process.args

    @property
    def returncode(self) -> int | None:
        return self._async_process.returncode

    @property
    def stdout(self) -> SyncSandboxProcessOutputStream:
        return self._stdout

    @property
    def stderr(self) -> SyncSandboxProcessOutputStream:
        return self._stderr

    def wait(self, timeout: float | None = None) -> int:
        return anyio.run(self._async_process.wait, timeout)

    def terminate(self) -> None:
        anyio.run(self._async_process.terminate)

    def close(self) -> None:
        anyio.run(self._async_process.aclose)

    def __enter__(self) -> SyncSandboxProcess:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        anyio.run(self._async_process.__aexit__, exc_type, exc_val, exc_tb)


class SyncSandboxFilesystem:
    """Synchronous filesystem facade for a sandbox."""

    def __init__(self, async_sandbox: AsyncSandbox) -> None:
        self._async_sandbox = async_sandbox

    def open(
        self,
        path: str,
        mode: str = "r",
        encoding: str = "utf-8",
    ) -> SyncSandboxFile:
        """Open a file inside the sandbox using stdlib open() semantics."""
        async_file = self._async_sandbox.fs.open(path, mode=mode, encoding=encoding)
        return SyncSandboxFile(async_file)

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write raw bytes to a file in the sandbox."""
        anyio.run(self._async_sandbox.fs.write_bytes, path, data)

    def write_text(self, path: str, text: str, encoding: str = "utf-8") -> None:
        """Write text to a file in the sandbox."""
        anyio.run(self._async_sandbox.fs.write_text, path, text, encoding)

    def read_bytes(self, path: str) -> bytes:
        """Read raw bytes from a file in the sandbox."""
        return anyio.run(self._async_sandbox.fs.read_bytes, path)

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read text from a file in the sandbox."""
        return anyio.run(self._async_sandbox.fs.read_text, path, encoding)


class SyncSandbox:
    """Synchronous sandbox instance representing a connected sandbox environment."""

    def __init__(self, async_sandbox: AsyncSandbox) -> None:
        self._async_sandbox = async_sandbox
        self._fs = SyncSandboxFilesystem(async_sandbox)

    @property
    def id(self) -> str:
        return self._async_sandbox.id

    @property
    def fs(self) -> SyncSandboxFilesystem:
        if self._async_sandbox._closed:
            raise SandboxClosedError("Cannot access filesystem on a closed sandbox.")
        return self._fs

    def close(self) -> None:
        anyio.run(self._async_sandbox.close)

    def run_process(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        check: bool = False,
    ) -> ProcessResult:
        """Run a command to completion and capture stdout and stderr."""

        async def _run() -> ProcessResult:
            return await self._async_sandbox.run_process(
                args, cwd=cwd, env=env, timeout=timeout, check=check
            )

        return anyio.run(_run)

    def open_process(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        retry_interval: float = 0.1,
    ) -> SyncSandboxProcess:
        """Open a reconnectable process with iterable output streams."""

        async def _start() -> AsyncSandboxProcess:
            return await self._async_sandbox.open_process(
                args,
                cwd=cwd,
                env=env,
                timeout=timeout,
                retry_interval=retry_interval,
            )

        return SyncSandboxProcess(anyio.run(_start))

    def __enter__(self) -> SyncSandbox:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


class SyncSandboxConnectOperation:
    """Synchronous context manager and caller for connecting to a sandbox."""

    def __init__(
        self,
        backend: SandboxBackend | None = None,
        *,
        image: str = "alpine:latest",
        name: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        auto_stop: bool = True,
    ) -> None:
        self._async_op = async_connect(
            backend=backend,
            image=image,
            name=name,
            env=env,
            timeout=timeout,
            auto_stop=auto_stop,
        )
        self._async_sandbox: AsyncSandbox | None = None

    def connect(self) -> SyncSandbox:
        """Connect directly without a context manager."""
        async_sbx = anyio.run(self._async_op.__aenter__)
        return SyncSandbox(async_sbx)

    def __enter__(self) -> SyncSandbox:
        self._async_sandbox = anyio.run(self._async_op.__aenter__)
        return SyncSandbox(self._async_sandbox)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._async_sandbox is not None:
            anyio.run(self._async_op.__aexit__, exc_type, exc_val, exc_tb)


def connect_sync(
    backend: SandboxBackend | None = None,
    *,
    image: str = "alpine:latest",
    name: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    auto_stop: bool = True,
) -> SyncSandboxConnectOperation:
    """Connect to or create a sandbox environment synchronously.

    Example:
    ```python
    with sandbox.connect_sync() as sbx:
        with sbx.fs.open("/data.txt", "w") as f:
            f.write("hello")
        with sbx.fs.open("/data.txt", "r") as f:
            assert f.read() == "hello"
    ```
    """
    return SyncSandboxConnectOperation(
        backend=backend,
        image=image,
        name=name,
        env=env,
        timeout=timeout,
        auto_stop=auto_stop,
    )
