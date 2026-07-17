from framework.constants import CLKCTRL_BASE, POWER_BASE
from framework.machine import with_machine


async def test_clkctrl_reset_contract(machine):
    """CLKCTRL reset contract"""
    pllctrl0 = await machine.readl(CLKCTRL_BASE + 0x000)
    pllctrl1 = await machine.readl(CLKCTRL_BASE + 0x010)
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    hbus = await machine.readl(CLKCTRL_BASE + 0x030)
    xbus = await machine.readl(CLKCTRL_BASE + 0x040)
    xtal = await machine.readl(CLKCTRL_BASE + 0x050)
    pix = await machine.readl(CLKCTRL_BASE + 0x060)
    ssp = await machine.readl(CLKCTRL_BASE + 0x070)
    gpmi = await machine.readl(CLKCTRL_BASE + 0x080)
    spdif = await machine.readl(CLKCTRL_BASE + 0x090)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
    reset = await machine.readl(CLKCTRL_BASE + 0x0f0)
    version = await machine.readl(CLKCTRL_BASE + 0x100)

    assert pllctrl0 == 0x00000000, f"CLKCTRL PLLCTRL0 reset mismatch: got 0x{pllctrl0:x}"
    assert pllctrl1 == 0x00000000, f"CLKCTRL PLLCTRL1 reset mismatch: got 0x{pllctrl1:x}"
    assert cpu == 0x00010001, f"CLKCTRL CPU reset mismatch: got 0x{cpu:x}"
    assert hbus == 0x00000001, f"CLKCTRL HBUS reset mismatch: got 0x{hbus:x}"
    assert xbus == 0x00000001, f"CLKCTRL XBUS reset mismatch: got 0x{xbus:x}"
    assert xtal == 0x70000001, f"CLKCTRL XTAL reset mismatch: got 0x{xtal:x}"
    assert pix == 0x80000001, f"CLKCTRL PIX reset mismatch: got 0x{pix:x}"
    assert ssp == 0x80000001, f"CLKCTRL SSP reset mismatch: got 0x{ssp:x}"
    assert gpmi == 0x80000001, f"CLKCTRL GPMI reset mismatch: got 0x{gpmi:x}"
    assert spdif == 0x80000000, f"CLKCTRL SPDIF reset mismatch: got 0x{spdif:x}"
    assert frac == 0x92920092, f"CLKCTRL FRAC reset mismatch: got 0x{frac:x}"
    assert clkseq == 0x000000bb, f"CLKCTRL CLKSEQ reset mismatch: got 0x{clkseq:x}"
    assert reset == 0x00000000, f"CLKCTRL RESET reset mismatch: got 0x{reset:x}"
    assert version == 0x02010000, f"CLKCTRL VERSION mismatch: got 0x{version:x}"


async def test_clkctrl_gated_divider_contract(machine):
    """CLKCTRL gated divider contract"""
    divider_regs = [
        ("PIX", CLKCTRL_BASE + 0x060),
        ("SSP", CLKCTRL_BASE + 0x070),
        ("GPMI", CLKCTRL_BASE + 0x080),
    ]

    for name, addr in divider_regs:
        reset = await machine.readl(addr)
        assert reset == 0x80000001, f"CLKCTRL {name} should reset gated with DIV=1: got 0x{reset:x}"

        await machine.writel(addr, 0x80000028)
        while_gated = await machine.readl(addr)
        assert while_gated == 0x80000001, f"CLKCTRL {name} should ignore DIV writes while CLKGATE=1: got 0x{while_gated:x}"

        await machine.writel(addr, 0x00000028)
        ungated_no_retune = await machine.readl(addr)
        assert ungated_no_retune == 0x00000001, f"CLKCTRL {name} should not retune DIV in the same write that ungates the clock: got 0x{ungated_no_retune:x}"

        await machine.writel(addr, 0x00000028)
        await machine.readl(addr)
        retuned = await machine.readl(addr)
        assert retuned == 0x00000028, f"CLKCTRL {name} should accept a new DIV only after the clock is already ungated: got 0x{retuned:x}"


async def test_clkctrl_writable_field_masks(machine):
    """CLKCTRL writable field masks"""
    await machine.writel(CLKCTRL_BASE + 0x000, 0xffffffff)
    await machine.writel(CLKCTRL_BASE + 0x020, 0xffffffff)
    await machine.writel(CLKCTRL_BASE + 0x030, 0xffffffff)
    await machine.writel(CLKCTRL_BASE + 0x040, 0xffffffff)
    await machine.writel(CLKCTRL_BASE + 0x050, 0xffffffff)
    await machine.writel(CLKCTRL_BASE + 0x090, 0xffffffff)
    await machine.writel(CLKCTRL_BASE + 0x0d0, 0xe3e3ffe3)
    await machine.writel(CLKCTRL_BASE + 0x0e0, 0xffffffff)

    pllctrl0 = await machine.readl(CLKCTRL_BASE + 0x000)
    await machine.readl(CLKCTRL_BASE + 0x020)
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    await machine.readl(CLKCTRL_BASE + 0x030)
    hbus = await machine.readl(CLKCTRL_BASE + 0x030)
    await machine.readl(CLKCTRL_BASE + 0x040)
    xbus = await machine.readl(CLKCTRL_BASE + 0x040)
    xtal = await machine.readl(CLKCTRL_BASE + 0x050)
    spdif = await machine.readl(CLKCTRL_BASE + 0x090)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)

    assert pllctrl0 == 0x33350000, f"CLKCTRL PLLCTRL0 should only expose documented writable fields: got 0x{pllctrl0:x}"
    assert cpu == 0x07ff17ff, f"CLKCTRL CPU should ignore busy/reserved bits on write: got 0x{cpu:x}"
    assert hbus == 0x07f7003f, f"CLKCTRL HBUS should ignore reserved/busy bits on write: got 0x{hbus:x}"
    assert xbus == 0x000007ff, f"CLKCTRL XBUS should only expose DIV_FRAC_EN/DIV: got 0x{xbus:x}"
    assert xtal == 0xfc000001, f"CLKCTRL XTAL should keep DIV_UART fixed at 1 and ignore reserved bits: got 0x{xtal:x}"
    assert spdif == 0x80000000, f"CLKCTRL SPDIF should only expose CLKGATE: got 0x{spdif:x}"
    assert frac == 0xe3e300e3, f"CLKCTRL FRAC should ignore software writes to STABLE/reserved bits while preserving stable toggles from divider changes: got 0x{frac:x}"
    assert clkseq == 0x000000ba, f"CLKCTRL CLKSEQ should keep BYPASS_SAIF cleared after software writes: got 0x{clkseq:x}"


async def test_clkctrl_frac_stable_contract(machine):
    """CLKCTRL FRAC stable contract"""
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 30) & 1 == 0, f"CLKCTRL FRAC IO_STABLE should reset low: got 0x{frac:x}"
    assert (frac >> 22) & 1 == 0, f"CLKCTRL FRAC PIX_STABLE should reset low: got 0x{frac:x}"
    assert (frac >> 6) & 1 == 0, f"CLKCTRL FRAC CPU_STABLE should reset low: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92920093)
    updated = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert updated & 0x3f == 0x13, f"CLKCTRL FRAC CPUFRAC should accept the new divider: got 0x{updated:x}"
    assert (updated >> 6) & 1 == 1, f"CLKCTRL FRAC CPU_STABLE should invert when CPUFRAC changes: got 0x{updated:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92930093)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 16) & 0x3f == 0x13, f"CLKCTRL FRAC PIXFRAC should accept the new divider: got 0x{frac:x}"
    assert (frac >> 22) & 1 == 1, f"CLKCTRL FRAC PIX_STABLE should invert when PIXFRAC changes: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x93930093)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 24) & 0x3f == 0x13, f"CLKCTRL FRAC IOFRAC should accept the new divider: got 0x{frac:x}"
    assert (frac >> 30) & 1 == 1, f"CLKCTRL FRAC IO_STABLE should invert when IOFRAC changes: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d8, 0x00800080)
    updated = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert updated & 0x00800080 == 0, f"CLKCTRL FRAC gate clear should ungate PIX/CPU clocks: got 0x{updated:x}"
    assert (updated >> 22) & 1 == 1, f"CLKCTRL FRAC PIX_STABLE should not invert on CLKGATE changes alone: got 0x{updated:x}"
    assert (updated >> 6) & 1 == 1, f"CLKCTRL FRAC CPU_STABLE should not invert on CLKGATE changes alone: got 0x{updated:x}"


async def test_clkctrl_pllctrl1_reserved_contract(machine):
    """CLKCTRL PLLCTRL1 reserved contract"""
    reset = await machine.readl(CLKCTRL_BASE + 0x010)
    assert reset == 0x00000000, f"CLKCTRL PLLCTRL1 should reset to 0: got 0x{reset:x}"

    await machine.writel(CLKCTRL_BASE + 0x000, 0x00010000)
    after_pll_power_on = await machine.readl(CLKCTRL_BASE + 0x010)
    assert after_pll_power_on == 0x00000000, f"CLKCTRL PLLCTRL1 LOCK/LOCK_COUNT are reserved and should stay 0 after PLL power-on: got 0x{after_pll_power_on:x}"

    await machine.writel(CLKCTRL_BASE + 0x010, 0xffffffff)
    after_write = await machine.readl(CLKCTRL_BASE + 0x010)
    assert after_write == 0x40000000, f"CLKCTRL PLLCTRL1 should only expose the documented FORCE_LOCK writable bit: got 0x{after_write:x}"


async def test_clkctrl_reset_self_clears(machine):
    """CLKCTRL reset self-clear contract"""
    await machine.writel(POWER_BASE + 0x0e0, 0x3e770001)
    power_reset_before_dig = await machine.readl(POWER_BASE + 0x0e0)
    assert power_reset_before_dig == 0x00000001, f"POWER RESET should accept the unlocked write before DIG reset: got 0x{power_reset_before_dig:x}"

    await machine.writel(CLKCTRL_BASE + 0x0f0, 0x00000001)
    reset = await machine.readl(CLKCTRL_BASE + 0x0f0)
    assert reset == 0x00000000, f"CLKCTRL RESET.DIG should self-clear after the reset cycle completes: got 0x{reset:x}"
    power_reset_after_dig = await machine.readl(POWER_BASE + 0x0e0)
    assert power_reset_after_dig == 0x00000001, f"CLKCTRL RESET.DIG should not reset the POWER module state: got 0x{power_reset_after_dig:x}"

    await machine.writel(CLKCTRL_BASE + 0x0f0, 0x00000002)
    reset = await machine.readl(CLKCTRL_BASE + 0x0f0)
    assert reset == 0x00000000, f"CLKCTRL RESET.CHIP should self-clear after the reset cycle completes: got 0x{reset:x}"


async def test_clkctrl_divider_range_contract(machine):
    """CLKCTRL divider range contract"""
    await machine.writel(CLKCTRL_BASE + 0x020, 0x00030002)
    await machine.readl(CLKCTRL_BASE + 0x020)
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    assert cpu == 0x00030002, f"CLKCTRL CPU should accept valid DIV_XTAL/DIV_CPU values: got 0x{cpu:x}"

    await machine.writel(CLKCTRL_BASE + 0x020, 0x00000002)
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    assert cpu == 0x00030002, f"CLKCTRL CPU should reject DIV_XTAL=0 and preserve the previous valid divider: got 0x{cpu:x}"

    await machine.writel(CLKCTRL_BASE + 0x020, 0x00030000)
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    assert cpu == 0x00030002, f"CLKCTRL CPU should reject DIV_CPU=0 and preserve the previous valid divider: got 0x{cpu:x}"

    await machine.writel(CLKCTRL_BASE + 0x030, 0x00000002)
    await machine.readl(CLKCTRL_BASE + 0x030)
    hbus = await machine.readl(CLKCTRL_BASE + 0x030)
    assert hbus == 0x00000002, f"CLKCTRL HBUS should accept a valid divider: got 0x{hbus:x}"

    await machine.writel(CLKCTRL_BASE + 0x030, 0x00000000)
    hbus = await machine.readl(CLKCTRL_BASE + 0x030)
    assert hbus == 0x00000002, f"CLKCTRL HBUS should reject DIV=0 and preserve the previous valid divider: got 0x{hbus:x}"

    await machine.writel(CLKCTRL_BASE + 0x040, 0x00000004)
    await machine.readl(CLKCTRL_BASE + 0x040)
    xbus = await machine.readl(CLKCTRL_BASE + 0x040)
    assert xbus == 0x00000004, f"CLKCTRL XBUS should accept a valid divider: got 0x{xbus:x}"

    await machine.writel(CLKCTRL_BASE + 0x040, 0x00000000)
    xbus = await machine.readl(CLKCTRL_BASE + 0x040)
    assert xbus == 0x00000004, f"CLKCTRL XBUS should reject DIV=0 and preserve the previous valid divider: got 0x{xbus:x}"

    await machine.writel(CLKCTRL_BASE + 0x060, 0x00000028)
    await machine.writel(CLKCTRL_BASE + 0x060, 0x00000028)
    await machine.readl(CLKCTRL_BASE + 0x060)
    pix = await machine.readl(CLKCTRL_BASE + 0x060)
    assert pix == 0x00000028, f"CLKCTRL PIX should accept a valid divider once ungated: got 0x{pix:x}"

    await machine.writel(CLKCTRL_BASE + 0x060, 0x00000000)
    pix = await machine.readl(CLKCTRL_BASE + 0x060)
    assert pix == 0x00000028, f"CLKCTRL PIX should reject DIV=0 and preserve the previous valid divider: got 0x{pix:x}"

    await machine.writel(CLKCTRL_BASE + 0x060, 0x00000123)
    pix = await machine.readl(CLKCTRL_BASE + 0x060)
    assert pix == 0x00000028, f"CLKCTRL PIX should reject DIV values above 255: got 0x{pix:x}"

    await machine.writel(CLKCTRL_BASE + 0x070, 0x00000028)
    await machine.writel(CLKCTRL_BASE + 0x070, 0x00000028)
    await machine.readl(CLKCTRL_BASE + 0x070)
    ssp = await machine.readl(CLKCTRL_BASE + 0x070)
    assert ssp == 0x00000028, f"CLKCTRL SSP should accept a valid divider once ungated: got 0x{ssp:x}"

    await machine.writel(CLKCTRL_BASE + 0x070, 0x00000000)
    ssp = await machine.readl(CLKCTRL_BASE + 0x070)
    assert ssp == 0x00000028, f"CLKCTRL SSP should reject DIV=0 and preserve the previous valid divider: got 0x{ssp:x}"

    await machine.writel(CLKCTRL_BASE + 0x080, 0x00000028)
    await machine.writel(CLKCTRL_BASE + 0x080, 0x00000028)
    await machine.readl(CLKCTRL_BASE + 0x080)
    gpmi = await machine.readl(CLKCTRL_BASE + 0x080)
    assert gpmi == 0x00000028, f"CLKCTRL GPMI should accept a valid divider once ungated: got 0x{gpmi:x}"

    await machine.writel(CLKCTRL_BASE + 0x080, 0x00000000)
    gpmi = await machine.readl(CLKCTRL_BASE + 0x080)
    assert gpmi == 0x00000028, f"CLKCTRL GPMI should reject DIV=0 and preserve the previous valid divider: got 0x{gpmi:x}"


async def test_clkctrl_busy_contract(machine):
    """CLKCTRL busy contract"""
    cpu_reset = await machine.readl(CLKCTRL_BASE + 0x020)
    assert cpu_reset & 0x30000000 == 0, f"CLKCTRL CPU busy bits should reset low: got 0x{cpu_reset:x}"

    await machine.writel(CLKCTRL_BASE + 0x020, 0x00010002)
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    assert (cpu >> 28) & 1 == 1, f"CLKCTRL CPU should raise BUSY_REF_CPU when DIV_CPU changes: got 0x{cpu:x}"
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    assert (cpu >> 28) & 1 == 0, f"CLKCTRL CPU BUSY_REF_CPU should clear after the transfer completes: got 0x{cpu:x}"

    await machine.writel(CLKCTRL_BASE + 0x020, 0x00020002)
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    assert (cpu >> 29) & 1 == 1, f"CLKCTRL CPU should raise BUSY_REF_XTAL when DIV_XTAL changes: got 0x{cpu:x}"
    cpu = await machine.readl(CLKCTRL_BASE + 0x020)
    assert (cpu >> 29) & 1 == 0, f"CLKCTRL CPU BUSY_REF_XTAL should clear after the transfer completes: got 0x{cpu:x}"

    await machine.writel(CLKCTRL_BASE + 0x030, 0x00000002)
    hbus = await machine.readl(CLKCTRL_BASE + 0x030)
    assert (hbus >> 29) & 1 == 1, f"CLKCTRL HBUS should raise BUSY when DIV changes: got 0x{hbus:x}"
    hbus = await machine.readl(CLKCTRL_BASE + 0x030)
    assert (hbus >> 29) & 1 == 0, f"CLKCTRL HBUS BUSY should clear after the transfer completes: got 0x{hbus:x}"

    await machine.writel(CLKCTRL_BASE + 0x040, 0x00000004)
    xbus = await machine.readl(CLKCTRL_BASE + 0x040)
    assert (xbus >> 31) & 1 == 1, f"CLKCTRL XBUS should raise BUSY when DIV changes: got 0x{xbus:x}"
    xbus = await machine.readl(CLKCTRL_BASE + 0x040)
    assert (xbus >> 31) & 1 == 0, f"CLKCTRL XBUS BUSY should clear after the transfer completes: got 0x{xbus:x}"

    for name, addr in [
        ("PIX", CLKCTRL_BASE + 0x060),
        ("SSP", CLKCTRL_BASE + 0x070),
        ("GPMI", CLKCTRL_BASE + 0x080),
    ]:
        await machine.writel(addr, 0x00000028)
        await machine.writel(addr, 0x00000028)
        reg = await machine.readl(addr)
        assert (reg >> 29) & 1 == 1, f"CLKCTRL {name} should raise BUSY when DIV changes while ungated: got 0x{reg:x}"
        reg = await machine.readl(addr)
        assert (reg >> 29) & 1 == 0, f"CLKCTRL {name} BUSY should clear after the transfer completes: got 0x{reg:x}"


async def test_clkctrl_frac_range_contract(machine):
    """CLKCTRL FRAC range contract"""
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert frac == 0x92920092, f"CLKCTRL FRAC should reset to the documented 0x12 dividers: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92920011)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert frac & 0x3f == 0x12, f"CLKCTRL FRAC should reject CPUFRAC values below 18: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92920023)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert frac & 0x3f == 0x23, f"CLKCTRL FRAC should accept CPUFRAC values within 18..35: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92920024)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert frac & 0x3f == 0x23, f"CLKCTRL FRAC should reject CPUFRAC values above 35 and preserve the previous valid value: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92120024)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 16) & 0x3f == 0x12, f"CLKCTRL FRAC should reject PIXFRAC values below 18: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92230023)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 16) & 0x3f == 0x23, f"CLKCTRL FRAC should accept PIXFRAC values within 18..35: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x92240023)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 16) & 0x3f == 0x23, f"CLKCTRL FRAC should reject PIXFRAC values above 35 and preserve the previous valid value: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x11240024)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 24) & 0x3f == 0x12, f"CLKCTRL FRAC should reject IOFRAC values below 18: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x23230023)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 24) & 0x3f == 0x23, f"CLKCTRL FRAC should accept IOFRAC values within 18..35: got 0x{frac:x}"

    await machine.writel(CLKCTRL_BASE + 0x0d0, 0x24230023)
    frac = await machine.readl(CLKCTRL_BASE + 0x0d0)
    assert (frac >> 24) & 0x3f == 0x23, f"CLKCTRL FRAC should reject IOFRAC values above 35 and preserve the previous valid value: got 0x{frac:x}"


async def test_clkctrl_clkseq_gate_contract():
    """CLKCTRL CLKSEQ gate contract"""
    async with with_machine() as machine:
        clkseq_reset = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq_reset == 0x000000bb, f"CLKCTRL CLKSEQ should reset with all documented bypass bits set: got 0x{clkseq_reset:x}"

        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x0000003b)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x000000ba, f"CLKCTRL CLKSEQ should ignore CPU bypass switching while FRAC.CLKGATECPU keeps ref_cpu gated: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x0d8, 0x00000080)
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x0000003a)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x0000003a, f"CLKCTRL CLKSEQ should allow CPU bypass switching once ref_cpu is ungated: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x0d4, 0x00000080)
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x000000ba)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x0000003a, f"CLKCTRL CLKSEQ should ignore CPU bypass switching back to XTAL while FRAC.CLKGATECPU is asserted: got 0x{clkseq:x}"

    async with with_machine() as machine:
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x000000b3)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x000000ba, f"CLKCTRL CLKSEQ should ignore IR bypass switching while FRAC.CLKGATEIO keeps ref_io gated: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x0d8, 0x80000000)
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x000000b2)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x000000b2, f"CLKCTRL CLKSEQ should allow IR bypass switching once ref_io is ungated: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x00000092)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x000000b2, f"CLKCTRL CLKSEQ should ignore SSP bypass switching while SSP.CLKGATE is still asserted: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x070, 0x00000028)
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x00000092)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x00000092, f"CLKCTRL CLKSEQ should allow SSP bypass switching once ref_io and SSP are both ungated: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x00000082)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x00000092, f"CLKCTRL CLKSEQ should ignore GPMI bypass switching while GPMI.CLKGATE is still asserted: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x080, 0x00000028)
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x00000082)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x00000082, f"CLKCTRL CLKSEQ should allow GPMI bypass switching once ref_io and GPMI are both ungated: got 0x{clkseq:x}"

    async with with_machine() as machine:
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x000000b9)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x000000ba, f"CLKCTRL CLKSEQ should ignore PIX bypass switching while FRAC.CLKGATEPIX keeps ref_pix gated: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x0d8, 0x00800000)
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x000000b8)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x000000ba, f"CLKCTRL CLKSEQ should ignore PIX bypass switching while PIX.CLKGATE is still asserted: got 0x{clkseq:x}"

        await machine.writel(CLKCTRL_BASE + 0x060, 0x00000028)
        await machine.writel(CLKCTRL_BASE + 0x0e0, 0x000000b8)
        clkseq = await machine.readl(CLKCTRL_BASE + 0x0e0)
        assert clkseq == 0x000000b8, f"CLKCTRL CLKSEQ should allow PIX bypass switching once ref_pix and PIX are both ungated: got 0x{clkseq:x}"
