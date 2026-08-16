"""Read-only hardware and replay verification reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from morningstar_modbus.catalog import get_profile
from morningstar_modbus.catalog.compatibility import effective_items
from morningstar_modbus.catalog.types import RegisterBlock
from morningstar_modbus.domain.models import DeviceIdentification, Endpoint, RegisterValue
from morningstar_modbus.intelligence import refresh_intelligence, resolve_device_intelligence
from morningstar_modbus.transports.modbus import ReadOnlyModbusClient


@dataclass(frozen=True, slots=True)
class VerificationReport:
    profile: str
    family: str
    model: str
    firmware: str
    hardware_revision: str
    transport: str
    unit_id: int
    intelligence_status: str
    confidence: float
    runtime_blocks_readable: int
    runtime_blocks_total: int
    metadata_blocks_readable: int
    metadata_blocks_total: int
    named_registers_decoded: int
    named_registers_total: int
    optional_blocks_readable: int
    optional_blocks_total: int
    result: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def render_text(self) -> str:
        return "\n".join(
            (
                "Morningstar Hardware Verification",
                "=================================",
                f"Model                 {self.model or '<unknown>'}",
                f"Firmware              {self.firmware or '<unknown>'}",
                f"Transport             {self.transport}",
                f"Unit ID               {self.unit_id}",
                "",
                f"Profile               {self.profile}",
                f"Identification        {self.intelligence_status.upper()}",
                f"Confidence            {self.confidence:.2f}",
                "",
                "Register blocks",
                "------------------------------",
                (
                    f"Runtime blocks        {self.runtime_blocks_readable}/"
                    f"{self.runtime_blocks_total} readable"
                ),
                (
                    f"Metadata blocks       {self.metadata_blocks_readable}/"
                    f"{self.metadata_blocks_total} readable"
                ),
                (
                    f"Named registers       {self.named_registers_decoded}/"
                    f"{self.named_registers_total} decoded"
                ),
                (
                    f"Optional blocks       {self.optional_blocks_readable}/"
                    f"{self.optional_blocks_total} available"
                ),
                "",
                f"RESULT: {self.result.upper()}",
            )
        )


def _block_available(block: RegisterBlock, values: tuple[RegisterValue, ...]) -> bool:
    raw_keys = {
        (value.function, value.address)
        for value in values
        if value.name.startswith(("holding_0x", "input_0x"))
    }
    return all(
        (block.function, address) in raw_keys
        for address in range(block.address, block.address + block.count)
    )


async def verify_device(
    client: ReadOnlyModbusClient,
    endpoint: Endpoint,
) -> tuple[VerificationReport, DeviceIdentification, tuple[RegisterValue, ...]]:
    try:
        identification = await client.read_device_identification()
    except Exception:
        identification = DeviceIdentification()
    intelligence = await resolve_device_intelligence(client, identification, endpoint=endpoint)
    profile = get_profile(intelligence.profile)
    values = await profile.poll(client, firmware=intelligence.firmware)
    intelligence = refresh_intelligence(intelligence, values, endpoint=endpoint)

    blocks = effective_items(profile.spec.blocks, intelligence.firmware)
    runtime = tuple(block for block in blocks if block.category != "metadata")
    metadata = tuple(block for block in blocks if block.category == "metadata")
    optional = tuple(block for block in blocks if block.optional)
    registers = effective_items(profile.spec.registers, intelligence.firmware)
    named = {
        value.name
        for value in values
        if not value.name.startswith(("holding_0x", "input_0x"))
    }
    required_ok = all(_block_available(block, values) for block in blocks if not block.optional)
    result = (
        "verified"
        if required_ok and intelligence.status not in {"generic", "invalid"}
        else "failed"
    )
    report = VerificationReport(
        profile=profile.name,
        family=profile.spec.family,
        model=intelligence.model,
        firmware=intelligence.firmware,
        hardware_revision=intelligence.hardware_revision,
        transport=endpoint.transport,
        unit_id=endpoint.unit_id,
        intelligence_status=intelligence.status,
        confidence=intelligence.confidence,
        runtime_blocks_readable=sum(_block_available(block, values) for block in runtime),
        runtime_blocks_total=len(runtime),
        metadata_blocks_readable=sum(_block_available(block, values) for block in metadata),
        metadata_blocks_total=len(metadata),
        named_registers_decoded=sum(register.name in named for register in registers),
        named_registers_total=len(registers),
        optional_blocks_readable=sum(_block_available(block, values) for block in optional),
        optional_blocks_total=len(optional),
        result=result,
        warnings=tuple(issue.message for issue in intelligence.warnings),
    )
    return report, identification, values
