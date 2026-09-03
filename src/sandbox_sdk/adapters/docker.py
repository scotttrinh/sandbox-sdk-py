"""Docker adapter implementation for SandboxBackend using AnyIO primitives."""

from __future__ import annotations

import io
import os
import tarfile
import time
from typing import TYPE_CHECKING

import anyio
import anyio.to_thread

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.errors import (
    SandboxConnectionError,
    SandboxFilesystemError,
    SandboxPathNotFoundError,
)
from sandbox_sdk.models import SandboxConfig

if TYPE_CHECKING:
    import docker


class DockerSandboxBackend(SandboxBackend):
    """Docker-based backend for running sandboxes locally.

    Uses anyio.to_thread.run_sync to bridge Docker's blocking Python client
    into AnyIO-compliant async execution.
    """

    def __init__(self, client: docker.DockerClient | None = None) -> None:
        self._client_instance = client

    def _get_client(self) -> docker.DockerClient:
        if self._client_instance is not None:
            return self._client_instance
        try:
            import docker

            self._client_instance = docker.from_env()
            return self._client_instance
        except Exception as err:
            raise SandboxConnectionError(f"Failed to initialize Docker client: {err}") from err

    async def start(self, config: SandboxConfig) -> str:
        """Start a new container for the sandbox."""

        def _sync_start() -> str:
            client = self._get_client()
            container = client.containers.run(
                image=config.image,
                name=config.name,
                environment=dict(config.env) if config.env else None,
                command="tail -f /dev/null",  # keep container running
                detach=True,
                auto_remove=False,
            )
            return str(container.id)

        try:
            return await anyio.to_thread.run_sync(_sync_start)
        except Exception as err:
            raise SandboxConnectionError(f"Failed to start Docker sandbox: {err}") from err

    async def stop(self, sandbox_id: str) -> None:
        """Stop and remove the container."""

        def _sync_stop() -> None:
            client = self._get_client()
            try:
                container = client.containers.get(sandbox_id)
                container.stop(timeout=5)
                container.remove(v=True, force=True)
            except Exception:
                pass

        await anyio.to_thread.run_sync(_sync_stop)

    async def write_bytes(self, sandbox_id: str, path: str, data: bytes) -> None:
        """Write bytes to a file inside the container using tar archive streaming."""

        def _sync_write() -> None:
            client = self._get_client()
            try:
                container = client.containers.get(sandbox_id)
            except Exception as err:
                raise SandboxConnectionError(f"Container {sandbox_id} not found: {err}") from err

            # Docker put_archive requires a tar stream and an extraction directory.
            dirname, filename = os.path.split(path)
            if not dirname:
                dirname = "/"
            if not filename:
                raise SandboxFilesystemError(f"Invalid file path: {path}")

            # Ensure parent directory exists
            exit_code, output = container.exec_run(f"mkdir -p {dirname}")
            if exit_code != 0:
                raise SandboxFilesystemError(
                    f"Failed to create directory {dirname}: {output.decode(errors='replace')}"
                )

            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode="w") as tar:
                tarinfo = tarfile.TarInfo(name=filename)
                tarinfo.size = len(data)
                tarinfo.mtime = int(time.time())
                tarinfo.mode = 0o644
                tar.addfile(tarinfo, io.BytesIO(data))

            tar_stream.seek(0)
            try:
                success = container.put_archive(path=dirname, data=tar_stream.getvalue())
                if not success:
                    raise SandboxFilesystemError(f"Docker put_archive failed for path: {path}")
            except Exception as err:
                raise SandboxFilesystemError(f"Failed writing to {path}: {err}") from err

        await anyio.to_thread.run_sync(_sync_write)

    async def read_bytes(self, sandbox_id: str, path: str) -> bytes:
        """Read bytes from a file inside the container using tar archive streaming."""

        def _sync_read() -> bytes:
            client = self._get_client()
            try:
                container = client.containers.get(sandbox_id)
            except Exception as err:
                raise SandboxConnectionError(f"Container {sandbox_id} not found: {err}") from err

            try:
                stream, _stat = container.get_archive(path)
            except Exception as err:
                # Docker raises docker.errors.NotFound if path doesn't exist
                if "404" in str(err) or "not found" in str(err).lower():
                    raise SandboxPathNotFoundError(path) from err
                raise SandboxFilesystemError(f"Failed to get archive for {path}: {err}") from err

            # Read stream into tarfile
            file_obj = io.BytesIO()
            for chunk in stream:
                file_obj.write(chunk)
            file_obj.seek(0)

            try:
                with tarfile.open(fileobj=file_obj, mode="r:*") as tar:
                    member = tar.next()
                    if member is None or not member.isfile():
                        raise SandboxPathNotFoundError(path)
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        raise SandboxFilesystemError(f"Could not extract file {path}")
                    return extracted.read()
            except SandboxPathNotFoundError:
                raise
            except Exception as err:
                raise SandboxFilesystemError(f"Error extracting {path} from tar: {err}") from err

        return await anyio.to_thread.run_sync(_sync_read)
