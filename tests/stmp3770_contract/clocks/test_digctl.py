from framework.constants import CLKCTRL_BASE, DIGCTL_BASE, ICOLL_BASE


async def test_digctl_writable_field_masks(machine):
    """DIGCTL writable field masks"""
    await machine.writel(DIGCTL_BASE + 0x030, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x040, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x050, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x0f0, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x2b0, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x330, 0xffffffff)

    ramctrl = await machine.readl(DIGCTL_BASE + 0x030)
    ramrepair = await machine.readl(DIGCTL_BASE + 0x040)
    romctrl = await machine.readl(DIGCTL_BASE + 0x050)
    ocram_bist = await machine.readl(DIGCTL_BASE + 0x0f0)
    armcache = await machine.readl(DIGCTL_BASE + 0x2b0)
    ahb_stats_select = await machine.readl(DIGCTL_BASE + 0x330)

    assert ramctrl == 0x00000f01, f"DIGCTL RAMCTRL should only expose SPEED_SELECT/RAM_REPAIR_EN: got 0x{ramctrl:x}"
    assert ramrepair == 0x0000ffff, f"DIGCTL RAMREPAIR should only expose ADDR[15:0]: got 0x{ramrepair:x}"
    assert romctrl == 0x0000000f, f"DIGCTL ROMCTRL should only expose RD_MARGIN[3:0]: got 0x{romctrl:x}"
    assert ocram_bist == 0x00000306, f"DIGCTL OCRAM_BIST_CSR should keep writable bits and self-clear START: got 0x{ocram_bist:x}"
    assert armcache == 0x00000333, f"DIGCTL ARMCACHE should only expose CACHE_SS/DTAG_SS/ITAG_SS: got 0x{armcache:x}"
    assert ahb_stats_select == 0x0f0f0f0f, f"DIGCTL AHB_STATS_SELECT should only expose layer-select nibbles: got 0x{ahb_stats_select:x}"


async def test_digctl_scratch_and_microseconds_contract(machine):
    """DIGCTL scratch and microseconds contract"""
    scratch0_reset = await machine.readl(DIGCTL_BASE + 0x290)
    scratch1_reset = await machine.readl(DIGCTL_BASE + 0x2a0)

    assert scratch0_reset == 0, f"DIGCTL SCRATCH0 should reset to 0: got 0x{scratch0_reset:x}"
    assert scratch1_reset == 0, f"DIGCTL SCRATCH1 should reset to 0: got 0x{scratch1_reset:x}"

    await machine.writel(DIGCTL_BASE + 0x290, 0x89abcdef)
    await machine.writel(DIGCTL_BASE + 0x2a0, 0x01234567)

    scratch0 = await machine.readl(DIGCTL_BASE + 0x290)
    scratch1 = await machine.readl(DIGCTL_BASE + 0x2a0)

    assert scratch0 == 0x89abcdef, f"DIGCTL SCRATCH0 should store arbitrary scratch data: got 0x{scratch0:x}"
    assert scratch1 == 0x01234567, f"DIGCTL SCRATCH1 should store arbitrary scratch data: got 0x{scratch1:x}"

    await machine.writel(DIGCTL_BASE + 0x0c0, 0x00000100)
    microseconds = await machine.readl(DIGCTL_BASE + 0x0c0)
    assert microseconds == 0x00000100, f"DIGCTL MICROSECONDS base write should seed the counter value: got 0x{microseconds:x}"

    await machine.writel(DIGCTL_BASE + 0x0c4, 0x00000020)
    microseconds = await machine.readl(DIGCTL_BASE + 0x0c0)
    assert microseconds == 0x00000120, f"DIGCTL MICROSECONDS_SET should OR bits into the current value: got 0x{microseconds:x}"

    await machine.writel(DIGCTL_BASE + 0x0c8, 0x00000010)
    microseconds = await machine.readl(DIGCTL_BASE + 0x0c0)
    assert microseconds == 0x00000120, f"DIGCTL MICROSECONDS_CLR should only clear selected bits: got 0x{microseconds:x}"

    await machine.writel(DIGCTL_BASE + 0x0cc, 0x00000001)
    microseconds = await machine.readl(DIGCTL_BASE + 0x0c0)
    assert microseconds == 0x00000121, f"DIGCTL MICROSECONDS_TOG should XOR selected bits: got 0x{microseconds:x}"


async def test_digctl_undocumented_alias_decode(machine):
    """DIGCTL undocumented alias decode"""
    await machine.writel(DIGCTL_BASE + 0x0400, 0x00000055)
    await machine.writel(DIGCTL_BASE + 0x0290, 0x89abcdef)
    await machine.writel(DIGCTL_BASE + 0x02b0, 0x00000321)
    await machine.writel(DIGCTL_BASE + 0x0330, 0x01020304)

    scratch0_alias_read = await machine.readl(DIGCTL_BASE + 0x0294)
    armcache_alias_read = await machine.readl(DIGCTL_BASE + 0x02b4)
    ahb_stats_alias_read = await machine.readl(DIGCTL_BASE + 0x0334)
    mpte0_alias_read = await machine.readl(DIGCTL_BASE + 0x0404)

    assert scratch0_alias_read == 0, f"DIGCTL SCRATCH0 undocumented +0x4 alias should decode as hole: got 0x{scratch0_alias_read:x}"
    assert armcache_alias_read == 0, f"DIGCTL ARMCACHE undocumented +0x4 alias should decode as hole: got 0x{armcache_alias_read:x}"
    assert ahb_stats_alias_read == 0, f"DIGCTL AHB_STATS_SELECT undocumented +0x4 alias should decode as hole: got 0x{ahb_stats_alias_read:x}"
    assert mpte0_alias_read == 0, f"DIGCTL MPTE0_LOC undocumented +0x4 alias should decode as hole: got 0x{mpte0_alias_read:x}"

    await machine.writel(DIGCTL_BASE + 0x0294, 0x13572468)
    await machine.writel(DIGCTL_BASE + 0x02b4, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x0334, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x0404, 0x00000a00)

    scratch0 = await machine.readl(DIGCTL_BASE + 0x0290)
    armcache = await machine.readl(DIGCTL_BASE + 0x02b0)
    ahb_stats_select = await machine.readl(DIGCTL_BASE + 0x0330)
    mpte0_loc = await machine.readl(DIGCTL_BASE + 0x0400)

    assert scratch0 == 0x89abcdef, f"DIGCTL SCRATCH0 base register should ignore undocumented alias writes: got 0x{scratch0:x}"
    assert armcache == 0x00000321, f"DIGCTL ARMCACHE base register should ignore undocumented alias writes: got 0x{armcache:x}"
    assert ahb_stats_select == 0x01020304, f"DIGCTL AHB_STATS_SELECT base register should ignore undocumented alias writes: got 0x{ahb_stats_select:x}"
    assert mpte0_loc == 0x00000055, f"DIGCTL MPTE0_LOC base register should ignore undocumented alias writes: got 0x{mpte0_loc:x}"


async def test_digctl_ctrl_behavior_contract(machine):
    """DIGCTL ctrl behavior contract"""
    ctrl_reset = await machine.readl(DIGCTL_BASE + 0x000)
    assert ctrl_reset == 0x00000004, f"DIGCTL CTRL should reset with only USB_CLKGATE set: got 0x{ctrl_reset:x}"

    await machine.writel(DIGCTL_BASE + 0x004, 0x00000008)
    ctrl_after_debug_disable_set = await machine.readl(DIGCTL_BASE + 0x000)
    assert ctrl_after_debug_disable_set == 0x0000000c, f"DIGCTL CTRL.DEBUG_DISABLE should latch high when set: got 0x{ctrl_after_debug_disable_set:x}"

    await machine.writel(DIGCTL_BASE + 0x008, 0x00000008)
    ctrl_after_debug_disable_clear = await machine.readl(DIGCTL_BASE + 0x000)
    assert ctrl_after_debug_disable_clear == 0x0000000c, f"DIGCTL CTRL.DEBUG_DISABLE should stay set until reset: got 0x{ctrl_after_debug_disable_clear:x}"

    await machine.writel(CLKCTRL_BASE + 0x0f0, 0x00000001)
    ctrl_after_dig_reset = await machine.readl(DIGCTL_BASE + 0x000)
    assert ctrl_after_dig_reset == 0x0000000c, f"DIGCTL CTRL.DEBUG_DISABLE should survive RESET.DIG and only recover after power-on/chip reset: got 0x{ctrl_after_dig_reset:x}"

    entropy_latched_reset = await machine.readl(DIGCTL_BASE + 0x0a0)
    assert entropy_latched_reset == 0, f"DIGCTL ENTROPY_LATCHED should reset to 0: got 0x{entropy_latched_reset:x}"

    await machine.clock_step(1_000_000)
    await machine.writel(DIGCTL_BASE + 0x004, 0x00000001)
    entropy_latched1 = await machine.readl(DIGCTL_BASE + 0x0a0)
    assert entropy_latched1 != 0, f"DIGCTL CTRL.LATCH_ENTROPY should latch the live entropy value on first set: got 0x{entropy_latched1:x}"

    await machine.clock_step(1_000_000)
    await machine.writel(DIGCTL_BASE + 0x004, 0x00000001)
    entropy_latched2 = await machine.readl(DIGCTL_BASE + 0x0a0)
    assert entropy_latched2 != entropy_latched1, f"DIGCTL CTRL.LATCH_ENTROPY should re-latch on repeated set writes: first=0x{entropy_latched1:x} second=0x{entropy_latched2:x}"


async def test_digctl_writeonce_resets_with_dig_reset(machine):
    """DIGCTL writeonce resets with dig reset"""
    writeonce_reset = await machine.readl(DIGCTL_BASE + 0x060)
    status_reset = await machine.readl(DIGCTL_BASE + 0x010)

    assert writeonce_reset == 0xa5a5a5a5, f"DIGCTL WRITEONCE should reset to its documented seed: got 0x{writeonce_reset:x}"
    assert status_reset & 0x1 == 0, f"DIGCTL STATUS.WRITTEN should reset low: got 0x{status_reset:x}"

    await machine.writel(DIGCTL_BASE + 0x060, 0x12345678)
    writeonce_written = await machine.readl(DIGCTL_BASE + 0x060)
    status_after_write = await machine.readl(DIGCTL_BASE + 0x010)

    assert writeonce_written == 0x12345678, f"DIGCTL WRITEONCE should accept the first write: got 0x{writeonce_written:x}"
    assert status_after_write & 0x1 != 0, f"DIGCTL STATUS.WRITTEN should set after a successful WRITEONCE write: got 0x{status_after_write:x}"

    await machine.writel(DIGCTL_BASE + 0x060, 0x87654321)
    writeonce_locked = await machine.readl(DIGCTL_BASE + 0x060)
    status_after_second_write = await machine.readl(DIGCTL_BASE + 0x010)

    assert writeonce_locked == 0x12345678, f"DIGCTL WRITEONCE should ignore later writes until chip-wide reset: got 0x{writeonce_locked:x}"
    assert status_after_second_write & 0x1 != 0, f"DIGCTL STATUS.WRITTEN should remain set after ignored WRITEONCE writes: got 0x{status_after_second_write:x}"

    await machine.writel(CLKCTRL_BASE + 0x0f0, 0x00000001)
    writeonce_after_dig_reset = await machine.readl(DIGCTL_BASE + 0x060)
    status_after_dig_reset = await machine.readl(DIGCTL_BASE + 0x010)

    assert writeonce_after_dig_reset == 0xa5a5a5a5, f"DIGCTL WRITEONCE should reset with RESET.DIG: got 0x{writeonce_after_dig_reset:x}"
    assert status_after_dig_reset & 0x1 == 0, f"DIGCTL STATUS.WRITTEN should clear with RESET.DIG: got 0x{status_after_dig_reset:x}"

    await machine.writel(DIGCTL_BASE + 0x060, 0x87654321)
    writeonce_after_dig_reset_write = await machine.readl(DIGCTL_BASE + 0x060)
    assert writeonce_after_dig_reset_write == 0x87654321, f"DIGCTL WRITEONCE should accept a first write after RESET.DIG: got 0x{writeonce_after_dig_reset_write:x}"


async def test_digctl_hclk_count_contract(machine):
    """DIGCTL HCLK counter contract"""
    hclk_start = await machine.readl(DIGCTL_BASE + 0x020)
    await machine.clock_step(1_000)
    hclk_at_24mhz = await machine.readl(DIGCTL_BASE + 0x020)

    assert (hclk_at_24mhz - hclk_start) & 0xffffffff == 24, f"DIGCTL HCLKCOUNT must advance once per 24 MHz HCLK edge: start=0x{hclk_start:x}, end=0x{hclk_at_24mhz:x}"

    hclk_before_fractional_reads = await machine.readl(DIGCTL_BASE + 0x020)
    await machine.clock_step(20)
    hclk_after_first_fractional_read = await machine.readl(DIGCTL_BASE + 0x020)
    await machine.clock_step(22)
    hclk_after_second_fractional_read = await machine.readl(DIGCTL_BASE + 0x020)

    assert (hclk_after_first_fractional_read - hclk_before_fractional_reads) & 0xffffffff == 0, (
        "DIGCTL HCLKCOUNT must not increment before a 24 MHz HCLK edge"
    )
    assert (hclk_after_second_fractional_read - hclk_before_fractional_reads) & 0xffffffff == 1, (
        "DIGCTL HCLKCOUNT must retain fractional time across reads until an HCLK edge occurs"
    )

    await machine.writel(CLKCTRL_BASE + 0x030, 0x00000002)
    hclk_before_divide = await machine.readl(DIGCTL_BASE + 0x020)
    await machine.clock_step(1_000)
    hclk_at_12mhz = await machine.readl(DIGCTL_BASE + 0x020)

    assert (hclk_at_12mhz - hclk_before_divide) & 0xffffffff == 12, f"DIGCTL HCLKCOUNT must follow HBUS.DIV=2: start=0x{hclk_before_divide:x}, end=0x{hclk_at_12mhz:x}"

    await machine.writel(CLKCTRL_BASE + 0x030, 0x00000001)
    await machine.writel(CLKCTRL_BASE + 0x0d8, 0x00000080)
    await machine.writel(CLKCTRL_BASE + 0x004, 0x00010000)
    await machine.writel(CLKCTRL_BASE + 0x0e8, 0x00000080)
    await machine.writel(CLKCTRL_BASE + 0x020, 0x00000600)

    hclk_before_cpu_fractional_divide = await machine.readl(DIGCTL_BASE + 0x020)
    await machine.clock_step(1_000)
    hclk_at_240mhz = await machine.readl(DIGCTL_BASE + 0x020)

    assert (hclk_at_240mhz - hclk_before_cpu_fractional_divide) & 0xffffffff == 240, f"DIGCTL HCLKCOUNT must honor CPU.DIV_CPU_FRAC_EN at bit 10: start=0x{hclk_before_cpu_fractional_divide:x}, end=0x{hclk_at_240mhz:x}"


async def test_digctl_read_only_status_contract(machine):
    """DIGCTL read-only status contract"""
    sjtag_reset = await machine.readl(DIGCTL_BASE + 0x0b0)
    dbgrd = await machine.readl(DIGCTL_BASE + 0x0d0)
    dbg = await machine.readl(DIGCTL_BASE + 0x0e0)
    chip_id = await machine.readl(DIGCTL_BASE + 0x310)

    assert sjtag_reset == 0x00020000, f"DIGCTL SJTAGDBG reset mismatch: got 0x{sjtag_reset:x}"
    assert dbgrd == 0x789abcde, f"DIGCTL DBGRD fixed complement mismatch: got 0x{dbgrd:x}"
    assert dbg == 0x87654321, f"DIGCTL DBG fixed value mismatch: got 0x{dbg:x}"
    assert chip_id == 0x37b00000, f"DIGCTL CHIPID table reset mismatch: got 0x{chip_id:x}"

    await machine.writel(DIGCTL_BASE + 0x0b0, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x0d0, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x0e0, 0xffffffff)
    await machine.writel(DIGCTL_BASE + 0x310, 0xffffffff)

    assert await machine.readl(DIGCTL_BASE + 0x0b0) == 0x00020003, (
        "DIGCTL SJTAGDBG must retain only diagnostic output bits 1:0"
    )
    assert await machine.readl(DIGCTL_BASE + 0x0d0) == dbgrd, "DIGCTL DBGRD must be read-only"
    assert await machine.readl(DIGCTL_BASE + 0x0e0) == dbg, "DIGCTL DBG must be read-only"
    assert await machine.readl(DIGCTL_BASE + 0x310) == chip_id, "DIGCTL CHIPID must be read-only"

    await machine.writel(DIGCTL_BASE + 0x0f0, 0x00000101)
    assert await machine.readl(DIGCTL_BASE + 0x0f0) == 0x00000106, (
        "DIGCTL OCRAM_BIST_CSR must self-clear START and report a completed passing BIST"
    )


async def test_digctl_dcp_bist_status_contract(machine):
    """DIGCTL DCP BIST status contract"""
    assert await machine.readl(DIGCTL_BASE + 0x010) == 0xf0000000, (
        "DIGCTL STATUS must reset with USB features present and DCP BIST not done"
    )

    await machine.writel(DIGCTL_BASE + 0x000, 0x00c00004)
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x00c00004, (
        "DIGCTL CTRL must accept DCP_BIST_CLKEN and DCP_BIST_START"
    )
    assert await machine.readl(DIGCTL_BASE + 0x010) == 0xf0000300, (
        "DIGCTL STATUS must report DCP BIST done and pass after start"
    )

    await machine.writel(DIGCTL_BASE + 0x008, 0x00400000)
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x00800004, (
        "DIGCTL CTRL DCP_BIST_START must clear via CLR alias"
    )
    assert await machine.readl(DIGCTL_BASE + 0x010) == 0xf0000300, (
        "DIGCTL STATUS DCP BIST done/pass must remain sticky after start bit clears"
    )

    await machine.writel(DIGCTL_BASE + 0x010, 0xffffffff)
    assert await machine.readl(DIGCTL_BASE + 0x010) == 0xf0000300, (
        "DIGCTL STATUS must be read-only and preserve DCP BIST sticky bits"
    )


async def test_digctl_trap_contract(machine):
    """DIGCTL trap contract"""
    trap_range_low = 0x8001c010
    trap_range_high = 0x8001c01f
    trap_irq_mask = 1 << 15  # ICOLL RAW1 bit 15 = source 47 DIGCTL_TRAP

    await machine.writel(DIGCTL_BASE + 0x2c0, trap_range_low)
    await machine.writel(DIGCTL_BASE + 0x2d0, trap_range_high)
    await machine.writel(DIGCTL_BASE + 0x000, 0x00000034)

    assert await machine.readl(DIGCTL_BASE + 0x2c0) == trap_range_low, (
        "DIGCTL DEBUG_TRAP_ADDR_LOW must retain written value"
    )
    assert await machine.readl(DIGCTL_BASE + 0x2d0) == trap_range_high, (
        "DIGCTL DEBUG_TRAP_ADDR_HIGH must retain written value"
    )
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x00000034, (
        "DIGCTL CTRL must reflect TRAP_ENABLE, TRAP_IN_RANGE and USB_CLKGATE"
    )
    assert await machine.readl(ICOLL_BASE + 0x050) == 0, (
        "ICOLL RAW1 source 47 must be deasserted before a trap"
    )

    status = await machine.readl(DIGCTL_BASE + 0x010)
    assert status == 0xf0000000, (
        "DIGCTL STATUS read must still return the correct value when trapped"
    )
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x20000034, (
        "DIGCTL CTRL.TRAP_IRQ must set when an in-range AHB access is trapped"
    )
    assert await machine.readl(ICOLL_BASE + 0x050) == trap_irq_mask, (
        "ICOLL source 47 (DIGCTL_TRAP) must assert when TRAP_IRQ is set"
    )

    await machine.writel(DIGCTL_BASE + 0x008, 0x20000000)
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x00000034, (
        "DIGCTL CTRL.TRAP_IRQ must clear via CLR alias"
    )
    assert await machine.readl(ICOLL_BASE + 0x050) == 0, (
        "ICOLL source 47 must deassert when TRAP_IRQ is cleared"
    )

    await machine.writel(DIGCTL_BASE + 0x000, 0x00000014)
    await machine.readl(DIGCTL_BASE + 0x000)
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x20000014, (
        "DIGCTL CTRL.TRAP_IRQ must set when an out-of-range AHB access is trapped and TRAP_IN_RANGE=0"
    )
    assert await machine.readl(ICOLL_BASE + 0x050) == trap_irq_mask, (
        "ICOLL source 47 must assert on out-of-range trap"
    )

    await machine.writel(DIGCTL_BASE + 0x000, 0x20000034)
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x00000034, (
        "DIGCTL CTRL.TRAP_IRQ must be W1C-clearable via base write"
    )
    assert await machine.readl(ICOLL_BASE + 0x050) == 0, (
        "ICOLL source 47 must deassert when TRAP_IRQ is W1C-cleared"
    )

    await machine.writel(DIGCTL_BASE + 0x000, 0x00000004)
    await machine.readl(DIGCTL_BASE + 0x010)
    assert await machine.readl(DIGCTL_BASE + 0x000) == 0x00000004, (
        "DIGCTL CTRL.TRAP_IRQ must not set when TRAP_ENABLE is disabled"
    )
    assert await machine.readl(ICOLL_BASE + 0x050) == 0, (
        "ICOLL source 47 must stay deasserted when TRAP_ENABLE is disabled"
    )
