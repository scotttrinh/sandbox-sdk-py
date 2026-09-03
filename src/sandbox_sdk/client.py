"""Core sandbox abstraction and context managers."""

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

    Like vercel-py's CreateSandboxOperation:
    - Awaiting it returns an AsyncSandbox without automatic cleanup on scope exit.
    - Using `async with` returns an AsyncSandbox and automatically cleans it up on exit.
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
                auto_stop=False,  # awaiting does not auto-stop on scope exit
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

    Can be awaited directly or used as an asynchronous context manager:
    ```python
    async with connect() as sbx:
        await sbx.fs.write_text("/hello.txt", "world")
        assert await sbx.fs.read_text("/hello.txt") == "world"
    ```

    Args:
        backend: Sandbox backend adapter (defaults to DockerSandboxBackend).
        image: Container or environment image reference.
        name: Optional name for the sandbox instance.
        env: Environment variables to populate in the sandbox.
        timeout: Operation timeout in seconds.
        auto_stop: Whether exiting context manager automatically stops the sandbox.
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
