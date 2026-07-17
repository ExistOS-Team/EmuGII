import pytest

from framework.constants import ICOLL_BASE


@pytest.mark.asyncio
async def test_icoll_core_contract(machine):
    """ICOLL core contract"""
    ctrl_reset = await machine.readl(ICOLL_BASE + 0x020)
    version = await machine.readl(ICOLL_BASE + 0x1D0)
    debug_read0 = await machine.readl(ICOLL_BASE + 0x180)
    debug_read1 = await machine.readl(ICOLL_BASE + 0x190)

    assert ctrl_reset == 0xC0030000, f"ICOLL CTRL reset mismatch: got 0x{ctrl_reset:x}"
    assert version == 0x02000000, f"ICOLL VERSION mismatch: got 0x{version:x}"
    assert debug_read0 == 0xECA94567, f"ICOLL DEBUGRD0 mismatch: got 0x{debug_read0:x}"
    assert debug_read1 == 0x1356DA98, f"ICOLL DEBUGRD1 mismatch: got 0x{debug_read1:x}"

    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x160, 0xFFFFFFFF)
    await machine.writel(ICOLL_BASE + 0x060, 0xFFFFFFFF)

    vbase = await machine.readl(ICOLL_BASE + 0x160)
    priority0 = await machine.readl(ICOLL_BASE + 0x060)

    assert vbase == 0xFFFFFFFC, f"ICOLL VBASE must keep word alignment: got 0x{vbase:x}"
    assert priority0 == 0x0F0F0F0F, f"ICOLL PRIORITY0 must hide reserved nibbles: got 0x{priority0:x}"

    await machine.writel(ICOLL_BASE + 0x060, 0)
    await machine.writel(ICOLL_BASE + 0x000, 0)
    await machine.writel(ICOLL_BASE + 0x010, 0x00000008)

    await machine.writel(ICOLL_BASE + 0x160, 0x00001000)
    await machine.writel(ICOLL_BASE + 0x060, 0x00000F00)
    await machine.clock_step(84)

    vector = await machine.readl(ICOLL_BASE + 0x000)
    stat = await machine.readl(ICOLL_BASE + 0x030)

    assert vector == 0x00001004, f"ICOLL must select the highest-priority SOFTIRQ source: got 0x{vector:x}"
    assert (stat & 0x3F) == 1, f"ICOLL STAT must report selected source 1: got 0x{stat:x}"

    await machine.writel(ICOLL_BASE + 0x024, 0x00200000)
    pitch_one_vector = await machine.readl(ICOLL_BASE + 0x000)
    assert pitch_one_vector == 0x00001004, (
        f"ICOLL VECTOR_PITCH=1 must remain a 4-byte stride: got 0x{pitch_one_vector:x}"
    )


@pytest.mark.asyncio
async def test_icoll_same_level_priority_contract(machine):
    """ICOLL same-level priority contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x160, 0x00001000)
    await machine.writel(ICOLL_BASE + 0x060, 0x0C00000C)
    await machine.clock_step(84)

    assert await machine.readl(ICOLL_BASE + 0x000) == 0x0000100C, (
        "ICOLL must select the highest-numbered source when same-level requests coincide"
    )
    assert (await machine.readl(ICOLL_BASE + 0x030) & 0x3F) == 3, (
        "ICOLL STAT must report the highest-numbered same-level source"
    )


@pytest.mark.asyncio
async def test_icoll_bypass_same_level_priority_contract(machine):
    """ICOLL BYPASS same-level priority contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x024, 0x00100000)
    await machine.writel(ICOLL_BASE + 0x160, 0x00001000)
    await machine.writel(ICOLL_BASE + 0x060, 0x0C00000C)

    assert await machine.readl(ICOLL_BASE + 0x000) == 0x0000100C, (
        "ICOLL BYPASS_FSM must use the highest-numbered coincident request"
    )


@pytest.mark.asyncio
async def test_icoll_vector_acknowledge_contract(machine):
    """ICOLL vector acknowledge contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x160, 0x00002000)
    await machine.writel(ICOLL_BASE + 0x060, 0x00000F0C)
    await machine.clock_step(84)

    high_vector = await machine.readl(ICOLL_BASE + 0x000)
    assert high_vector == 0x00002004, f"ICOLL should select level 3 source first: got 0x{high_vector:x}"

    await machine.writel(ICOLL_BASE + 0x000, 0)
    await machine.writel(ICOLL_BASE + 0x068, 0x00000800)

    before_acknowledge = await machine.readl(ICOLL_BASE + 0x000)
    assert before_acknowledge == 0x00002004, (
        f"ICOLL VECTOR must remain on the in-service level until LEVELACK: got 0x{before_acknowledge:x}"
    )

    await machine.writel(ICOLL_BASE + 0x010, 0x00000008)
    await machine.clock_step(84)
    after_acknowledge = await machine.readl(ICOLL_BASE + 0x000)
    assert after_acknowledge == 0x00002000, (
        f"ICOLL LEVELACK bit 3 must release level 3 for level 0: got 0x{after_acknowledge:x}"
    )


@pytest.mark.asyncio
async def test_icoll_arm_rse_mode_contract(machine):
    """ICOLL ARM_RSE mode contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x024, 0x00040000)
    await machine.writel(ICOLL_BASE + 0x160, 0x00003000)
    await machine.writel(ICOLL_BASE + 0x060, 0x00000F0C)
    await machine.clock_step(84)

    high_vector = await machine.readl(ICOLL_BASE + 0x000)
    assert high_vector == 0x00003004, f"ICOLL should select level 3 source first: got 0x{high_vector:x}"

    await machine.writel(ICOLL_BASE + 0x068, 0x00000800)
    before_acknowledge = await machine.readl(ICOLL_BASE + 0x000)
    assert before_acknowledge == 0x00003004, (
        f"ICOLL ARM_RSE_MODE read must enter service before LEVELACK: got 0x{before_acknowledge:x}"
    )

    await machine.writel(ICOLL_BASE + 0x010, 0x00000008)
    await machine.clock_step(84)
    after_acknowledge = await machine.readl(ICOLL_BASE + 0x000)
    assert after_acknowledge == 0x00003000, (
        f"ICOLL ARM_RSE_MODE must let LEVELACK release the read vector: got 0x{after_acknowledge:x}"
    )


@pytest.mark.asyncio
async def test_icoll_no_nesting_contract(machine):
    """ICOLL no nesting contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x024, 0x00080000)
    await machine.writel(ICOLL_BASE + 0x160, 0x00004000)
    await machine.writel(ICOLL_BASE + 0x060, 0x0000000C)
    await machine.clock_step(84)

    low_vector = await machine.readl(ICOLL_BASE + 0x000)
    assert low_vector == 0x00004000, f"ICOLL should select level 0 source first: got 0x{low_vector:x}"

    await machine.writel(ICOLL_BASE + 0x000, 0)
    await machine.writel(ICOLL_BASE + 0x064, 0x00000F00)

    while_in_service = await machine.readl(ICOLL_BASE + 0x000)
    assert while_in_service == 0x00004000, (
        f"ICOLL NO_NESTING must block higher priority preemption: got 0x{while_in_service:x}"
    )


@pytest.mark.asyncio
async def test_icoll_debug_flag_contract(machine):
    """ICOLL debug flag contract"""
    reset = await machine.readl(ICOLL_BASE + 0x1A0)
    assert reset == 0, f"ICOLL DEBUGFLAG should reset to 0: got 0x{reset:x}"

    await machine.writel(ICOLL_BASE + 0x1A0, 0xFFFFFFFF)
    written = await machine.readl(ICOLL_BASE + 0x1A0)
    assert written == 0x0000FFFF, f"ICOLL DEBUGFLAG must expose only bits 15:0: got 0x{written:x}"

    await machine.writel(ICOLL_BASE + 0x1A8, 0x000000F0)
    cleared = await machine.readl(ICOLL_BASE + 0x1A0)
    assert cleared == 0x0000FF0F, f"ICOLL DEBUGFLAG_CLR should clear selected flags: got 0x{cleared:x}"

    await machine.writel(ICOLL_BASE + 0x1AC, 0x0000000F)
    toggled = await machine.readl(ICOLL_BASE + 0x1A0)
    assert toggled == 0x0000FF00, f"ICOLL DEBUGFLAG_TOG should toggle selected flags: got 0x{toggled:x}"


@pytest.mark.asyncio
async def test_icoll_debug_state_contract(machine):
    """ICOLL debug state contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x024, 0x00000001)
    await machine.writel(ICOLL_BASE + 0x0D0, 0x00000008)

    debug = await machine.readl(ICOLL_BASE + 0x170)
    request_low = await machine.readl(ICOLL_BASE + 0x1B0)

    assert (debug & (1 << 16)) == 0, (
        f"ICOLL DEBUG.IRQ must remain low for a source routed to FIQ: debug=0x{debug:x}"
    )
    assert (debug & (1 << 17)) != 0, (
        f"ICOLL DEBUG.FIQ must reflect the asserted CPU FIQ output: debug=0x{debug:x}"
    )
    assert (request_low & (1 << 28)) != 0, (
        f"ICOLL DBGREQUEST0 must expose software request 28: request=0x{request_low:x}"
    )

    await machine.writel(ICOLL_BASE + 0x170, 0xFFFFFFFF)
    await machine.writel(ICOLL_BASE + 0x1B0, 0xFFFFFFFF)
    assert await machine.readl(ICOLL_BASE + 0x170) == debug, "ICOLL DEBUG must be read-only"
    assert await machine.readl(ICOLL_BASE + 0x1B0) == request_low, (
        "ICOLL DBGREQUEST0 must be read-only"
    )

    await machine.writel(ICOLL_BASE + 0x028, 0x00020000)
    debug_with_final_fiq_disabled = await machine.readl(ICOLL_BASE + 0x170)
    assert (debug_with_final_fiq_disabled & (1 << 17)) == 0, (
        f"ICOLL DEBUG.FIQ must follow FIQ_FINAL_ENABLE: debug=0x{debug_with_final_fiq_disabled:x}"
    )


@pytest.mark.asyncio
async def test_icoll_soft_reset_contract(machine):
    """ICOLL soft reset contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x1A0, 0x0000005A)

    await machine.writel(ICOLL_BASE + 0x024, 0xC0000000)
    assert await machine.readl(ICOLL_BASE + 0x1A0) == 0x0000005A, (
        "ICOLL simultaneous SFTRST and CLKGATE must leave state unchanged"
    )

    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x024, 0x80000000)
    ctrl_before_reset_completes = await machine.readl(ICOLL_BASE + 0x020)
    assert (ctrl_before_reset_completes & 0x80000000) != 0, (
        f"ICOLL SFTRST must remain asserted while reset is pending: ctrl=0x{ctrl_before_reset_completes:x}"
    )
    assert (ctrl_before_reset_completes & 0x40000000) == 0, (
        f"ICOLL CLKGATE must not assert before the reset delay elapses: ctrl=0x{ctrl_before_reset_completes:x}"
    )

    await machine.clock_step(125)
    assert ((await machine.readl(ICOLL_BASE + 0x020)) & 0x40000000) == 0, (
        "ICOLL CLKGATE must remain low before four reset clocks"
    )

    await machine.clock_step(42)
    ctrl_after_reset_completes = await machine.readl(ICOLL_BASE + 0x020)
    assert (ctrl_after_reset_completes & 0x40000000) != 0, (
        f"ICOLL CLKGATE must assert when soft reset completes: ctrl=0x{ctrl_after_reset_completes:x}"
    )
    assert await machine.readl(ICOLL_BASE + 0x1A0) == 0, "ICOLL soft reset must clear DEBUGFLAG state"


@pytest.mark.asyncio
async def test_icoll_bypass_fsm_contract(machine):
    """ICOLL bypass FSM contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x024, 0x00100000)
    await machine.writel(ICOLL_BASE + 0x160, 0x00005000)
    await machine.writel(ICOLL_BASE + 0x060, 0x00000800)

    first_vector = await machine.readl(ICOLL_BASE + 0x000)
    assert first_vector == 0x00005004, (
        f"ICOLL BYPASS_FSM should initially expose source 1: got 0x{first_vector:x}"
    )

    await machine.writel(ICOLL_BASE + 0x060, 0x00000008)
    bypass_vector = await machine.readl(ICOLL_BASE + 0x000)
    assert bypass_vector == 0x00005000, (
        f"ICOLL BYPASS_FSM must continuously update the vector without VECTOR acknowledgement: got 0x{bypass_vector:x}"
    )

    debug = await machine.readl(ICOLL_BASE + 0x170)
    assert (debug & 0x3FF) == 0, (
        f"ICOLL BYPASS_FSM must bypass the vector request FSM: debug=0x{debug:x}"
    )


@pytest.mark.asyncio
async def test_icoll_request_holding_contract(machine):
    """ICOLL request holding contract"""
    await machine.writel(ICOLL_BASE + 0x028, 0xC0000000)
    await machine.writel(ICOLL_BASE + 0x160, 0x00006000)

    assert await machine.readl(ICOLL_BASE + 0x040) == 0, (
        "ICOLL RAW0 should reset low before exercising its read-only aliases"
    )
    await machine.writel(ICOLL_BASE + 0x040, 0xFFFFFFFF)
    await machine.writel(ICOLL_BASE + 0x044, 0xFFFFFFFF)
    await machine.writel(ICOLL_BASE + 0x048, 0xFFFFFFFF)
    await machine.writel(ICOLL_BASE + 0x04C, 0xFFFFFFFF)
    assert await machine.readl(ICOLL_BASE + 0x040) == 0, (
        "ICOLL RAW0 and its aliases must not manufacture raw interrupt inputs"
    )

    await machine.writel(ICOLL_BASE + 0x060, 0x0000000C)
    assert await machine.readl(ICOLL_BASE + 0x1B0) == 0x00000001, (
        "ICOLL DBGREQUEST0 should capture the first software request"
    )

    await machine.writel(ICOLL_BASE + 0x068, 0x00000008)
    await machine.writel(ICOLL_BASE + 0x064, 0x00000C00)
    assert await machine.readl(ICOLL_BASE + 0x1B0) == 0x00000001, (
        "ICOLL DBGREQUEST0 must retain the closed holding-register snapshot until VECTOR acknowledgement"
    )

    await machine.clock_step(84)
    await machine.writel(ICOLL_BASE + 0x000, 0)
    assert await machine.readl(ICOLL_BASE + 0x1B0) == 0x00000002, (
        "ICOLL VECTOR acknowledgement must reopen the holding register for current requests"
    )

    await machine.writel(ICOLL_BASE + 0x010, 0x00000001)
    await machine.clock_step(84)
    assert await machine.readl(ICOLL_BASE + 0x000) == 0x00006004, (
        "ICOLL must service the newly sampled request after LEVELACK releases the prior level"
    )
