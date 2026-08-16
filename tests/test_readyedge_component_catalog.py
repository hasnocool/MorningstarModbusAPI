from morningstar_modbus.catalog import get_profile


def test_readyedge_catalog_exposes_all_connected_product_descriptors() -> None:
    spec = get_profile("readyedge").spec
    registers = {register.name: register for register in spec.registers}

    assert registers["connected_product_0_type"].address == 0x1F53
    assert registers["connected_product_0_serial"].address == 0x1F54
    assert registers["connected_product_0_serial"].words == 4
    assert registers["connected_product_0_serial"].decoder == "ascii_hi_lo"
    assert registers["connected_product_0_bus_and_address"].address == 0x1F58

    assert registers["connected_product_15_type"].address == 0x2043
    assert registers["connected_product_15_serial"].address == 0x2044
    assert registers["connected_product_15_bus_and_address"].address == 0x2048

    type_enum = dict(registers["connected_product_0_type"].enum)
    assert type_enum[0x0104] == "TriStar-MPPT"
    assert type_enum[0x0109] == "TriStar-MPPT-600V"
    assert type_enum[0xFFFF] == "none"

    blocks = {(block.address, block.count): block for block in spec.blocks}
    assert blocks[(0x1F53, 0x0076)].optional is True
    assert blocks[(0x1FD3, 0x0076)].optional is True
    assert "connected_product_inventory" in spec.capabilities


def test_readyedge_connected_product_expansion_words_remain_reserved() -> None:
    spec = get_profile("readyedge").spec
    ranges = {(item.address, item.count) for item in spec.reserved_ranges}
    assert (0x1F59, 10) in ranges
    assert (0x2049, 10) in ranges
