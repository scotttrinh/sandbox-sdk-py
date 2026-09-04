# Sandbox SDK (Python)

Generic Python SDK for sandbox-like execution environments (Docker, Vercel Sandbox, Sprites, Modal, etc.).

## Features

- **Generic & Extensible**: Decoupled from provider-specific assumptions via the `SandboxBackend` protocol.
- **Pythonic Stdlib Metaphors**: File operations use `with sbx.fs.open(path, "w") as f` / `async with sbx.fs.open(...)` context managers, line-iteration, and flushing just like Python's built-in file handles.
- **Natural Connection Context Managers**: `with connect(...)` or `async with connect(...)` handles starting, running, and automatic stopping/destruction of the sandbox.
- **AnyIO Async Primitives**: Native support for AnyIO concurrency primitives.
- **Sync & Async Parity**: First-class synchronous API (`connect_sync`) alongside the asynchronous API (`connect`).
- **Short & Long-Running Processes**: `run_process()` captures short jobs, while `open_process()` exposes reconnectable, iterable output streams for long-running work.
- **Designed for Iter-Coroutine Shared Backends**: Ready for unification of sync and async execution via coroutine driver patterns.
- **Docker Adapter**: Local sandbox execution backed by Docker.
- **Strict Typing & Quality**: Verified with `ty`, `ruff`, `poethepoet`, `pytest`, and property-based testing with `hypothesis`.

## Installation

```bash
uv add sandbox-sdk
```

Or with Docker support:

```bash
uv add "sandbox-sdk[docker]"
```

## Quick Start: Write and Read a File

### Asynchronous Flow

```python
import anyio
from sandbox_sdk import connect

async def main() -> None:
    # Connect to a sandbox (starts container and automatically cleans up on exit)
    async with connect(image="alpine:latest") as sbx:
        # Standard open() context manager on the filesystem interface
        async with sbx.fs.open("/workspace/hello.txt", "w") as f:
            await f.write("Hello from Sandbox SDK!\n")

        # Standard open() context manager for reading
        async with sbx.fs.open("/workspace/hello.txt", "r") as f:
            content = await f.read()
            print(content)

anyio.run(main)
```

### Synchronous Flow

```python
from sandbox_sdk import connect_sync

def main() -> None:
    with connect_sync(image="alpine:latest") as sbx:
        with sbx.fs.open("/workspace/hello.txt", "w") as f:
            f.write("Hello from sync Sandbox!\n")

        with sbx.fs.open("/workspace/hello.txt", "r") as f:
            content = f.read()
            print(content)

if __name__ == "__main__":
    main()
```

## Architecture

- **`SandboxBackend` protocol**: Defines provider-neutral lifecycle, filesystem, and process capabilities.
- **`DockerSandboxBackend`**: Default local adapter bridging Docker via AnyIO worker threads (`anyio.to_thread.run_sync`).
- **`AsyncSandbox` / `SyncSandbox`**: High-level facades providing Python stdlib-style `open()` context managers and lifecycle management.
- **`AsyncSandboxFile` / `SyncSandboxFile`**: File-like handle implementations with buffer streaming, reading, writing, flushing, and line iteration.
- **`_internal.iter_coroutine`**: Driver for executing transport-agnostic coroutines synchronously without suspending.

## Execute an Uploaded Script

The result uses bytes by default, like `subprocess.run`, so it can be streamed directly into a
local binary file:

```python
from pathlib import Path

from sandbox_sdk import connect_sync

script = b'''from datetime import date
print(f"{date.today()} | NYC | Clear | 24 C")
'''

with connect_sync(image="python:3.13-alpine") as sandbox:
    sandbox.fs.write_bytes("/workspace/weather.py", script)
    result = sandbox.run_process(
        ["python", "weather.py"], cwd="/workspace", check=True
    )

with Path("weather-history.txt").open("ab") as report:
    report.write(result.stdout)
```

For longer-running work, `open_process()` returns an AnyIO-style process handle. Its `stdout` and
`stderr` properties are independent, iterable byte receive streams, and `wait()` returns the exit
code. Reads and exit polling resume from the last byte after transient connection drops:

```python
async with connect() as sandbox:
    process = await sandbox.open_process(["sh", "-c", "echo ready; echo note >&2"])
    async for chunk in process.stdout:
        print(chunk.decode(), end="")
    returncode = await process.wait(timeout=5)
```

A normal process context waits for completion, mirroring AnyIO's process resource. If the context
body raises or is cancelled, it terminates and reaps the process before propagating the error.
The process handle is intentionally independent from the transport connection, so it can reconnect
until its operation timeout is exhausted:

```python
with connect_sync() as sandbox:
    with sandbox.open_process(["sh", "-c", "sleep 1; echo ready"], timeout=10) as process:
        for chunk in process.stdout:
            print(chunk.decode(), end="")
    assert process.returncode == 0
```

## Development & Verification

Run checks and test suite:

```bash
uv run poe check
```

Or individual tasks:

```bash
uv run poe lint       # ruff check
uv run poe format     # ruff format check
uv run poe typecheck  # ty check
uv run poe test       # pytest & hypothesis
```
