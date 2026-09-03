"""Base transport and filesystem operations shared across sync and async."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    """Abstraction for executing sandbox operations."""

    async def write_bytes(self, sandbox_id: str, path: str, data: bytes) -> None: ...

    async def read_bytes(self, sandbox_id: str, path: str) -> bytes: ...
