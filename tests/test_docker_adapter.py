"""Outside-in integration tests for Docker adapter testing stdlib open() context managers."""

from __future__ import annotations

import pytest

from sandbox_sdk import (
    SandboxPathNotFoundError,
    connect,
    connect_sync,
)


@pytest.mark.anyio
async def test_async_docker_open_context_manager_roundtrip() -> None:
    """Async connect -> async open("w") -> write -> async open("r") -> read back."""
    test_path = "/tmp/test_open.txt"
    test_content = "Hello from Async open() context manager!"

    async with connect(image="alpine:latest") as sbx:
        # Standard open() context manager in write mode
        async with sbx.open(test_path, "w") as f:
            assert f.writable()
            await f.write(test_content)

        # Standard open() context manager in read mode
        async with sbx.open(test_path, "r") as f:
            assert f.readable()
            result = await f.read()
            assert result == test_content


def test_sync_docker_open_context_manager_roundtrip() -> None:
    """Sync connect_sync -> open("wb") -> write -> open("rb") -> read back."""
    test_path = "/tmp/test_sync_open.bin"
    test_content = b"\xde\xad\xbe\xef\x01\x02\x03\x04"

    with connect_sync(image="alpine:latest") as sbx:
        with sbx.open(test_path, "wb") as f:
            assert f.writable()
            f.write(test_content)

        with sbx.open(test_path, "rb") as f:
            assert f.readable()
            result = f.read()
            assert result == test_content


@pytest.mark.anyio
async def test_read_non_existent_file_raises_not_found() -> None:
    """Opening non-existent file in read mode raises SandboxPathNotFoundError."""
    async with connect(image="alpine:latest") as sbx:
        with pytest.raises(SandboxPathNotFoundError):
            async with sbx.open("/non_existent/missing.txt", "r"):
                pass
