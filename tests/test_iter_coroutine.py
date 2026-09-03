"""Tests verifying the iter_coroutine bridge mechanics for future sync/async backends."""

from __future__ import annotations

import pytest

from sandbox_sdk._internal.iter_coroutine import iter_coroutine


def test_iter_coroutine_success() -> None:
    """Non-suspending coroutines run to completion and return result."""

    async def simple_sync_wrapped() -> str:
        return "hello from iter_coroutine"

    res = iter_coroutine(simple_sync_wrapped())
    assert res == "hello from iter_coroutine"


def test_iter_coroutine_raises_on_yield() -> None:
    """If a coroutine attempts to suspend/yield, RuntimeError is raised."""

    class SuspendingAwaitable:
        def __await__(self):
            yield  # explicitly yields/suspends

    async def suspending_coro() -> None:
        await SuspendingAwaitable()

    with pytest.raises(RuntimeError, match="suspended unexpectedly"):
        iter_coroutine(suspending_coro())
