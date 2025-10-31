"""
Utilities for testing async code in the multi-agent system.

Provides helpers for:
- Running async functions in tests
- Waiting for conditions with timeout
- Collecting results from async generators
"""

import asyncio
import time
from typing import Any, Callable, List, Optional, TypeVar


T = TypeVar('T')


async def run_async_test(coro, timeout: float = 5.0):
    """
    Run an async test with timeout.

    Args:
        coro: Coroutine to run
        timeout: Maximum seconds to wait

    Returns:
        Result of the coroutine

    Raises:
        asyncio.TimeoutError: If timeout exceeded
    """
    return await asyncio.wait_for(coro, timeout=timeout)


async def wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = 5.0,
    check_interval: float = 0.1,
    error_message: Optional[str] = None
) -> bool:
    """
    Wait for a condition to become true.

    Args:
        condition: Callable that returns True when condition met
        timeout: Maximum seconds to wait
        check_interval: Seconds between checks
        error_message: Custom error message if timeout

    Returns:
        True if condition met within timeout

    Raises:
        asyncio.TimeoutError: If condition not met within timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        if condition():
            return True
        await asyncio.sleep(check_interval)

    # Timeout
    msg = error_message or f"Condition not met within {timeout}s"
    raise asyncio.TimeoutError(msg)


async def collect_async_results(
    async_gen,
    max_items: Optional[int] = None,
    timeout: float = 5.0
) -> List[Any]:
    """
    Collect results from an async generator.

    Args:
        async_gen: Async generator to collect from
        max_items: Maximum items to collect (None = all)
        timeout: Maximum seconds to wait for collection

    Returns:
        List of items from generator

    Raises:
        asyncio.TimeoutError: If timeout exceeded
    """
    results = []

    async def _collect():
        count = 0
        async for item in async_gen:
            results.append(item)
            count += 1
            if max_items and count >= max_items:
                break

    await asyncio.wait_for(_collect(), timeout=timeout)
    return results


class AsyncContextManager:
    """
    Helper for testing async context managers.

    Usage:
        async with AsyncContextManager(some_async_cm) as obj:
            # Test code
    """

    def __init__(self, async_cm):
        self._async_cm = async_cm
        self._obj = None

    async def __aenter__(self):
        self._obj = await self._async_cm.__aenter__()
        return self._obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._async_cm.__aexit__(exc_type, exc_val, exc_tb)


class AsyncMockCallTracker:
    """
    Track calls to async mock methods.

    Usage:
        tracker = AsyncMockCallTracker()
        mock_method = tracker.create_mock()

        await mock_method("arg1", kwarg="value")

        assert tracker.call_count == 1
        assert tracker.calls[0]["args"] == ("arg1",)
    """

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.call_count = 0

    def create_mock(self, return_value: Any = None):
        """Create an async mock that tracks calls."""
        async def mock_method(*args, **kwargs):
            self.calls.append({
                "args": args,
                "kwargs": kwargs,
                "timestamp": time.time()
            })
            self.call_count += 1
            return return_value

        return mock_method

    def reset(self):
        """Reset tracking state."""
        self.calls.clear()
        self.call_count = 0

    def get_call_args(self, call_index: int = 0):
        """Get args from a specific call."""
        if call_index >= len(self.calls):
            raise IndexError(f"Call {call_index} not found")
        return self.calls[call_index]["args"]

    def get_call_kwargs(self, call_index: int = 0):
        """Get kwargs from a specific call."""
        if call_index >= len(self.calls):
            raise IndexError(f"Call {call_index} not found")
        return self.calls[call_index]["kwargs"]


async def run_with_timeout(coro, timeout: float, default=None):
    """
    Run coroutine with timeout, returning default on timeout.

    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        default: Value to return on timeout

    Returns:
        Result of coro or default on timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return default


async def gather_with_timeout(
    *coros,
    timeout: float = 5.0,
    return_exceptions: bool = False
):
    """
    Gather multiple coroutines with overall timeout.

    Args:
        *coros: Coroutines to gather
        timeout: Overall timeout in seconds
        return_exceptions: Whether to return exceptions instead of raising

    Returns:
        List of results

    Raises:
        asyncio.TimeoutError: If timeout exceeded
    """
    return await asyncio.wait_for(
        asyncio.gather(*coros, return_exceptions=return_exceptions),
        timeout=timeout
    )
