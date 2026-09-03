"""Outside-in integration test for Docker adapter.

Tests the fundamental flow: connect to sandbox -> write file -> read it back -> clean up.
"""

from __future__ import annotations

import pytest

from sandbox_sdk import (
    SandboxPathNotFoundError,
    connect,
    connect_sync,
)


@pytest.mark.anyio
async def test_async_docker_write_and_read_roundtrip() -> None:
    """Async connect, write file, read it back, verify automatic cleanup."""
    test_path = "/tmp/test_async.txt"
    test_content = "Hello from Async Sandbox SDK!"

    async with connect(image="alpine:latest") as sbx:
        assert sbx.id is not None
        # Write text
        await sbx.fs.write_text(test_path, test_content)

        # Read text back
        result = await sbx.fs.read_text(test_path)
        assert result == test_content

        # Write binary
        bin_path = "/tmp/test_async.bin"
        bin_content = b"\x00\x01\x02\x03\xff\xfe"
        await sbx.fs.write_bytes(bin_path, bin_content)

        # Read binary back
        bin_result = await sbx.fs.read_bytes(bin_path)
        assert bin_result == bin_content


def test_sync_docker_write_and_read_roundtrip() -> None:
    """Sync connect, write file, read it back, verify automatic cleanup."""
    test_path = "/tmp/test_sync.txt"
    test_content = "Hello from Sync Sandbox SDK!"

    with connect_sync(image="alpine:latest") as sbx:
        assert sbx.id is not None
        # Write text
        sbx.fs.write_text(test_path, test_content)

        # Read text back
        result = sbx.fs.read_text(test_path)
        assert result == test_content


@pytest.mark.anyio
async def test_read_non_existent_file_raises_not_found() -> None:
    """Reading a file that does not exist should raise SandboxPathNotFoundError."""
    async with connect(image="alpine:latest") as sbx:
        with pytest.raises(SandboxPathNotFoundError):
            await sbx.fs.read_bytes("/non_existent_path/should_fail.txt")
