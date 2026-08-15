"""Independent verification evidence for catalog profiles.

This registry deliberately lives outside vendor-derived family modules so fixture/hardware
verification can evolve without pretending those changes came from a vendor register map.
"""

from __future__ import annotations

from morningstar_modbus.catalog.types import VerificationSpec

_DEFAULT = VerificationSpec()

PROFILE_VERIFICATION: dict[str, VerificationSpec] = {
    "tristar_mppt": VerificationSpec(
        document="verified",
        software="verified",
        fixture="synthetic",
        hardware="pending",
        models=("TS-MPPT-45", "TS-MPPT-60"),
        fixture_paths=(
            "tests/fixtures/morningstar/tristar_mppt/TS-MPPT-60/synthetic-fw-29",
        ),
        notes=(
            "Replay coverage is synthetic/spec-derived until a sanitized capture from known "
            "physical hardware is reviewed and committed."
        ),
    ),
}


def verification_for(profile_name: str) -> VerificationSpec:
    return PROFILE_VERIFICATION.get(profile_name, _DEFAULT)
