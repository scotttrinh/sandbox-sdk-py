"""Docker adapter implementation for SandboxBackend using AnyIO primitives."""

from __future__ import annotations

import io
import os
import shlex
import tarfile
import time
import uuid
from typing import TYPE_CHECKING, Literal

import anyio
import anyio.to_thread

from sandbox_sdk.backend import SandboxBackend
from sandbox_sdk.errors import (
    SandboxConnectionError,
    SandboxFilesystemError,
    SandboxPathNotFoundError,
    SandboxProcessError,
    SandboxTimeoutError,
)
from sandbox_sdk.models import (
    ProcessOptions,
    ProcessOutputChunk,
    ProcessResult,
    SandboxConfig,
)

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

    @staticmethod
    def _command(options: ProcessOptions) -> str:
        if not options.args:
            raise ValueError("args must contain at least one item")
        command = shlex.join(options.args)
        if options.env:
            assignments = " ".join(
                shlex.quote(f"{key}={value}") for key, value in options.env.items()
            )
            command = f"env {assignments} {command}"
        if options.cwd is not None:
            command = f"cd {shlex.quote(options.cwd)} && {command}"
        return command

    async def run_process(
        self, sandbox_id: str, options: ProcessOptions, timeout: float | None = None
    ) -> ProcessResult:
        """Execute a command in the container and capture both output streams."""
        process_id = await self.start_process(sandbox_id, options)
        try:
            result = await self.wait_process(sandbox_id, process_id, timeout)
        except SandboxTimeoutError:
            await self.terminate_process(sandbox_id, process_id)
            await self.wait_process(sandbox_id, process_id)
            raise
        return ProcessResult(options.args, result.returncode, result.stdout, result.stderr)

    async def start_process(self, sandbox_id: str, options: ProcessOptions) -> str:
        """Start a command using files for provider-independent deferred collection."""
        process_id = uuid.uuid4().hex
        process_dir = f"/tmp/.sandbox-sdk-processes/{process_id}"
        command = self._command(options)
        wrapper = (
            f"mkdir -p {process_dir}; "
            f"({command}) >{process_dir}/stdout 2>{process_dir}/stderr & "
            f"child=$!; echo $child >{process_dir}/pid; "
            f"wait $child; echo $? >{process_dir}/returncode"
        )

        def _sync_start() -> None:
            try:
                container = self._get_client().containers.get(sandbox_id)
                container.exec_run(["/bin/sh", "-c", wrapper], detach=True)
            except Exception as err:
                raise SandboxProcessError(f"Failed to start {options.args!r}: {err}") from err

        await anyio.to_thread.run_sync(_sync_start)
        return process_id

    async def poll_process(self, sandbox_id: str, process_id: str) -> int | None:
        """Read a process return-code sentinel when present."""
        process_dir = f"/tmp/.sandbox-sdk-processes/{process_id}"

        def _sync_poll() -> int | None:
            try:
                container = self._get_client().containers.get(sandbox_id)
                result = container.exec_run(
                    [
                        "/bin/sh",
                        "-c",
                        f"test -f {process_dir}/returncode && cat {process_dir}/returncode",
                    ]
                )
            except Exception as err:
                raise SandboxProcessError(f"Failed to inspect process {process_id}: {err}") from err
            if result.exit_code != 0:
                return None
            try:
                return int(result.output.strip())
            except ValueError as err:
                raise SandboxProcessError(f"Invalid state for process {process_id}") from err

        return await anyio.to_thread.run_sync(_sync_poll)

    async def wait_process(
        self, sandbox_id: str, process_id: str, timeout: float | None = None
    ) -> ProcessResult:
        """Wait for a deferred command and collect its captured output."""
        process_dir = f"/tmp/.sandbox-sdk-processes/{process_id}"

        async def _wait() -> ProcessResult:
            while (returncode := await self.poll_process(sandbox_id, process_id)) is None:
                await anyio.sleep(0.05)

            def _sync_collect() -> tuple[bytes, bytes]:
                try:
                    container = self._get_client().containers.get(sandbox_id)
                    stdout = container.exec_run(["cat", f"{process_dir}/stdout"]).output
                    stderr = container.exec_run(["cat", f"{process_dir}/stderr"]).output
                    return stdout, stderr
                except Exception as err:
                    raise SandboxProcessError(
                        f"Failed to collect process {process_id}: {err}"
                    ) from err

            stdout, stderr = await anyio.to_thread.run_sync(_sync_collect)
            return ProcessResult((), returncode, stdout, stderr)

        try:
            if timeout is None:
                return await _wait()
            with anyio.fail_after(timeout):
                return await _wait()
        except TimeoutError as err:
            raise SandboxTimeoutError(f"Process timed out after {timeout} seconds") from err

    async def terminate_process(self, sandbox_id: str, process_id: str) -> None:
        """Send SIGTERM to a deferred command."""
        process_dir = f"/tmp/.sandbox-sdk-processes/{process_id}"

        def _sync_terminate() -> None:
            try:
                container = self._get_client().containers.get(sandbox_id)
                result = container.exec_run(
                    [
                        "/bin/sh",
                        "-c",
                        f"while ! test -f {process_dir}/pid; do sleep 0.01; done; "
                        f"kill $(cat {process_dir}/pid)",
                    ]
                )
                if result.exit_code != 0:
                    raise SandboxProcessError(f"Process {process_id} could not be terminated")
            except SandboxProcessError:
                raise
            except Exception as err:
                raise SandboxProcessError(
                    f"Failed to terminate process {process_id}: {err}"
                ) from err

        await anyio.to_thread.run_sync(_sync_terminate)

    async def read_process_output(
        self,
        sandbox_id: str,
        process_id: str,
        stream: Literal["stdout", "stderr"],
        offset: int,
        max_bytes: int,
    ) -> ProcessOutputChunk:
        """Wait for and read the next available output chunk."""
        process_dir = f"/tmp/.sandbox-sdk-processes/{process_id}"

        def _sync_read() -> ProcessOutputChunk:
            try:
                container = self._get_client().containers.get(sandbox_id)
                result = container.exec_run(
                    [
                        "/bin/sh",
                        "-c",
                        f"dd if={process_dir}/{stream} bs=1 skip={offset} count={max_bytes} "
                        f"2>/dev/null; test -f {process_dir}/returncode",
                    ],
                    demux=True,
                )
            except Exception as err:
                raise SandboxProcessError(
                    f"Failed to read {stream} for process {process_id}: {err}"
                ) from err
            stdout, _stderr = result.output or (b"", b"")
            return ProcessOutputChunk(stdout or b"", result.exit_code == 0)

        while True:
            chunk = await anyio.to_thread.run_sync(_sync_read)
            if chunk.data or chunk.eof:
                return chunk
            await anyio.sleep(0.05)
