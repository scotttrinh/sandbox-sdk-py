"""Iter-coroutine execution runner for non-suspending coroutines."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import TypeVar

_T = TypeVar("_T")


def iter_coroutine(coro: Coroutine[None, None, _T]) -> _T:
    """Execute a non-suspending coroutine synchronously.

    Drives a coroutine forward exactly one step. If the coroutine completes
    without suspending (yielding), its return value is extracted from the
    StopIteration exception. If it suspends, RuntimeError is raised.
    """
    try:
        coro.send(None)
    except StopIteration as ex:
        return ex.value
    else:
        raise RuntimeError(f"Coroutine {coro!r} suspended unexpectedly in synchronous runner!")
    finally:
        coro.close()
