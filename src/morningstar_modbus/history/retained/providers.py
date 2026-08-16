# src/morningstar_modbus/controller_history_providers.py
"""Pluggable retained-history providers selected by device capability."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from morningstar_modbus.config import HistoryBackfillConfig
from morningstar_modbus.domain.models import DiscoveredDevice
from morningstar_modbus.history.retained.liveview import ControllerHistoryBackfiller as LiveViewBackfiller
from morningstar_modbus.history.retained.storage import ControllerHistoryRepository
from morningstar_modbus.history.retained.types import BackfillResult


class ControllerHistoryProvider(Protocol):
    """Read-only retained-history backend contract."""

    name: str

    async def initialize(self) -> None: ...

    def supports(self, device: DiscoveredDevice) -> bool: ...

    async def sync(self, device_id: str, device: DiscoveredDevice) -> BackfillResult: ...


class LiveViewHistoryProvider:
    """Adapter around the existing TriStar MPPT LiveView daily logger."""

    name = "tristar-liveview-daily"

    def __init__(self, database_path: str, config: HistoryBackfillConfig) -> None:
        self.backend = LiveViewBackfiller(database_path, config)

    @property
    def repository(self) -> ControllerHistoryRepository:
        return self.backend.repository

    async def initialize(self) -> None:
        await self.backend.initialize()

    def supports(self, device: DiscoveredDevice) -> bool:
        return self.backend.supports(device)

    async def sync(self, device_id: str, device: DiscoveredDevice) -> BackfillResult:
        return await self.backend.sync(device_id, device)


class ControllerHistoryProviderRegistry:
    """Select one verified retained-history provider without guessing undocumented protocols.

    The registry is intentionally conservative: a backend must explicitly claim a
    device before it is used. This makes it possible to add GenStar hourly/daily/
    event-log readers or future Morningstar products without changing watcher
    scheduling or weakening the current source/provenance boundary.
    """

    def __init__(
        self,
        database_path: str,
        config: HistoryBackfillConfig,
        *,
        providers: Iterable[ControllerHistoryProvider] | None = None,
    ) -> None:
        self.providers: tuple[ControllerHistoryProvider, ...] = tuple(
            providers if providers is not None else (LiveViewHistoryProvider(database_path, config),)
        )
        self.repository = ControllerHistoryRepository(database_path)
        if len(self.providers) == 1 and isinstance(self.providers[0], LiveViewHistoryProvider):
            self.repository = self.providers[0].repository

    async def initialize(self) -> None:
        await self.repository.initialize()
        for provider in self.providers:
            await provider.initialize()

    def provider_for(self, device: DiscoveredDevice) -> ControllerHistoryProvider | None:
        return next((provider for provider in self.providers if provider.supports(device)), None)

    def supports(self, device: DiscoveredDevice) -> bool:
        return self.provider_for(device) is not None

    async def sync(self, device_id: str, device: DiscoveredDevice) -> BackfillResult:
        provider = self.provider_for(device)
        if provider is None:
            return BackfillResult(status="unsupported")
        return await provider.sync(device_id, device)

    def summary(self) -> list[dict[str, object]]:
        return [{"name": provider.name} for provider in self.providers]
