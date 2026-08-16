# src/morningstar_modbus/exceptions.py
"""Protocol and transport exceptions."""


class ModbusError(Exception):
    """Base Modbus error."""


class ModbusProtocolError(ModbusError):
    """Malformed or unexpected Modbus response."""


class ModbusDeviceError(ModbusError):
    """Modbus exception response returned by the remote unit."""

    def __init__(self, function_code: int, exception_code: int) -> None:
        self.function_code = function_code
        self.exception_code = exception_code
        super().__init__(
            f"Modbus device exception function=0x{function_code:02x} code=0x{exception_code:02x}"
        )
