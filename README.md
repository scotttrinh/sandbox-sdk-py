# Sandbox SDK (Python)

Generic Python SDK for sandbox-like execution environments (Docker, Vercel Sandbox, Sprites, Modal, etc.).

## Features

- **Generic & Extensible**: Decoupled from provider-specific assumptions via the `SandboxBackend` protocol.
- **Pythonic Stdlib Metaphors**: File operations use `with sbx.open(path, "w") as f` / `async with sbx.open(...)` context managers, line-iteration, and flushing just like Python's built-in file handles.
- **Natural Connection Context Managers**: `with connect(...)` or `async with connect(...)` handles starting, running, and automatic stopping/destruction of the sandbox.
- **AnyIO Async Primitives**: Native support for AnyIO concurrency primitives.
- **Sync & Async Parity**: First-class synchronous API (`connect_sync`) alongside the asynchronous API (`connect`).
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
        # Standard open() context manager for writing
        async with sbx.open("/workspace/hello.txt", "w") as f:
            await f.write("Hello from Sandbox SDK!\n")

        # Standard open() context manager for reading
        async with sbx.open("/workspace/hello.txt", "r") as f:
            content = await f.read()
            print(content)

anyio.run(main)
```

### Synchronous Flow

```python
from sandbox_sdk import connect_sync

def main() -> None:
    with connect_sync(image="alpine:latest") as sbx:
        with sbx.open("/workspace/hello.txt", "w") as f:
            f.write("Hello from sync Sandbox!\n")

        with sbx.open("/workspace/hello.txt", "r") as f:
            content = f.read()
            print(content)

if __name__ == "__main__":
    main()
```

## Architecture

- **`SandboxBackend` protocol**: Defines the minimal contract (`start`, `stop`, `write_bytes`, `read_bytes`) required for any provider.
- **`DockerSandboxBackend`**: Default local adapter bridging Docker via AnyIO worker threads (`anyio.to_thread.run_sync`).
- **`AsyncSandbox` / `SyncSandbox`**: High-level facades providing Python stdlib-style `open()` context managers and lifecycle management.
- **`AsyncSandboxFile` / `SyncSandboxFile`**: File-like handle implementations with buffer streaming, reading, writing, flushing, and line iteration.
- **`_internal.iter_coroutine`**: Driver for executing transport-agnostic coroutines synchronously without suspending.

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
