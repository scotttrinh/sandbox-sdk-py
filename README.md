# Sandbox SDK (Python)

Generic Python SDK for sandbox-like execution environments (Docker, Vercel Sandbox, Sprites, Modal, etc.).

## Features

- **Generic & Extensible**: Decoupled from provider-specific assumptions via the `SandboxBackend` protocol.
- **Pythonic Context Managers**: Native support for `async with` and sync `with` context managers for automatic resource cleanup.
- **AnyIO Async Primitives**: Built for async event loops with AnyIO concurrency primitives.
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
    # Connect to a sandbox (starts a container or connects to an existing one)
    async with connect(image="alpine:latest") as sbx:
        # Write a file
        await sbx.fs.write_text("/workspace/hello.txt", "Hello from Sandbox SDK!")

        # Read it back
        content = await sbx.fs.read_text("/workspace/hello.txt")
        print(content)
        # Sandbox is cleanly stopped and removed upon exit

anyio.run(main)
```

### Synchronous Flow

```python
from sandbox_sdk import connect_sync

def main() -> None:
    with connect_sync(image="alpine:latest") as sbx:
        sbx.fs.write_text("/workspace/hello.txt", "Hello from sync Sandbox!")
        content = sbx.fs.read_text("/workspace/hello.txt")
        print(content)

if __name__ == "__main__":
    main()
```

## Architecture

- **`SandboxBackend` protocol**: Defines the minimal contract (`start`, `stop`, `write_bytes`, `read_bytes`) required for any provider.
- **`DockerSandboxBackend`**: Default local adapter bridging Docker via AnyIO worker threads (`anyio.to_thread.run_sync`).
- **`AsyncSandbox` / `SyncSandbox`**: High-level facades exposing filesystem operations and resource lifecycles.
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
