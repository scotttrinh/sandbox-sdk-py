"""Outside-in process execution tests against the local Docker adapter."""

from __future__ import annotations

import subprocess

import anyio
import pytest

from sandbox_sdk import SandboxTimeoutError, connect, connect_sync


def test_uploaded_weather_report_executes_and_appends_locally(tmp_path) -> None:
    """Upload a report program, execute it, then consume its output locally."""
    script = b"""from datetime import date
import os

print(f"{date(2026, 9, 3)} | NYC | {os.environ['CONDITIONS']} | 24 C")
"""
    local_report = tmp_path / "daily-weather.txt"

    with connect_sync(image="python:3.13-alpine") as sandbox:
        sandbox.fs.write_bytes("/workspace/weather.py", script)
        completed = sandbox.run(
            ["python", "weather.py"],
            cwd="/workspace",
            env={"CONDITIONS": "Clear"},
            check=True,
        )

    with local_report.open("ab") as report:
        report.write(completed.stdout)

    assert local_report.read_text() == "2026-09-03 | NYC | Clear | 24 C\n"
    assert completed.stderr == b""


@pytest.mark.anyio
async def test_wait_for_long_running_process_and_capture_separate_streams() -> None:
    async with connect(image="alpine:latest") as sandbox:
        process = await sandbox.start(
            ["sh", "-c", "sleep 0.1; echo ready; echo diagnostic >&2; exit 7"]
        )
        assert await process.poll() is None

        completed = await process.wait()

        assert completed.args[0:2] == ("sh", "-c")
        assert completed.returncode == 7
        assert completed.stdout == b"ready\n"
        assert completed.stderr == b"diagnostic\n"
        assert process.returncode == 7


@pytest.mark.anyio
async def test_stdout_and_stderr_are_anyio_byte_streams() -> None:
    async with connect(image="alpine:latest") as sandbox:
        process = await sandbox.start(
            [
                "sh",
                "-c",
                "printf first; sleep 0.1; printf second; printf warning >&2",
            ]
        )

        assert await process.stdout.receive(5) == b"first"
        assert await process.stdout.receive() == b"second"
        with pytest.raises(anyio.EndOfStream):
            await process.stdout.receive()
        assert await process.stderr.receive() == b"warning"
        with pytest.raises(anyio.EndOfStream):
            await process.stderr.receive()

        completed = await process.wait()
        assert completed.stdout == b"firstsecond"
        assert completed.stderr == b"warning"


def test_detached_process_survives_handle_context() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        with sandbox.start(["sh", "-c", "sleep 0.1; printf detached"], detached=True) as process:
            assert process.detached

        completed = process.wait(timeout=2)
        assert completed.stdout == b"detached"


def test_process_context_waits_on_normal_exit() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        with sandbox.start(["sh", "-c", "sleep 0.1; printf finished"]) as process:
            assert process.poll() is None

        assert process.returncode == 0
        assert process.wait().stdout == b"finished"


def test_process_context_terminates_on_exception() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        with pytest.raises(RuntimeError, match="abort work"):
            with sandbox.start(["sleep", "30"]) as process:
                raise RuntimeError("abort work")

        assert process.returncode is not None
        assert process.returncode != 0


def test_sync_output_stream() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        process = sandbox.start(["sh", "-c", "printf streamed"])
        assert process.stdout.receive(4) == b"stre"
        assert process.stdout.receive() == b"amed"
        with pytest.raises(anyio.EndOfStream):
            process.stdout.receive()
        process.wait()


def test_check_and_timeout_follow_subprocess_conventions() -> None:
    with connect_sync(image="alpine:latest") as sandbox:
        with pytest.raises(subprocess.CalledProcessError) as raised:
            sandbox.run(["sh", "-c", "echo bad >&2; exit 4"], check=True)
        assert raised.value.returncode == 4
        assert raised.value.stderr == b"bad\n"

        with pytest.raises(SandboxTimeoutError):
            sandbox.run(["sleep", "30"], timeout=0.05)

        process = sandbox.start(["sleep", "30"])
        with pytest.raises(SandboxTimeoutError):
            process.wait(timeout=0.05)
        process.terminate()
        process.wait(timeout=2)
