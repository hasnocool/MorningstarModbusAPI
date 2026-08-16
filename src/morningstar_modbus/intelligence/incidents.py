# src/morningstar_modbus/intelligence/incidents.py
"""Evidence-backed site baselines, anomaly detection, and persistent incident lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from morningstar_modbus.history.analytics import ControllerHistoryAnalytics
from morningstar_modbus.persistence.incidents import IncidentStore
from morningstar_modbus.systems.data import SystemDataRepository, SystemNotFoundError

LOGGER = logging.getLogger(__name__)

Severity = Literal["info", "warning", "critical"]
Confidence = Literal["low", "medium", "high"]
Category = Literal[
    "production",
    "charging",
    "battery",
    "communications",
    "data_integrity",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _register(sample: dict[str, object], *names: str) -> dict[str, object] | None:
    by_name = {
        str(item.get("register_name")): item
        for item in sample.get("values", [])
        if isinstance(item, dict)
    }
    for name in names:
        item = by_name.get(name)
        if item is not None:
            return item
    return None


def _register_number(sample: dict[str, object], *names: str) -> float | None:
    item = _register(sample, *names)
    return _numeric(item.get("value")) if item is not None else None


def _state_clear(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) == 0.0
    normalized = str(value).strip().lower()
    return normalized in {"", "0", "0.0", "[]", "{}", "none", "clear", "normal", "ok"}


@dataclass(frozen=True, slots=True)
class Evidence:
    """One source-backed observation supporting an intelligence finding."""

    code: str
    message: str
    value: object | None = None
    unit: str | None = None
    source: str = "telemetry"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Finding:
    """A detector result eligible to be reconciled into a persistent incident."""

    detector: str
    evaluation_key: str
    fingerprint: str
    category: Category
    severity: Severity
    confidence: Confidence
    title: str
    summary: str
    controller_uid: str | None = None
    observed_value: float | None = None
    expected_low: float | None = None
    expected_high: float | None = None
    unit: str | None = None
    evidence: tuple[Evidence, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload


@dataclass(frozen=True, slots=True)
class IncidentPolicy:
    """Conservative defaults for the first site-intelligence release."""

    scan_interval_seconds: float = 60.0
    sense_warning_v: float = 0.25
    sense_critical_v: float = 0.50
    minimum_efficiency_input_w: float = 100.0
    efficiency_warning: float = 0.80
    efficiency_critical: float = 0.60
    polling_min_samples: int = 20
    polling_warning_success_rate: float = 0.95
    polling_critical_success_rate: float = 0.80
    polling_warning_deadline_miss_rate: float = 0.10
    charge_cycle_absorption_entries_warning: int = 6
    charge_cycle_absorption_entries_critical: int = 10
    production_history_days: int = 8
    production_min_comparable_days: int = 3
    production_min_expected_w: float = 100.0
    production_warning_fraction: float = 0.60
    production_critical_fraction: float = 0.25
    production_baseline_window_minutes: int = 45
    coverage_warning_percent: float = 80.0


class SiteIntelligenceService:
    """Evaluate source-backed observations and reconcile persistent incident lifecycle."""

    def __init__(
        self,
        path: str,
        systems: SystemDataRepository,
        *,
        policy: IncidentPolicy | None = None,
    ) -> None:
        self.path = path
        self.systems = systems
        self.policy = policy or IncidentPolicy()
        self.store = IncidentStore(path)
        self.history = ControllerHistoryAnalytics(path)
        self._task: asyncio.Task[None] | None = None
        self._scan_lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self.store.initialize()

    async def start(self) -> None:
        """Start an optional non-blocking background evaluator."""
        await self.initialize()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(),
                name="morningstar-site-intelligence",
            )

    async def close(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _run(self) -> None:
        while True:
            try:
                await self.scan_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("site intelligence scan failed")
            await asyncio.sleep(max(5.0, self.policy.scan_interval_seconds))

    async def scan_all(self) -> None:
        for system in await self.systems.list_systems():
            system_uid = str(system.get("system_uid") or "")
            if not system_uid:
                continue
            try:
                await self.scan(system_uid)
            except SystemNotFoundError:
                continue
            except Exception:
                LOGGER.exception("site intelligence scan failed system=%s", system_uid)

    async def scan(self, system_uid: str) -> list[dict[str, object]]:
        """Evaluate one site and persist open/update/resolve transitions."""
        async with self._scan_lock:
            await self.initialize()
            now = _utcnow()
            controllers = await self.systems.controllers(system_uid)
            findings: list[Finding] = []
            evaluated: set[str] = set()

            snapshots = await asyncio.gather(
                *(
                    self.systems.controllers_data.latest(str(item["controller_uid"]))
                    for item in controllers
                )
            )
            for controller, sample in zip(controllers, snapshots, strict=True):
                uid = str(controller["controller_uid"])
                detected, detector_keys = await self._evaluate_controller(
                    uid,
                    controller,
                    sample,
                    now,
                )
                findings.extend(detected)
                evaluated.update(detector_keys)

            baseline_finding, baseline_evaluated = await self._evaluate_solar_baseline(
                system_uid,
                now,
            )
            if baseline_finding is not None:
                findings.append(baseline_finding)
            evaluated.update(baseline_evaluated)

            transitions = await self.store.reconcile(
                system_uid,
                (finding.to_dict() for finding in findings),
                evaluated_keys=evaluated,
                observed_at=now.isoformat(),
            )
            await self._record_transitions(transitions)
            return await self.store.list(system_uid=system_uid, limit=500)

    async def _evaluate_solar_baseline(
        self,
        system_uid: str,
        now: datetime,
    ) -> tuple[Finding | None, set[str]]:
        baseline = await self.solar_baseline(system_uid, now=now)
        key = f"solar_underproduction|{system_uid}"
        if baseline.get("status") != "ready":
            return None, set()

        current = _numeric(baseline.get("current_value"))
        median = _numeric(baseline.get("expected_median"))
        low = _numeric(baseline.get("expected_low"))
        high = _numeric(baseline.get("expected_high"))
        evaluated = {key}
        if (
            current is None
            or median is None
            or median < self.policy.production_min_expected_w
        ):
            return None, evaluated

        trigger = min(
            median * self.policy.production_warning_fraction,
            (low or median) * 0.75,
        )
        if current >= trigger:
            return None, evaluated

        severity: Severity = (
            "critical"
            if current < median * self.policy.production_critical_fraction
            else "warning"
        )
        comparable = int(baseline.get("comparable_days") or 0)
        confidence: Confidence = "high" if comparable >= 5 else "medium"
        deviation = ((current / median) - 1.0) * 100.0
        return (
            Finding(
                detector="solar_underproduction",
                evaluation_key=key,
                fingerprint=key,
                category="production",
                severity=severity,
                confidence=confidence,
                title="Solar production below historical baseline",
                summary=(
                    f"Current site solar input is {abs(deviation):.0f}% below the "
                    "time-of-day historical median."
                ),
                observed_value=current,
                expected_low=low,
                expected_high=high,
                unit="W",
                evidence=(
                    Evidence(
                        "current_solar_input",
                        "Current normalized site solar input power.",
                        current,
                        "W",
                        "system-latest",
                    ),
                    Evidence(
                        "historical_median",
                        "Median from comparable UTC time windows on prior days.",
                        median,
                        "W",
                        "system-history",
                    ),
                    Evidence(
                        "comparable_days",
                        "Prior days contributing to the local baseline.",
                        comparable,
                        source="system-history",
                    ),
                ),
            ),
            evaluated,
        )

    async def _record_transitions(self, transitions: list[dict[str, object]]) -> None:
        for incident in transitions:
            transition = str(incident.get("transition") or "updated")
            incident_uid = str(incident.get("incident_uid") or "")
            updated_at = str(incident.get("updated_at") or "")
            controller_uid = incident.get("controller_uid")
            await self.systems.events_store.record(
                f"INCIDENT_{transition.upper()}",
                controller_uid=str(controller_uid) if controller_uid else None,
                severity=str(incident.get("severity") or "info"),
                source="site-intelligence",
                message=str(incident.get("title") or ""),
                payload={
                    "incident_uid": incident_uid,
                    "system_uid": incident.get("system_uid"),
                    "detector": incident.get("detector"),
                    "category": incident.get("category"),
                    "state": incident.get("state"),
                    "transition": transition,
                },
                observed_at=updated_at or None,
                dedupe_key=f"incident:{incident_uid}:{transition}:{updated_at}",
            )

    async def _evaluate_controller(
        self,
        uid: str,
        controller: dict[str, object],
        sample: dict[str, object] | None,
        now: datetime,
    ) -> tuple[list[Finding], set[str]]:
        findings: list[Finding] = []
        evaluated: set[str] = set()

        offline = self._offline_finding(uid, controller)
        evaluated.add(f"controller_offline|{uid}")
        if offline is not None:
            findings.append(offline)
        if sample is None:
            return findings, evaluated

        for finding, key in (
            self._sense_finding(uid, sample),
            self._efficiency_finding(uid, sample),
        ):
            if key is not None:
                evaluated.add(key)
            if finding is not None:
                findings.append(finding)

        status_findings, status_evaluated = self._status_findings(uid, sample)
        findings.extend(status_findings)
        evaluated.update(status_evaluated)

        polling_finding, polling_key = await self._polling_finding(uid)
        if polling_key is not None:
            evaluated.add(polling_key)
        if polling_finding is not None:
            findings.append(polling_finding)

        cycle_finding, cycle_key = await self._charge_cycle_finding(uid, now)
        if cycle_key is not None:
            evaluated.add(cycle_key)
        if cycle_finding is not None:
            findings.append(cycle_finding)

        coverage_finding, coverage_key = await self._coverage_finding(uid)
        if coverage_key is not None:
            evaluated.add(coverage_key)
        if coverage_finding is not None:
            findings.append(coverage_finding)

        return findings, evaluated

    def _offline_finding(
        self,
        uid: str,
        controller: dict[str, object],
    ) -> Finding | None:
        status = str(controller.get("status") or "unknown").lower()
        if status == "online":
            return None
        key = f"controller_offline|{uid}"
        return Finding(
            detector="controller_offline",
            evaluation_key=key,
            fingerprint=key,
            category="communications",
            severity="warning",
            confidence="high",
            title="Controller is offline",
            summary="The physical controller is not currently reporting as online.",
            controller_uid=uid,
            evidence=(
                Evidence(
                    "controller_status",
                    "Physical-controller inventory status.",
                    status,
                    source="controller-inventory",
                ),
            ),
        )

    def _sense_finding(
        self,
        uid: str,
        sample: dict[str, object],
    ) -> tuple[Finding | None, str | None]:
        sense = _register_number(
            sample,
            "battery_sense_voltage",
            "battery_remote_sense_voltage",
        )
        terminal = _register_number(
            sample,
            "battery_terminal_voltage",
            "battery_voltage",
        )
        if sense is None or terminal is None:
            return None, None
        key = f"battery_sense_divergence|{uid}"
        delta = abs(terminal - sense)
        if delta < self.policy.sense_warning_v:
            return None, key
        return (
            Finding(
                detector="battery_sense_divergence",
                evaluation_key=key,
                fingerprint=key,
                category="battery",
                severity=(
                    "critical"
                    if delta >= self.policy.sense_critical_v
                    else "warning"
                ),
                confidence="high",
                title="Battery terminal and sense voltage disagree",
                summary=(
                    "The controller terminal voltage and remote-sense voltage differ by "
                    f"{delta:.2f} V."
                ),
                controller_uid=uid,
                observed_value=delta,
                expected_low=0.0,
                expected_high=self.policy.sense_warning_v,
                unit="V",
                evidence=(
                    Evidence(
                        "terminal_voltage",
                        "Controller terminal voltage.",
                        terminal,
                        "V",
                    ),
                    Evidence(
                        "sense_voltage",
                        "Remote battery sense voltage.",
                        sense,
                        "V",
                    ),
                ),
            ),
            key,
        )

    def _efficiency_finding(
        self,
        uid: str,
        sample: dict[str, object],
    ) -> tuple[Finding | None, str | None]:
        input_power = _register_number(
            sample,
            "input_power",
            "array_power",
            "pv_power",
            "input_power_reported",
        )
        output_power = _register_number(
            sample,
            "output_power",
            "charge_power",
            "battery_charge_power",
        )
        if (
            input_power is None
            or output_power is None
            or input_power < self.policy.minimum_efficiency_input_w
        ):
            return None, None
        key = f"controller_efficiency|{uid}"
        efficiency = output_power / input_power if input_power > 0 else 0.0
        if efficiency >= self.policy.efficiency_warning:
            return None, key
        return (
            Finding(
                detector="controller_efficiency",
                evaluation_key=key,
                fingerprint=key,
                category="production",
                severity=(
                    "critical"
                    if efficiency < self.policy.efficiency_critical
                    else "warning"
                ),
                confidence="medium",
                title="Controller conversion efficiency is unusually low",
                summary=(
                    "Source-backed input and output power imply a conversion ratio of "
                    f"{efficiency * 100.0:.1f}%."
                ),
                controller_uid=uid,
                observed_value=efficiency * 100.0,
                expected_low=self.policy.efficiency_warning * 100.0,
                expected_high=100.0,
                unit="%",
                evidence=(
                    Evidence(
                        "input_power",
                        "Controller input power.",
                        input_power,
                        "W",
                    ),
                    Evidence(
                        "output_power",
                        "Controller charging output power.",
                        output_power,
                        "W",
                    ),
                    Evidence(
                        "interpretation_boundary",
                        "Low ratio is an observation, not a hardware-failure diagnosis.",
                        source="policy",
                    ),
                ),
            ),
            key,
        )

    def _status_findings(
        self,
        uid: str,
        sample: dict[str, object],
    ) -> tuple[list[Finding], set[str]]:
        findings: list[Finding] = []
        evaluated: set[str] = set()
        definitions = (
            (
                "controller_fault",
                ("faults", "fault_state"),
                "critical",
                "Controller fault is active",
            ),
            (
                "controller_alarm",
                ("alarms", "alarm_state"),
                "warning",
                "Controller alarm is active",
            ),
        )
        for detector, names, severity, title in definitions:
            item = _register(sample, *names)
            if item is None:
                continue
            key = f"{detector}|{uid}"
            evaluated.add(key)
            value = item.get("value")
            if _state_clear(value):
                continue
            findings.append(
                Finding(
                    detector=detector,
                    evaluation_key=key,
                    fingerprint=key,
                    category="communications",
                    severity=severity,
                    confidence="high",
                    title=title,
                    summary=(
                        "A source-backed controller status register reports a non-clear state."
                    ),
                    controller_uid=uid,
                    evidence=(
                        Evidence(
                            str(item.get("register_name") or detector),
                            "Raw controller-reported state.",
                            value,
                            source="controller-telemetry",
                        ),
                    ),
                )
            )
        return findings, evaluated

    async def _polling_finding(
        self,
        uid: str,
    ) -> tuple[Finding | None, str | None]:
        try:
            summary = await self.systems.controllers_data.polling_summary(
                uid,
                window=300,
                mode="watch",
            )
        except Exception:
            return None, None
        samples = int(summary.get("samples") or 0)
        if samples < self.policy.polling_min_samples:
            return None, None

        key = f"polling_degradation|{uid}"
        success = float(summary.get("success_rate") or 0.0)
        deadline = float(summary.get("deadline_miss_rate") or 0.0)
        degraded = (
            success < self.policy.polling_warning_success_rate
            or deadline > self.policy.polling_warning_deadline_miss_rate
        )
        if not degraded:
            return None, key
        return (
            Finding(
                detector="polling_degradation",
                evaluation_key=key,
                fingerprint=key,
                category="communications",
                severity=(
                    "critical"
                    if success < self.policy.polling_critical_success_rate
                    else "warning"
                ),
                confidence="high",
                title="Modbus polling reliability degraded",
                summary=(
                    f"Recent poll success is {success * 100.0:.1f}% with "
                    f"{deadline * 100.0:.1f}% deadline misses."
                ),
                controller_uid=uid,
                observed_value=success * 100.0,
                expected_low=self.policy.polling_warning_success_rate * 100.0,
                expected_high=100.0,
                unit="%",
                evidence=(
                    Evidence(
                        "poll_samples",
                        "Recent persisted polling-performance samples.",
                        samples,
                    ),
                    Evidence(
                        "success_rate",
                        "Successful logical polls.",
                        success * 100.0,
                        "%",
                    ),
                    Evidence(
                        "deadline_miss_rate",
                        "Poll deadline misses.",
                        deadline * 100.0,
                        "%",
                    ),
                ),
            ),
            key,
        )

    async def _charge_cycle_finding(
        self,
        uid: str,
        now: datetime,
    ) -> tuple[Finding | None, str | None]:
        cycle = await self.charge_cycle_summary(uid, now=now)
        if int(cycle.get("observed_samples") or 0) < 3:
            return None, None
        key = f"charge_stage_cycling|{uid}"
        entries = int(cycle.get("absorption_entries") or 0)
        if entries < self.policy.charge_cycle_absorption_entries_warning:
            return None, key
        return (
            Finding(
                detector="charge_stage_cycling",
                evaluation_key=key,
                fingerprint=key,
                category="charging",
                severity=(
                    "critical"
                    if entries >= self.policy.charge_cycle_absorption_entries_critical
                    else "warning"
                ),
                confidence="high",
                title="Repeated charge-stage cycling detected",
                summary=(
                    f"The controller entered Absorption {entries} times in the last 24 hours."
                ),
                controller_uid=uid,
                observed_value=float(entries),
                expected_low=0.0,
                expected_high=float(
                    self.policy.charge_cycle_absorption_entries_warning - 1
                ),
                unit="entries/24h",
                evidence=(
                    Evidence(
                        "stage_sequence",
                        "Collapsed source-backed charge-state sequence.",
                        cycle.get("stage_sequence"),
                        source="controller-history",
                    ),
                    Evidence(
                        "transition_count",
                        "Observed charge-state transitions.",
                        cycle.get("transition_count"),
                        source="controller-history",
                    ),
                ),
            ),
            key,
        )

    async def _coverage_finding(
        self,
        uid: str,
    ) -> tuple[Finding | None, str | None]:
        try:
            coverage = await self.history.coverage(uid)
        except Exception:
            return None, None
        daily = coverage.get("daily_evidence")
        period = coverage.get("period")
        if not isinstance(daily, dict) or not isinstance(period, dict):
            return None, None
        day_count = int(period.get("day_count") or 0)
        percent = _numeric(daily.get("coverage_percent"))
        if day_count < 3 or percent is None:
            return None, None

        key = f"history_coverage|{uid}"
        if percent >= self.policy.coverage_warning_percent:
            return None, key
        return (
            Finding(
                detector="history_coverage",
                evaluation_key=key,
                fingerprint=key,
                category="data_integrity",
                severity="warning",
                confidence="high",
                title="Controller history evidence has gaps",
                summary=(
                    f"Day-level live/recovered evidence covers {percent:.1f}% of the "
                    "available analysis period."
                ),
                controller_uid=uid,
                observed_value=percent,
                expected_low=self.policy.coverage_warning_percent,
                expected_high=100.0,
                unit="%",
                evidence=(
                    Evidence(
                        "covered_days",
                        "Days with local samples or complete retained evidence.",
                        daily.get("covered_days"),
                        source="history-reconciliation",
                    ),
                    Evidence(
                        "recovered_days",
                        "Days recovered from complete retained controller history.",
                        daily.get("recovered_days"),
                        source="history-reconciliation",
                    ),
                    Evidence(
                        "missing_days",
                        "Days with no defensible evidence.",
                        daily.get("missing_days"),
                        source="history-reconciliation",
                    ),
                ),
            ),
            key,
        )

    async def solar_baseline(
        self,
        system_uid: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        """Build an offline time-of-day baseline from normalized system history."""
        current_time = (now or _utcnow()).astimezone(UTC)
        latest = await self.systems.latest(system_uid)
        metrics = latest.get("metrics", {})
        metric = metrics.get("solar_input_power_w", {}) if isinstance(metrics, dict) else {}
        current = _numeric(metric.get("value")) if isinstance(metric, dict) else None

        history = await self.systems.history(
            system_uid,
            "solar_input_power_w",
            start=(current_time - timedelta(days=self.policy.production_history_days)).isoformat(),
            end=current_time.isoformat(),
            resolution="15m",
            max_points=20_000,
        )
        target_minutes = current_time.hour * 60 + current_time.minute
        by_day: dict[str, list[float]] = defaultdict(list)
        for point in history.get("points", []):
            if not isinstance(point, dict):
                continue
            timestamp = _parse_time(point.get("bucket_start") or point.get("observed_at"))
            value = _numeric(point.get("value"))
            if timestamp is None or value is None:
                continue
            if timestamp.date() == current_time.date():
                continue
            point_minutes = timestamp.hour * 60 + timestamp.minute
            if (
                abs(point_minutes - target_minutes)
                > self.policy.production_baseline_window_minutes
            ):
                continue
            by_day[timestamp.date().isoformat()].append(value)

        daily_values = [
            sum(values) / len(values)
            for values in by_day.values()
            if values
        ]
        low = _percentile(daily_values, 0.10)
        median = _percentile(daily_values, 0.50)
        high = _percentile(daily_values, 0.90)
        ready = (
            current is not None
            and median is not None
            and len(daily_values) >= self.policy.production_min_comparable_days
        )
        return {
            "system_uid": system_uid,
            "metric": "solar_input_power_w",
            "unit": "W",
            "status": "ready" if ready else "insufficient_evidence",
            "observed_at": latest.get("observed_at"),
            "current_value": current,
            "expected_low": low,
            "expected_median": median,
            "expected_high": high,
            "comparable_days": len(daily_values),
            "window_minutes": self.policy.production_baseline_window_minutes,
            "history_days": self.policy.production_history_days,
            "confidence": (
                "high"
                if len(daily_values) >= 5
                else "medium"
                if ready
                else "low"
            ),
            "provenance": "local normalized system history; no weather dependency",
        }

    async def charge_cycle_summary(
        self,
        controller_uid: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, object]:
        """Summarize source-backed charge-state transitions over the previous 24 hours."""
        current_time = (now or _utcnow()).astimezone(UTC)
        rows = await self.systems.controllers_data.register_history(
            controller_uid,
            "charge_state",
            limit=5000,
            start=(current_time - timedelta(hours=24)).isoformat(),
            end=current_time.isoformat(),
            order="asc",
        )
        sequence: list[str] = []
        durations: dict[str, float] = defaultdict(float)
        absorption_entries = 0
        float_entries = 0
        previous_state: str | None = None
        previous_at: datetime | None = None

        for row in rows:
            state = str(row.get("value") or "").strip().upper()
            timestamp = _parse_time(row.get("observed_at"))
            if not state:
                continue
            if previous_state is not None and previous_at is not None and timestamp is not None:
                delta = max(0.0, (timestamp - previous_at).total_seconds())
                if delta <= 900.0:
                    durations[previous_state] += delta
            if state != previous_state:
                sequence.append(state)
                if state == "ABSORPTION":
                    absorption_entries += 1
                elif state == "FLOAT":
                    float_entries += 1
            previous_state = state
            previous_at = timestamp

        return {
            "controller_uid": controller_uid,
            "period_hours": 24,
            "observed_samples": len(rows),
            "transition_count": max(0, len(sequence) - 1),
            "absorption_entries": absorption_entries,
            "float_entries": float_entries,
            "stage_sequence": sequence,
            "duration_seconds_by_state": dict(durations),
        }

    async def baselines(self, system_uid: str) -> dict[str, object]:
        controllers = await self.systems.controllers(system_uid)
        cycles = await asyncio.gather(
            *(
                self.charge_cycle_summary(str(item["controller_uid"]))
                for item in controllers
            )
        )
        return {
            "system_uid": system_uid,
            "solar_input_power": await self.solar_baseline(system_uid),
            "charge_cycles": list(cycles),
        }

    async def incidents(
        self,
        *,
        system_uid: str | None = None,
        controller_uid: str | None = None,
        state: str | None = None,
        severity: str | None = None,
        limit: int = 500,
        scan: bool = False,
    ) -> list[dict[str, object]]:
        if scan and system_uid is not None:
            await self.scan(system_uid)
        return await self.store.list(
            system_uid=system_uid,
            controller_uid=controller_uid,
            state=state,
            severity=severity,
            limit=limit,
        )

    async def health_score(
        self,
        system_uid: str,
        *,
        controller_uid: str | None = None,
        scan: bool = True,
    ) -> dict[str, object]:
        """Return a transparent score derived only from current active incidents."""
        if scan:
            await self.scan(system_uid)
        incidents = await self.store.list(
            system_uid=system_uid,
            controller_uid=controller_uid,
            state="active",
            limit=1000,
        )
        category_scores = {
            "production": 20,
            "charging": 20,
            "battery": 20,
            "communications": 20,
            "data_integrity": 20,
        }
        penalties: list[dict[str, object]] = []
        weights = {"info": 2, "warning": 8, "critical": 20}
        for incident in incidents:
            category = str(incident.get("category") or "data_integrity")
            severity = str(incident.get("severity") or "info")
            penalty = weights.get(severity, 2)
            if category in category_scores:
                category_scores[category] = max(
                    0,
                    category_scores[category] - penalty,
                )
            penalties.append(
                {
                    "incident_uid": incident.get("incident_uid"),
                    "category": category,
                    "severity": severity,
                    "penalty": penalty,
                    "title": incident.get("title"),
                }
            )
        score = sum(category_scores.values())
        status = "good" if score >= 85 else "warning" if score >= 60 else "critical"
        return {
            "system_uid": system_uid,
            "controller_uid": controller_uid,
            "score": score,
            "status": status,
            "components": category_scores,
            "active_incidents": len(incidents),
            "penalties": penalties,
            "semantics": (
                "transparent evidence-backed score; penalties link to active incidents"
            ),
        }
