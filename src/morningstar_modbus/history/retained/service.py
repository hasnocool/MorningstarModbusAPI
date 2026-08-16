# src/morningstar_modbus/controller_history.py
"""Public controller-retained history API and provider registry."""

from morningstar_modbus.controller_history_liveview import parse_liveview_datalog
from morningstar_modbus.controller_history_providers import (
    ControllerHistoryProvider,
    ControllerHistoryProviderRegistry,
    LiveViewHistoryProvider,
)
from morningstar_modbus.controller_history_storage import ControllerHistoryRepository
from morningstar_modbus.controller_history_types import (
    BackfillResult,
    ControllerDailyRecord,
    ControllerHistoryError,
)

# Backward-compatible name used by Watcher.  It now dispatches through the
# provider registry while retaining the existing supports()/sync() contract.
ControllerHistoryBackfiller = ControllerHistoryProviderRegistry

__all__ = [
    "BackfillResult",
    "ControllerDailyRecord",
    "ControllerHistoryBackfiller",
    "ControllerHistoryError",
    "ControllerHistoryProvider",
    "ControllerHistoryProviderRegistry",
    "ControllerHistoryRepository",
    "LiveViewHistoryProvider",
    "parse_liveview_datalog",
]
