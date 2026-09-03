"""Core sandbox abstraction, connection lifecycle, and stdlib metaphors."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.errors import SandboxClosedError
from sandbox_sdk.filesystem import AsyncSandboxFilesystem
from sandbox_sdk.models import SandboxConfig


class AsyncSandbox:
    """Asynchronous sandbox instance representing a connected sandbox environment."""

    def __init__(
        self,
        backend: SandboxBackend,
        sandbox_id: str,
        config: SandboxConfig,
        auto_stop: bool = True,
    ) -> None:
        self._backend = backend
        self._id = sandbox_id
        self._config = config
        self._auto_stop = auto_stop
        self._closed = False
        self._fs = AsyncSandboxFilesystem(backend, sandbox_id)

    @property
    def id(self) -> str:
        """The unique identifier of the sandbox."""
        return self._id

    @property
    def fs(self) -> AsyncSandboxFilesystem:
        """Access filesystem operations within the sandbox."""
        if self._closed:
            raise SandboxClosedError("Cannot access filesystem on a closed sandbox.")
        return self._fs

    async def close(self) -> None:
        """Stop and clean up the sandbox."""
        if not self._closed:
            self._closed = True
            await self._backend.stop(self._id)

    async def __aenter__(self) -> AsyncSandbox:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()


class AsyncSandboxConnectOperation:
    """Awaitable and async context manager for connecting to/creating a sandbox.

    Supports both:
    ```python
    # Context manager cleans up automatically on exit:
    async with sandbox.connect(...) as sbx:
        ...

    # Direct await keeps the sandbox open until sbx.close():
    sbx = await sandbox.connect(...)
    ```
    """

    def __init__(
        self,
        backend: SandboxBackend,
        config: SandboxConfig,
        auto_stop: bool = True,
    ) -> None:
        self._backend = backend
        self._config = config
        self._auto_stop = auto_stop
        self._sandbox: AsyncSandbox | None = None

    def __await__(self):
        async def _connect():
            sandbox_id = await self._backend.start(self._config)
            return AsyncSandbox(
                backend=self._backend,
                sandbox_id=sandbox_id,
                config=self._config,
                auto_stop=False,
            )

        return _connect().__await__()

    async def __aenter__(self) -> AsyncSandbox:
        sandbox_id = await self._backend.start(self._config)
        self._sandbox = AsyncSandbox(
            backend=self._backend,
            sandbox_id=sandbox_id,
            config=self._config,
            auto_stop=self._auto_stop,
        )
        return self._sandbox

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._sandbox is not None:
            await self._sandbox.close()


def connect(
    backend: SandboxBackend | None = None,
    *,
    image: str = "alpine:latest",
    name: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    auto_stop: bool = True,
) -> AsyncSandboxConnectOperation:
    """Connect to or create a sandbox environment asynchronously.

    Example:
    ```python
    async with sandbox.connect() as sbx:
        async with sbx.fs.open("/data.txt", "w") as f:
            await f.write("hello world")
        async with sbx.fs.open("/data.txt", "r") as f:
            assert await f.read() == "hello world"
    ```
    """
    if backend is None:
        from sandbox_sdk.adapters.docker import DockerSandboxBackend

        backend = DockerSandboxBackend()

    config = SandboxConfig(
        image=image,
        name=name,
        env=env,
        timeout=timeout,
    )
    return AsyncSandboxConnectOperation(backend=backend, config=config, auto_stop=auto_stop)
