"""Sandbox SDK: A generic Python SDK for isolated sandbox environments."""

from __future__ import annotations

from sandbox_sdk.adapters.docker import DockerSandboxBackend
from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.client import AsyncSandbox, AsyncSandboxConnectOperation, connect
from sandbox_sdk.errors import (
    SandboxClosedError,
    SandboxConnectionError,
    SandboxError,
    SandboxFilesystemError,
    SandboxPathNotFoundError,
    SandboxProcessError,
    SandboxTimeoutError,
)
from sandbox_sdk.file import AsyncSandboxFile, SyncSandboxFile
from sandbox_sdk.filesystem import AsyncSandboxFilesystem
from sandbox_sdk.models import ProcessOptions, ProcessOutputChunk, ProcessResult, SandboxConfig
from sandbox_sdk.process import AsyncSandboxProcess, SandboxProcessOutputStream
from sandbox_sdk.sync import (
    SyncSandbox,
    SyncSandboxConnectOperation,
    SyncSandboxFilesystem,
    SyncSandboxProcess,
    SyncSandboxProcessOutputStream,
    connect_sync,
)

__all__ = [
    "AsyncSandbox",
    "AsyncSandboxConnectOperation",
    "AsyncSandboxFile",
    "AsyncSandboxFilesystem",
    "AsyncSandboxProcess",
    "DockerSandboxBackend",
    "ProcessOptions",
    "ProcessOutputChunk",
    "ProcessResult",
    "SandboxBackend",
    "SandboxClosedError",
    "SandboxConfig",
    "SandboxConnectionError",
    "SandboxError",
    "SandboxFilesystemError",
    "SandboxPathNotFoundError",
    "SandboxProcessError",
    "SandboxProcessOutputStream",
    "SandboxTimeoutError",
    "SyncSandbox",
    "SyncSandboxConnectOperation",
    "SyncSandboxFile",
    "SyncSandboxFilesystem",
    "SyncSandboxProcess",
    "SyncSandboxProcessOutputStream",
    "connect",
    "connect_sync",
]
