"""Shared-store writer lease acquisition helpers for FleetQoX gateways."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from .quic_gateway_state import (
    FleetQoxGatewayState,
    FramePersistenceError,
    FramePersistenceUnavailableError,
)


async def acquire_gateway_state_with_lease_wait(
    *,
    factory: Callable[[], FleetQoxGatewayState],
    wait_timeout_ms: int,
    retry_ms: int,
    on_wait: Callable[[], None] | None = None,
) -> tuple[FleetQoxGatewayState, dict[str, int | bool]]:
    """Create a writer state, waiting only while another valid holder owns it."""

    if wait_timeout_ms < 0 or retry_ms <= 0:
        raise ValueError("writer lease wait configuration is invalid")
    loop = asyncio.get_running_loop()
    started = loop.time()
    timeout_seconds = wait_timeout_ms / 1000.0
    deadline = started + timeout_seconds
    attempts = 0
    unavailable_retries = 0
    waiting_reported = False
    while True:
        attempts += 1
        try:
            state = factory()
        except FramePersistenceError as exc:
            unavailable = isinstance(exc, FramePersistenceUnavailableError)
            retryable = (
                "durable writer lease is held by" in str(exc) or unavailable
            )
            remaining = deadline - loop.time()
            if not retryable or timeout_seconds <= 0.0 or remaining <= 0.0:
                if retryable and timeout_seconds > 0.0 and remaining <= 0.0:
                    raise FramePersistenceError(
                        "timed out waiting for durable writer lease or state availability"
                    ) from exc
                raise
            if unavailable:
                unavailable_retries += 1
            if not waiting_reported:
                if on_wait is not None:
                    on_wait()
                waiting_reported = True
            await asyncio.sleep(min(retry_ms / 1000.0, remaining))
            continue
        waited_ms = max(0, round((loop.time() - started) * 1000.0))
        return state, {
            "automatic_standby_wait_configured": timeout_seconds > 0.0,
            "writer_lease_acquisition_attempts": attempts,
            "writer_lease_acquisition_wait_ms": waited_ms,
            "writer_lease_unavailable_retries": unavailable_retries,
        }
