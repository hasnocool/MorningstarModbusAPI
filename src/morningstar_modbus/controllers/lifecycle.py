"""Device lifecycle state and retry/backoff policy."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

LifecycleState = Literal[
    "discovered",
    "connecting",
    "online",
    "degraded",
    "offline",
    "rediscovering",
]


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class DeviceLifecycle:
    state: LifecycleState = "discovered"
    consecutive_failures: int = 0
    reconnect_count: int = 0
    endpoint_changes: int = 0
    last_discovered: str = ""
    last_success: str = ""
    offline_since: str = ""
    next_retry_monotonic: float = 0.0
    retry_in_seconds: float = 0.0

    def mark_discovered(self, *, endpoint_changed: bool = False) -> None:
        self.last_discovered = _utcnow()
        if endpoint_changed:
            self.endpoint_changes += 1
        if self.state in {"offline", "rediscovering"}:
            self.state = "connecting"
        elif self.state != "online":
            self.state = "discovered"
        self.next_retry_monotonic = 0.0
        self.retry_in_seconds = 0.0

    def mark_missing(self) -> None:
        if self.state != "offline":
            self.state = "rediscovering"
        if not self.offline_since:
            self.offline_since = _utcnow()

    def mark_connecting(self) -> None:
        if self.state != "online":
            self.state = "connecting"

    def mark_success(self) -> None:
        if self.state in {"offline", "rediscovering", "degraded"} or self.consecutive_failures:
            self.reconnect_count += 1
        self.state = "online"
        self.consecutive_failures = 0
        self.last_success = _utcnow()
        self.offline_since = ""
        self.next_retry_monotonic = 0.0
        self.retry_in_seconds = 0.0

    def mark_failure(
        self,
        *,
        threshold: int,
        initial_backoff: float,
        max_backoff: float,
    ) -> None:
        self.consecutive_failures += 1
        self.state = "offline" if self.consecutive_failures >= threshold else "degraded"
        if self.state == "offline" and not self.offline_since:
            self.offline_since = _utcnow()
        exponent = max(0, self.consecutive_failures - 1)
        delay = min(max_backoff, initial_backoff * (2**exponent))
        self.retry_in_seconds = delay
        self.next_retry_monotonic = time.monotonic() + delay

    def can_poll(self, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return self.state != "rediscovering" and current >= self.next_retry_monotonic

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "reconnect_count": self.reconnect_count,
            "endpoint_changes": self.endpoint_changes,
            "last_discovered": self.last_discovered,
            "last_success": self.last_success,
            "offline_since": self.offline_since,
            "retry_in_seconds": self.retry_in_seconds,
        }
