"""Synchronous Sandbox interface and context managers."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType

import anyio

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.client import AsyncSandbox
from sandbox_sdk.client import connect as async_connect
from sandbox_sdk.errors import SandboxClosedError


class SyncSandboxFilesystem:
    """Synchronous filesystem facade for a sandbox."""

    def __init__(self, async_sandbox: AsyncSandbox) -> None:
        self._async_sandbox = async_sandbox

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
    with connect_sync() as sbx:
        sbx.fs.write_text("/hello.txt", "world")
        assert sbx.fs.read_text("/hello.txt") == "world"
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
