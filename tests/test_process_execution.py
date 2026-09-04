"""Outside-in process API tests against Docker and a reconnecting backend."""

from __future__ import annotations

import subprocess

import pytest

from sandbox_sdk import SandboxConnectionError, SandboxTimeoutError, connect, connect_sync
from sandbox_sdk.adapters.docker import DockerSandboxBackend


def test_uploaded_weather_report_executes_and_appends_locally(tmp_path) -> None:
    script = b"""from datetime import date
import os
print(f"{date(2026, 9, 3)} | NYC | {os.environ['CONDITIONS']} | 24 C")
"""
    local_report = tmp_path / "daily-weather.txt"
    with connect_sync(image="python:3.13-alpine") as sandbox:
        sandbox.fs.write_bytes("/workspace/weather.py", script)
        completed = sandbox.run_process(
            ["python", "weather.py"],
            cwd="/workspace",
            env={"CONDITIONS": "Clear"},
            check=True,
        )
    with local_report.open("ab") as report:
        report.write(completed.stdout)
    assert local_report.read_text() == "2026-09-03 | NYC | Clear | 24 C\n"


@pytest.mark.anyio
async def test_open_process_streams_are_iterable_and_wait_returns_exit_code() -> None:
    async with connect(image="alpine:latest") as sandbox:
        async with await sandbox.open_process(
            ["sh", "-c", "printf first; sleep 0.1; printf second; echo warning >&2; exit 7"]
        ) as process:
            stdout = b"".join([chunk async for chunk in process.stdout])
            stderr = b"".join([chunk async for chunk in process.stderr])
            assert await process.wait() == 7
        assert stdout == b"firstsecond"
        assert stderr == b"warning\n"
        assert process.returncode == 7


def test_sync_open_process_streams_are_iterable() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        with sandbox.open_process(["sh", "-c", "printf streamed"]) as process:
            assert b"".join(process.stdout) == b"streamed"
        assert process.returncode == 0


def test_process_context_waits_normally_and_terminates_on_exception() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        with sandbox.open_process(["sh", "-c", "sleep 0.1; exit 3"]) as completed:
            pass
        assert completed.returncode == 3

        with pytest.raises(RuntimeError, match="abort"):
            with sandbox.open_process(["sleep", "30"]) as interrupted:
                raise RuntimeError("abort")
        assert interrupted.returncode is not None


def test_run_process_check_and_timeouts() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        with pytest.raises(subprocess.CalledProcessError) as raised:
            sandbox.run_process(["sh", "-c", "echo bad >&2; exit 4"], check=True)
        assert raised.value.stderr == b"bad\n"
        with pytest.raises(SandboxTimeoutError):
            sandbox.run_process(["sleep", "30"], timeout=0.05)

        process = sandbox.open_process(["sleep", "30"], timeout=2)
        with pytest.raises(SandboxTimeoutError):
            process.wait(timeout=0.05)
        process.terminate()
        assert process.wait() != 0


class DisconnectingDockerBackend(DockerSandboxBackend):
    """Simulate dropped provider connections while the process keeps running."""

    def __init__(self) -> None:
        super().__init__()
        self.poll_failures = 2
        self.read_failures = 2

    async def poll_process(self, sandbox_id: str, process_id: str) -> int | None:
        if self.poll_failures:
            self.poll_failures -= 1
            raise SandboxConnectionError("connection dropped")
        return await super().poll_process(sandbox_id, process_id)

    async def read_process_output(self, *args, **kwargs):
        if self.read_failures:
            self.read_failures -= 1
            raise SandboxConnectionError("connection dropped")
        return await super().read_process_output(*args, **kwargs)


@pytest.mark.anyio
async def test_open_process_reconnects_for_streaming_and_exit_code() -> None:
    backend = DisconnectingDockerBackend()
    async with connect(backend=backend, image="alpine:latest") as sandbox:
        process = await sandbox.open_process(
            ["sh", "-c", "sleep 0.1; printf recovered"], timeout=3, retry_interval=0.01
        )
        assert b"".join([chunk async for chunk in process.stdout]) == b"recovered"
        assert await process.wait() == 0
    assert backend.read_failures == 0
    assert backend.poll_failures == 0


@pytest.mark.anyio
async def test_stream_receive_respects_timeout_during_reconnect() -> None:
    backend = DisconnectingDockerBackend()
    backend.read_failures = 10_000
    async with connect(backend=backend, image="alpine:latest") as sandbox:
        process = await sandbox.open_process(["sleep", "30"], timeout=0.05, retry_interval=0.01)
        with pytest.raises(SandboxTimeoutError):
            await process.stdout.receive()
        await process.terminate()
