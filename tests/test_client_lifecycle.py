"""Unit tests for context manager behaviors, open() semantics, and error handling."""

from __future__ import annotations

import pytest

from sandbox_sdk.adapters.docker import DockerSandboxBackend
from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.client import connect
from sandbox_sdk.errors import SandboxClosedError, SandboxFilesystemError
from sandbox_sdk.sync import connect_sync
from tests.test_property_roundtrip import InMemoryMockBackend


def test_backend_protocol_conformance() -> None:
    """Check that DockerSandboxBackend and MockBackend satisfy the runtime checkable protocol."""
    assert isinstance(DockerSandboxBackend, type)
    mock = InMemoryMockBackend()
    assert isinstance(mock, SandboxBackend)
    docker_backend = DockerSandboxBackend()
    assert isinstance(docker_backend, SandboxBackend)


@pytest.mark.anyio
async def test_async_await_without_context_manager() -> None:
    """Awaiting connect() directly creates a sandbox that remains open until explicitly closed."""
    backend = InMemoryMockBackend()
    sbx = await connect(backend=backend)
    try:
        assert sbx.id in backend.running
        async with sbx.fs.open("/file.txt", "w") as f:
            await f.write("content")
        async with sbx.fs.open("/file.txt", "r") as f:
            assert await f.read() == "content"
    finally:
        await sbx.close()

    assert sbx.id not in backend.running


@pytest.mark.anyio
async def test_closed_sandbox_access_raises_error() -> None:
    """Operating on a closed sandbox raises SandboxClosedError."""
    backend = InMemoryMockBackend()
    async with connect(backend=backend) as sbx:
        pass  # exits and closes

    with pytest.raises(SandboxClosedError):
        _ = sbx.fs


def test_sync_connect_without_context_manager() -> None:
    """Using sync connect().connect() creates a sandbox that remains open until closed."""
    backend = InMemoryMockBackend()
    op = connect_sync(backend=backend)
    sbx = op.connect()
    try:
        assert sbx.id in backend.running
        with sbx.fs.open("/file.txt", "w") as f:
            f.write("sync content")
        with sbx.fs.open("/file.txt", "r") as f:
            assert f.read() == "sync content"
    finally:
        sbx.close()

    assert sbx.id not in backend.running


@pytest.mark.anyio
async def test_file_mode_and_closed_errors() -> None:
    """Check writing to a read-only open file raises SandboxFilesystemError."""
    backend = InMemoryMockBackend()
    async with connect(backend=backend) as sbx:
        async with sbx.fs.open("/test.txt", "w") as f:
            await f.write("initial")

        async with sbx.fs.open("/test.txt", "r") as f:
            with pytest.raises(SandboxFilesystemError, match="File not open for writing"):
                await f.write("should fail")

        # After file exit context, f is closed
        with pytest.raises(SandboxClosedError):
            await f.read()
