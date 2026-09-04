"""Hypothesis property-based tests for filesystem open() write and read roundtrip."""

from __future__ import annotations

from typing import Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.client import connect
from sandbox_sdk.errors import SandboxPathNotFoundError
from sandbox_sdk.models import (
    ProcessOptions,
    ProcessOutputChunk,
    SandboxConfig,
)


class InMemoryMockBackend(SandboxBackend):
    """Fast in-memory mock backend conforming to SandboxBackend protocol for property testing."""

    def __init__(self) -> None:
        self.files: dict[str, dict[str, bytes]] = {}
        self.running: set[str] = set()
        self._counter = 0

    async def start(self, config: SandboxConfig) -> str:
        self._counter += 1
        sandbox_id = f"sbx-{self._counter}"
        self.files[sandbox_id] = {}
        self.running.add(sandbox_id)
        return sandbox_id

    async def stop(self, sandbox_id: str) -> None:
        self.running.discard(sandbox_id)

    async def write_bytes(self, sandbox_id: str, path: str, data: bytes) -> None:
        if sandbox_id not in self.running:
            raise RuntimeError("Sandbox not running")
        self.files[sandbox_id][path] = data

    async def read_bytes(self, sandbox_id: str, path: str) -> bytes:
        if sandbox_id not in self.running:
            raise RuntimeError("Sandbox not running")
        if path not in self.files[sandbox_id]:
            raise SandboxPathNotFoundError(path)
        return self.files[sandbox_id][path]

    async def start_process(self, sandbox_id: str, options: ProcessOptions) -> str:
        raise NotImplementedError

    async def poll_process(self, sandbox_id: str, process_id: str) -> int | None:
        raise NotImplementedError

    async def terminate_process(self, sandbox_id: str, process_id: str) -> None:
        raise NotImplementedError

    async def read_process_output(
        self,
        sandbox_id: str,
        process_id: str,
        stream: Literal["stdout", "stderr"],
        offset: int,
        max_bytes: int,
    ) -> ProcessOutputChunk:
        raise NotImplementedError


@settings(max_examples=50)
@given(
    path=st.text(min_size=1, max_size=50).filter(lambda s: "\x00" not in s),
    content=st.text(),
)
@pytest.mark.anyio
async def test_property_roundtrip_text_open(path: str, content: str) -> None:
    """Any valid utf-8 string written with fs.open('w') is read back with fs.open('r')."""
    backend = InMemoryMockBackend()
    async with connect(backend=backend) as sbx:
        async with sbx.fs.open(path, "w") as f:
            await f.write(content)

        async with sbx.fs.open(path, "r") as f:
            assert await f.read() == content


@settings(max_examples=50)
@given(
    path=st.text(min_size=1, max_size=50).filter(lambda s: "\x00" not in s),
    content=st.binary(),
)
@pytest.mark.anyio
async def test_property_roundtrip_binary_open(path: str, content: bytes) -> None:
    """Any binary data written with fs.open('wb') is read back with fs.open('rb')."""
    backend = InMemoryMockBackend()
    async with connect(backend=backend) as sbx:
        async with sbx.fs.open(path, "wb") as f:
            await f.write(content)

        async with sbx.fs.open(path, "rb") as f:
            assert await f.read() == content
