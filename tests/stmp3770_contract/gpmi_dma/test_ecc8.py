import pytest

from framework.constants import BCH_BASE, DIGCTL_BASE, GPMI_BASE, ICOLL_BASE, SRAM_BASE


@pytest.mark.asyncio
async def test_ecc8_completion_result_contract(machine):
    """ECC8 completion result contract"""
    payload = SRAM_BASE + 0x1000
    auxiliary = SRAM_BASE + 0x2000

    await machine.writel(BCH_BASE + 0x000, 0)
    await machine.writel(GPMI_BASE + 0x000, 0)

    await machine.writel(payload, 0x11111111)
    await machine.writel(payload + 0x200, 0x22222222)
    await machine.writel(auxiliary, 0x33333333)
    await machine.writel(GPMI_BASE + 0x040, payload)
    await machine.writel(GPMI_BASE + 0x050, auxiliary)
    await machine.writel(GPMI_BASE + 0x020, 0x00001002)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | 1)

    payload0 = await machine.readl(payload)
    assert payload0 == 0x11111111, (
        f"ECC8 must not write unselected payload buffer 0: got 0x{payload0:x}"
    )
    payload1 = await machine.readl(payload + 0x200)
    assert payload1 == 0xFFFFFFFF, (
        f"ECC8 must transfer the selected payload buffer 1: got 0x{payload1:x}"
    )
    auxiliary0 = await machine.readl(auxiliary)
    assert auxiliary0 == 0x33333333, (
        f"ECC8 must not write the auxiliary buffer unless BUFFER_MASK.AUXILIARY is set: got 0x{auxiliary0:x}"
    )
    await machine.writel(BCH_BASE + 0x008, 1)

    await machine.writel(GPMI_BASE + 0x020, 0x1234110F)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | (2 << 20) | 1)
    first_status0 = await machine.readl(BCH_BASE + 0x010)
    assert (first_status0 >> 16) == 0x1234, (
        f"ECC8 STATUS0 must retain the GPMI ECC handle: got 0x{first_status0:x}"
    )
    assert (first_status0 & 0x3) == 2, (
        f"ECC8 STATUS0 must report the completing chip select: got 0x{first_status0:x}"
    )
    assert ((first_status0 >> 8) & 0xF) == 0, (
        f"ECC8 STATUS0 must report a checked auxiliary block: got 0x{first_status0:x}"
    )
    status1 = await machine.readl(BCH_BASE + 0x020)
    assert status1 == 0xCCCC0000, (
        f"ECC8 STATUS1 must mark unrequested payload blocks as not checked: got 0x{status1:x}"
    )

    await machine.writel(GPMI_BASE + 0x020, 0xBEEF110F)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | (1 << 20) | 1)
    status0 = await machine.readl(BCH_BASE + 0x010)
    assert status0 == first_status0, (
        f"ECC8 must retain unread completion results until COMPLETE_IRQ is cleared: got 0x{status0:x}"
    )

    await machine.writel(BCH_BASE + 0x008, 1)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | (1 << 20) | 1)
    second_status0 = await machine.readl(BCH_BASE + 0x010)
    assert (second_status0 >> 16) == 0xBEEF, (
        f"ECC8 must accept a new result after COMPLETE_IRQ is cleared: got 0x{second_status0:x}"
    )
    assert (second_status0 & 0x3) == 1, (
        f"ECC8 must report the new completing chip select: got 0x{second_status0:x}"
    )


@pytest.mark.asyncio
async def test_ecc8_register_contract(machine):
    """ECC8 register contract"""
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert ctrl == 0xE0000000, (
        f"ECC8 CTRL must reset with SFTRST, CLKGATE, and AHBM_SFTRST asserted: got 0x{ctrl:x}"
    )
    status0 = await machine.readl(BCH_BASE + 0x010)
    assert status0 == 0x0000FC10, (
        f"ECC8 STATUS0 must reset with all four capabilities, NOT_CHECKED auxiliary status, and ALLONES: got 0x{status0:x}"
    )
    status1 = await machine.readl(BCH_BASE + 0x020)
    assert status1 == 0xCCCCCCCC, (
        f"ECC8 STATUS1 must reset with every payload marked NOT_CHECKED: got 0x{status1:x}"
    )
    blockname = await machine.readl(BCH_BASE + 0x080)
    assert blockname == 0x38434345, (
        f"ECC8 BLOCKNAME must expose the fixed ASCII ECC8 identifier: got 0x{blockname:x}"
    )
    version = await machine.readl(BCH_BASE + 0x0A0)
    assert version == 0x01000000, (
        f"ECC8 VERSION must expose the documented v1.0 value: got 0x{version:x}"
    )
    for offset in [0x040, 0x050, 0x060, 0x070]:
        debug = await machine.readl(BCH_BASE + offset)
        assert debug == 0, (
            f"ECC8 debug read register 0x{offset:x} must reset to zero: got 0x{debug:x}"
        )

    await machine.writel(GPMI_BASE + 0x000, 0)
    await machine.writel(GPMI_BASE + 0x020, 0x0000110F)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | 1)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & 1) == 0, (
        f"ECC8 must not complete while SFTRST is asserted: ctrl=0x{ctrl:x}"
    )

    await machine.writel(BCH_BASE + 0x008, 0x80000000)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | 1)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & 1) == 0, (
        f"ECC8 must not complete while CLKGATE or AHBM_SFTRST is asserted: ctrl=0x{ctrl:x}"
    )

    await machine.writel(BCH_BASE + 0x008, (1 << 30) | (1 << 29))
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | 1)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & 1) != 0, (
        f"ECC8 must complete after SFTRST, CLKGATE, and AHBM_SFTRST are all clear: ctrl=0x{ctrl:x}"
    )
    await machine.writel(BCH_BASE + 0x008, 1)

    await machine.writel(BCH_BASE + 0x000, 0xFFFFFFFF)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert ctrl == 0xEF000700, (
        f"ECC8 CTRL base write must retain documented configuration fields but not manufacture IRQ status: got 0x{ctrl:x}"
    )

    await machine.writel(BCH_BASE + 0x008, 0x80000000)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & (1 << 30)) == (1 << 30), (
        f"ECC8 CLKGATE must remain asserted until explicitly cleared after SFTRST release: ctrl=0x{ctrl:x}"
    )
    await machine.writel(BCH_BASE + 0x008, 0xE0000000)

    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 24) | 1)
    completed_status = await machine.readl(BCH_BASE + 0x010)
    assert completed_status != 0x00001C01, (
        f"ECC8 completion must update STATUS0: got 0x{completed_status:x}"
    )
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & 1) != 0, (
        f"ECC8 completion must set COMPLETE_IRQ: ctrl=0x{ctrl:x}"
    )

    await machine.writel(BCH_BASE + 0x010, 0xFFFFFFFF)
    status0 = await machine.readl(BCH_BASE + 0x010)
    assert status0 == completed_status, (
        f"ECC8 STATUS0 must be read-only: got 0x{status0:x}"
    )
    await machine.writel(BCH_BASE + 0x014, 0xFFFFFFFF)
    status0 = await machine.readl(BCH_BASE + 0x010)
    assert status0 == completed_status, (
        f"ECC8 STATUS0 must reject undocumented aliases: got 0x{status0:x}"
    )

    await machine.writel(BCH_BASE + 0x000, 1)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & 1) != 0, (
        f"ECC8 base CTRL write must not clear COMPLETE_IRQ: ctrl=0x{ctrl:x}"
    )
    await machine.writel(BCH_BASE + 0x008, 1)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & 1) == 0, (
        f"ECC8 CTRL_CLR must clear COMPLETE_IRQ: ctrl=0x{ctrl:x}"
    )

    await machine.writel(BCH_BASE + 0x030, 0x01FFFF3F)
    await machine.writel(BCH_BASE + 0x004, 0x80000000)
    status0 = await machine.readl(BCH_BASE + 0x010)
    assert status0 == 0x0000FC10, (
        f"ECC8 SFTRST must restore STATUS0 defaults: got 0x{status0:x}"
    )
    status1 = await machine.readl(BCH_BASE + 0x020)
    assert status1 == 0xCCCCCCCC, (
        f"ECC8 SFTRST must restore STATUS1 defaults: got 0x{status1:x}"
    )
    debug0 = await machine.readl(BCH_BASE + 0x030)
    assert debug0 == 0, (
        f"ECC8 SFTRST must reset DEBUG0: got 0x{debug0:x}"
    )

    for offset in [0x080, 0x084, 0x088, 0x08C, 0x0A0, 0x0A4, 0x0A8, 0x0AC]:
        await machine.writel(BCH_BASE + offset, 0xFFFFFFFF)
    blockname = await machine.readl(BCH_BASE + 0x080)
    assert blockname == 0x38434345, (
        f"ECC8 BLOCKNAME must remain read-only: got 0x{blockname:x}"
    )
    version = await machine.readl(BCH_BASE + 0x0A0)
    assert version == 0x01000000, (
        f"ECC8 VERSION must remain read-only: got 0x{version:x}"
    )


@pytest.mark.asyncio
async def test_ecc8_ahb_bus_error_contract(machine):
    """ECC8 AHB bus error contract"""
    run_bit = 1 << 29
    command_read = 1 << 24
    word_length_8bit = 1 << 23
    address_data = 0 << 17
    enable_ecc = 1 << 12

    await machine.writel(BCH_BASE + 0x008, 0xE0000000)
    await machine.writel(GPMI_BASE + 0x000, 0)

    await machine.writel(GPMI_BASE + 0x040, 0xDEAD0000)
    await machine.writel(GPMI_BASE + 0x020, enable_ecc | 1)

    read_ctrl0 = run_bit | command_read | word_length_8bit | address_data | 1
    await machine.writel(GPMI_BASE + 0x000, read_ctrl0)

    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & (1 << 3)) != 0, (
        f"ECC8 must set BM_ERROR_IRQ when the AHB master cannot write the payload buffer: ctrl=0x{ctrl:x}"
    )
    assert (ctrl & 1) != 0, (
        f"ECC8 must still set COMPLETE_IRQ after an AHB bus error: ctrl=0x{ctrl:x}"
    )
    raw = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw & (1 << 21)) != 0, (
        f"ECC8 AHB bus error must assert the ECC8 ICOLL source (raw bit 21): raw=0x{raw:x}"
    )

    await machine.writel(BCH_BASE + 0x008, 1 << 3)
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & (1 << 3)) == 0, (
        f"ECC8 BM_ERROR_IRQ must clear with CTRL_CLR: ctrl=0x{ctrl:x}"
    )


@pytest.mark.asyncio
async def test_ecc8_debug_trigger_contract(machine):
    """ECC8 debug trigger contract"""
    run_bit = 1 << 29
    command_read = 1 << 24
    word_length_8bit = 1 << 23
    address_data = 0 << 17
    enable_ecc = 1 << 12
    payload = SRAM_BASE + 0x18000
    auxiliary = SRAM_BASE + 0x20000

    await machine.writel(BCH_BASE + 0x008, 0xE0000000)
    await machine.writel(GPMI_BASE + 0x000, 0)

    debug_enable = (1 << 10) | (1 << 9)
    await machine.writel(BCH_BASE + 0x000, debug_enable)
    await machine.writel(GPMI_BASE + 0x040, payload)
    await machine.writel(GPMI_BASE + 0x050, auxiliary)
    await machine.writel(GPMI_BASE + 0x020, enable_ecc | 0x10F)

    read_ctrl0 = run_bit | command_read | word_length_8bit | address_data | 1
    await machine.writel(GPMI_BASE + 0x000, read_ctrl0)

    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & (1 << 1)) != 0, (
        f"ECC8 must set DEBUG_WRITE_IRQ when DEBUG_WRITE_IRQ_EN is set for each transfer: ctrl=0x{ctrl:x}"
    )
    assert (ctrl & (1 << 2)) != 0, (
        f"ECC8 must set DEBUG_STALL_IRQ when DEBUG_STALL_IRQ_EN is set per block: ctrl=0x{ctrl:x}"
    )
    raw = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw & (1 << 21)) != 0, (
        f"ECC8 debug trigger must assert the ECC8 ICOLL source (raw bit 21): raw=0x{raw:x}"
    )

    await machine.writel(BCH_BASE + 0x008, (1 << 2) | (1 << 1))
    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & ((1 << 2) | (1 << 1))) == 0, (
        f"ECC8 DEBUG_STALL_IRQ and DEBUG_WRITE_IRQ must clear with CTRL_CLR: ctrl=0x{ctrl:x}"
    )
    raw = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw & (1 << 21)) == 0, (
        f"ECC8 debug trigger IRQ must de-assert after status is cleared: raw=0x{raw:x}"
    )


@pytest.mark.asyncio
async def test_ecc8_throttle_contract(machine):
    """ECC8 THROTTLE contract"""
    run_bit = 1 << 29
    command_read = 1 << 24
    word_length_8bit = 1 << 23
    address_data = 0 << 17
    enable_ecc = 1 << 12
    throttle = 1
    payload = SRAM_BASE + 0x18000
    auxiliary = SRAM_BASE + 0x20000

    await machine.writel(GPMI_BASE + 0x000, 0)
    await machine.writel(BCH_BASE + 0x000, throttle << 24)

    hclk_before = await machine.readl(DIGCTL_BASE + 0x020)

    await machine.writel(GPMI_BASE + 0x040, payload)
    await machine.writel(GPMI_BASE + 0x050, auxiliary)
    await machine.writel(GPMI_BASE + 0x020, enable_ecc | 0x10F)

    read_ctrl0 = run_bit | command_read | word_length_8bit | address_data | 1
    await machine.writel(GPMI_BASE + 0x000, read_ctrl0)

    hclk_after = await machine.readl(DIGCTL_BASE + 0x020)
    expected = 5 * throttle
    actual = hclk_after - hclk_before
    assert actual == expected, (
        f"ECC8 THROTTLE={throttle} should advance HCLKCOUNT by exactly {expected} cycles (got {actual})"
    )

    ctrl = await machine.readl(BCH_BASE + 0x000)
    assert (ctrl & 1) != 0, (
        f"ECC8 must complete after THROTTLE delays: ctrl=0x{ctrl:x}"
    )
