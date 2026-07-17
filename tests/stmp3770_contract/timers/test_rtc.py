import pytest

from framework.constants import CLKCTRL_BASE, ICOLL_BASE, RTC_BASE


@pytest.mark.asyncio
async def test_rtc_1ms_irq_routing(machine):
    """RTC 1ms IRQ routing"""
    await machine.writel(RTC_BASE + 0x008, 0xC000002D)
    await machine.writel(RTC_BASE + 0x004, 0x00000002)
    await machine.clock_step(1_000_000)

    ctrl = await machine.readl(RTC_BASE + 0x000)
    raw0 = await machine.readl(ICOLL_BASE + 0x040)
    raw1 = await machine.readl(ICOLL_BASE + 0x050)

    assert ctrl & (1 << 3), f"RTC 1ms status bit missing: ctrl=0x{ctrl:x}"
    assert raw0 & (1 << 22) == 0, (
        f"RTC alarm line asserted unexpectedly: raw0=0x{raw0:x}"
    )
    assert raw1 & (1 << 16), (
        f"RTC 1ms line not asserted on ICOLL source 48: raw1=0x{raw1:x}"
    )


@pytest.mark.asyncio
async def test_rtc_reset_and_persistent0_contract(machine):
    """RTC reset and persistent0 contract"""
    assert await machine.readl(RTC_BASE + 0x010) == 0xE0FF0000, (
        "RTC STAT reset must expose presence flags and all eight stale shadow registers"
    )

    await machine.writel(RTC_BASE + 0x064, 0x80030000)
    assert await machine.readl(RTC_BASE + 0x060) == 0x80030100, (
        "RTC PERSISTENT0 SET must retain SPARE_ANALOG, AUTO_RESTART, and DISABLE_PSWITCH"
    )


@pytest.mark.asyncio
async def test_rtc_copy_controller_contract(machine):
    """RTC copy controller contract"""
    assert (((await machine.readl(RTC_BASE + 0x010)) >> 16) & 0xFF) == 0xFF, (
        "RTC copy controller must report all shadow registers stale after reset"
    )
    await machine.clock_step(3_000_000)
    assert (((await machine.readl(RTC_BASE + 0x010)) >> 16) & 0xFF) == 0, (
        "RTC copy controller must complete reset shadow refresh in approximately 3 ms"
    )

    await machine.writel(RTC_BASE + 0x070, 0x12345678)
    assert (((await machine.readl(RTC_BASE + 0x010)) >> 8) & 0x02) != 0, (
        "RTC PERSISTENT1 write must mark its shadow value newer than analog storage"
    )
    await machine.clock_step(3_000_000)
    assert (((await machine.readl(RTC_BASE + 0x010)) >> 8) & 0x02) == 0, (
        "RTC copy controller must clear PERSISTENT1 NEW_REGS after write-back"
    )

    await machine.writel(RTC_BASE + 0x004, 0x00000020)
    ctrl_after_force_update = await machine.readl(RTC_BASE + 0x000)
    assert (ctrl_after_force_update & 0x20) == 0, (
        "RTC FORCE_UPDATE must self-clear after the copy request is accepted"
    )
    assert (((await machine.readl(RTC_BASE + 0x010)) >> 16) & 0xFF) == 0xFF, (
        "RTC FORCE_UPDATE must mark every shadow register stale"
    )
    await machine.clock_step(3_000_000)
    assert (((await machine.readl(RTC_BASE + 0x010)) >> 16) & 0xFF) == 0, (
        "RTC FORCE_UPDATE refresh must complete through the copy controller"
    )


@pytest.mark.asyncio
async def test_rtc_clock_gate_contract(machine):
    """RTC clock gate contract"""
    await machine.writel(RTC_BASE + 0x004, 0xC0000000)
    assert ((await machine.readl(RTC_BASE + 0x000)) & 0xC0000000) == 0xC0000000, (
        "RTC CTRL_SET must assert both SFTRST and CLKGATE"
    )

    await machine.writel(RTC_BASE + 0x008, 0x80000000)
    assert ((await machine.readl(RTC_BASE + 0x000)) & 0xC0000000) == 0x40000000, (
        "RTC CTRL_CLR.SFTRST must not clear the independently controlled CLKGATE bit"
    )

    await machine.writel(RTC_BASE + 0x008, 0x40000000)
    assert ((await machine.readl(RTC_BASE + 0x000)) & 0xC0000000) == 0, (
        "RTC CTRL_CLR.CLKGATE must independently enable the digital clock"
    )


@pytest.mark.asyncio
async def test_rtc_watchdog_debug_contract(machine):
    """RTC watchdog debug contract"""
    await machine.writel(RTC_BASE + 0x008, 0xC0000000)
    await machine.writel(RTC_BASE + 0x0C4, 0x00000003)
    assert await machine.readl(RTC_BASE + 0x0C0) == 0x00000002, (
        "RTC DEBUG must allow only WATCHDOG_RESET_MASK to be written"
    )

    await machine.writel(RTC_BASE + 0x050, 1)
    await machine.writel(RTC_BASE + 0x004, 0x00000010)
    await machine.clock_step(1_000_000)
    assert await machine.readl(RTC_BASE + 0x0C0) == 0x00000003, (
        "RTC watchdog mask must retain the SoC and expose asserted watchdog reset state"
    )


@pytest.mark.asyncio
async def test_rtc_alarm_wake_contract(machine):
    """RTC alarm wake contract"""
    await machine.writel(RTC_BASE + 0x008, 0xC0000000)
    await machine.clock_step(3_000_000)
    await machine.writel(RTC_BASE + 0x040, 1)
    await machine.writel(RTC_BASE + 0x064, 0x00000004)
    await machine.writel(RTC_BASE + 0x030, 1)

    assert ((await machine.readl(RTC_BASE + 0x060)) & 0x80) == 0, (
        "RTC ALARM_WAKE must remain clear when an alarm occurs while the chip is powered up"
    )


@pytest.mark.asyncio
async def test_rtc_suppress_copy_to_analog_contract(machine):
    """RTC suppress copy-to-analog contract"""
    await machine.writel(RTC_BASE + 0x008, 0xC0000000)
    await machine.clock_step(3_000_000)
    await machine.writel(RTC_BASE + 0x004, 0x00000040)
    await machine.writel(RTC_BASE + 0x070, 0x12345678)
    await machine.clock_step(3_000_000)

    assert (((await machine.readl(RTC_BASE + 0x010)) >> 8) & 0x02) != 0, (
        "RTC SUPPRESS_COPY2ANALOG must retain PERSISTENT1 NEW_REGS while automatic copy is disabled"
    )


@pytest.mark.asyncio
async def test_rtc_analog_state_survives_chip_reset(machine):
    """RTC analog state survives chip reset"""
    await machine.clock_step(3_000_000)
    await machine.writel(RTC_BASE + 0x030, 0x12345678)
    await machine.writel(RTC_BASE + 0x040, 0x87654321)
    await machine.writel(RTC_BASE + 0x070, 0x0000000F)
    await machine.writel(RTC_BASE + 0x064, 0x00000008)
    await machine.clock_step(3_000_000)

    await machine.writel(CLKCTRL_BASE + 0x0F0, 0x00000002)
    await machine.writel(RTC_BASE + 0x030, 0xFFFFFFFF)
    assert await machine.readl(RTC_BASE + 0x030) == 0, (
        "RTC LCK_SECS analog state must reject seconds writes before reset shadow refresh completes"
    )
    await machine.clock_step(3_000_000)

    assert await machine.readl(RTC_BASE + 0x030) == 0x12345678, (
        "RTC SECONDS analog state must survive CLKCTRL RESET.CHIP and refresh the shadow register"
    )
    assert await machine.readl(RTC_BASE + 0x040) == 0x87654321, (
        "RTC ALARM analog state must survive CLKCTRL RESET.CHIP and refresh the shadow register"
    )
    assert await machine.readl(RTC_BASE + 0x060) == 0x00000108, (
        "RTC PERSISTENT0 analog state, including LCK_SECS, must survive CLKCTRL RESET.CHIP"
    )
    assert await machine.readl(RTC_BASE + 0x070) == 0x0000000F, (
        "RTC PERSISTENT1 analog state must survive CLKCTRL RESET.CHIP and refresh the shadow register"
    )


@pytest.mark.asyncio
async def test_rtc_persistent1_write_mask_contract(machine):
    """RTC PERSISTENT1 write mask contract"""
    await machine.clock_step(3_000_000)
    await machine.writel(RTC_BASE + 0x070, 0xFFFFFFFF)
    assert await machine.readl(RTC_BASE + 0x070) == 0x0000000F, (
        "RTC PERSISTENT1 must ignore writes to reserved bits 31:4"
    )

    await machine.writel(RTC_BASE + 0x070, 0xDEADBEEF)
    assert await machine.readl(RTC_BASE + 0x070) == 0x0000000F, (
        "RTC PERSISTENT1 must only retain writable bits 3:0"
    )


@pytest.mark.asyncio
async def test_rtc_analog_seconds_run_while_digital_clock_gated(machine):
    """RTC analog seconds run while digital clock gated"""
    await machine.clock_step(3_000_000)
    await machine.writel(RTC_BASE + 0x030, 0)
    await machine.clock_step(3_000_000)

    await machine.writel(RTC_BASE + 0x004, 0x40000000)
    await machine.clock_step(1_000_000_000)
    await machine.writel(RTC_BASE + 0x008, 0x40000000)
    await machine.writel(RTC_BASE + 0x004, 0x00000020)
    await machine.clock_step(3_000_000)

    assert await machine.readl(RTC_BASE + 0x030) == 1, (
        "RTC analog seconds must continue while the digital clock is gated and refresh after it is enabled"
    )


@pytest.mark.asyncio
async def test_rtc_msec_resolution_contract(machine):
    """RTC millisecond resolution contract"""
    resolutions = [1, 2, 4, 8, 16]

    await machine.writel(RTC_BASE + 0x008, 0xC0000000)
    await machine.clock_step(3_000_000)

    for resolution in resolutions:
        await machine.writel(RTC_BASE + 0x060, resolution << 8)
        await machine.clock_step(3_000_000)
        before = await machine.readl(RTC_BASE + 0x020)

        await machine.clock_step(resolution * 8 * 1_000_000)
        assert await machine.readl(RTC_BASE + 0x020) == before + 8, (
            f"RTC MSEC_RES={resolution} must advance the counter once per {resolution} ms"
        )
