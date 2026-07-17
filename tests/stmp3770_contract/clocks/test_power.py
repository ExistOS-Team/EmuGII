from framework.constants import POWER_BASE


async def test_power_version_and_reset_contract(machine):
    """POWER version and reset contract"""
    version = await machine.readl(POWER_BASE + 0x110)
    reset_before = await machine.readl(POWER_BASE + 0x0e0)

    assert version == 0x02000000, f"POWER VERSION should report v2.0 at 0x110: got 0x{version:x}"
    assert reset_before == 0, f"POWER RESET should reset to 0: got 0x{reset_before:x}"

    await machine.writel(POWER_BASE + 0x0e0, 0x00000001)
    reset_without_unlock = await machine.readl(POWER_BASE + 0x0e0)
    assert reset_without_unlock == 0, (
        f"POWER RESET low bits must ignore writes without unlock key: got 0x{reset_without_unlock:x}"
    )

    await machine.writel(POWER_BASE + 0x0e0, 0x3e770001)
    reset_with_unlock = await machine.readl(POWER_BASE + 0x0e0)
    assert reset_with_unlock == 0x00000001, (
        f"POWER RESET should accept unlocked write to PWD bit: got 0x{reset_with_unlock:x}"
    )


async def test_power_reset_values(machine):
    """POWER reset values"""
    ctrl = await machine.readl(POWER_BASE + 0x000)
    v5ctrl = await machine.readl(POWER_BASE + 0x010)
    charge = await machine.readl(POWER_BASE + 0x030)
    vddd = await machine.readl(POWER_BASE + 0x040)
    vdda = await machine.readl(POWER_BASE + 0x050)
    vddio = await machine.readl(POWER_BASE + 0x060)
    dclimits = await machine.readl(POWER_BASE + 0x090)
    loopctrl = await machine.readl(POWER_BASE + 0x0a0)
    speed = await machine.readl(POWER_BASE + 0x0c0)
    batt = await machine.readl(POWER_BASE + 0x0d0)
    sts = await machine.readl(POWER_BASE + 0x0b0)

    # After ROM boot init, POWER CTRL.CLKGATE (bit 30) is cleared.
    assert ctrl == 0x00040024, f"POWER CTRL post-ROM-boot mismatch: got 0x{ctrl:x}"
    assert v5ctrl == 0x00000100, f"POWER 5VCTRL reset mismatch: got 0x{v5ctrl:x}"
    assert charge == 0x00010000, f"POWER CHARGE reset mismatch: got 0x{charge:x}"
    assert vddd == 0x00310710, f"POWER VDDDCTRL reset mismatch: got 0x{vddd:x}"
    assert vdda == 0x0000170a, f"POWER VDDACTRL reset mismatch: got 0x{vdda:x}"
    assert vddio == 0x0000170c, f"POWER VDDIOCTRL reset mismatch: got 0x{vddio:x}"
    assert dclimits == 0x00040c5f, f"POWER DCLIMITS reset mismatch: got 0x{dclimits:x}"
    assert loopctrl == 0x00000021, f"POWER LOOPCTRL reset mismatch: got 0x{loopctrl:x}"
    assert speed == 0x00000000, f"POWER SPEED reset mismatch: got 0x{speed:x}"
    assert batt == 0x00000020, f"POWER BATTMONITOR reset mismatch: got 0x{batt:x}"
    assert sts == 0x80000000, f"POWER STS reset mismatch: got 0x{sts:x}"
