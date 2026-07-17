import pytest

from framework.constants import PWM_BASE, TIMROT_BASE


@pytest.mark.asyncio
async def test_timrot_tick_and_update_contract(machine):
    """TIMROT tick and update contract"""
    await machine.writel(TIMROT_BASE + 0x008, 0xC0000000)

    await machine.writel(TIMROT_BASE + 0x020, 0x000000CF)
    await machine.writel(TIMROT_BASE + 0x030, 10)
    await machine.clock_step(1_000)
    assert ((await machine.readl(TIMROT_BASE + 0x020)) & 0x8000) != 0, (
        "TIMROT SELECT=0xF must use undefined-select always-tick behavior"
    )

    await machine.writel(TIMROT_BASE + 0x028, 0x00008000)
    await machine.writel(TIMROT_BASE + 0x020, 0x0000004C)
    await machine.writel(TIMROT_BASE + 0x030, 1_000)
    await machine.clock_step(10_000)
    running_before_update = (await machine.readl(TIMROT_BASE + 0x030)) >> 16

    await machine.writel(TIMROT_BASE + 0x024, 0x00000080)
    await machine.clock_step(1_000)
    running_after_update = (await machine.readl(TIMROT_BASE + 0x030)) >> 16

    assert running_after_update < running_before_update, (
        f"TIMROT UPDATE alone must not reload running count: before={running_before_update}, after={running_after_update}"
    )


@pytest.mark.asyncio
async def test_timrot_external_edge_contract(machine):
    """TIMROT external edge contract"""
    pwm0_active = 0x00010000
    pwm0_period = 0x004B0003

    await machine.writel(TIMROT_BASE + 0x008, 0xC0000000)

    await machine.writel(TIMROT_BASE + 0x020, 0x00000081)
    await machine.writel(TIMROT_BASE + 0x030, 1)
    await machine.writel(TIMROT_BASE + 0x040, 0x00000181)
    await machine.writel(TIMROT_BASE + 0x050, 1)

    await machine.writel(PWM_BASE + 0x008, 0xC0000000)
    await machine.writel(PWM_BASE + 0x010, pwm0_active)
    await machine.writel(PWM_BASE + 0x020, pwm0_period)
    await machine.writel(PWM_BASE + 0x004, 0x00000001)

    assert ((await machine.readl(TIMROT_BASE + 0x020)) & 0x8000) != 0, (
        "TIMROT POLARITY=0 must decrement a PWM-selected timer on PWM rising edges"
    )
    assert ((await machine.readl(TIMROT_BASE + 0x040)) & 0x8000) == 0, (
        "TIMROT POLARITY=1 must not decrement a PWM-selected timer on PWM rising edges"
    )

    await machine.clock_step(1_400)
    assert ((await machine.readl(TIMROT_BASE + 0x040)) & 0x8000) != 0, (
        "TIMROT POLARITY=1 must decrement a PWM-selected timer on PWM falling edges"
    )


@pytest.mark.asyncio
async def test_timrot_duty_cycle_contract(machine):
    """TIMROT duty-cycle contract"""
    await machine.writel(TIMROT_BASE + 0x008, 0xC0000000)
    await machine.writel(TIMROT_BASE + 0x080, 0x0002020C)
    assert await machine.readl(TIMROT_BASE + 0x080) == 0x0002020C, (
        "TIMROT Timer3 control must decode at its documented 0x80 offset"
    )

    await machine.writel(PWM_BASE + 0x008, 0xC0000000)
    await machine.writel(PWM_BASE + 0x030, 0x00010000)
    await machine.writel(PWM_BASE + 0x040, 0x000B0003)
    await machine.writel(PWM_BASE + 0x004, 0x00000002)

    await machine.clock_step(1_000)

    duty_ctrl = await machine.readl(TIMROT_BASE + 0x080)
    duty_count = await machine.readl(TIMROT_BASE + 0x090)

    assert (duty_ctrl & 0x00000400) != 0, (
        f"TIMROT Timer3 must set DUTY_VALID after sampling PWM1 high and low intervals: ctrl=0x{duty_ctrl:x}, count=0x{duty_count:x}"
    )
    assert (duty_count >> 16) != 0, (
        "TIMROT Timer3 duty mode must latch a nonzero low interval on PWM1 rising edge"
    )
    assert (duty_count & 0xFFFF) != 0, (
        "TIMROT Timer3 duty mode must latch a nonzero high interval on PWM1 falling edge"
    )

    await machine.writel(TIMROT_BASE + 0x080, 0x0002020C)
    assert ((await machine.readl(TIMROT_BASE + 0x080)) & 0x00000400) == 0, (
        "TIMROT Timer3 control writes must clear DUTY_VALID while duty mode remains enabled"
    )

    await machine.writel(TIMROT_BASE + 0x088, 0x00000200)
    assert ((await machine.readl(TIMROT_BASE + 0x080)) & 0x00000400) == 0, (
        "TIMROT Timer3 must clear DUTY_VALID when duty-cycle mode is disabled"
    )


@pytest.mark.asyncio
async def test_timrot_rotary_contract(machine):
    """TIMROT rotary contract"""
    pwm_active = 0x27100000
    pwm_period = 0x000B4E20

    await machine.writel(TIMROT_BASE + 0x000, 0x00000C32)
    await machine.writel(PWM_BASE + 0x008, 0xC0000000)
    await machine.writel(PWM_BASE + 0x030, pwm_active)
    await machine.writel(PWM_BASE + 0x040, pwm_period)
    await machine.writel(PWM_BASE + 0x050, pwm_active)
    await machine.writel(PWM_BASE + 0x060, pwm_period)

    await machine.writel(PWM_BASE + 0x004, 0x00000002)
    await machine.clock_step(208_000)
    await machine.writel(PWM_BASE + 0x004, 0x00000004)
    await machine.clock_step(5_000_000)

    absolute_count = await machine.readl(TIMROT_BASE + 0x010)
    assert (absolute_count >> 16) == 0, (
        "TIMROT ROTCOUNT must keep its reserved upper half clear"
    )
    assert (absolute_count & 0xFFFF) != 0, (
        "TIMROT rotary decoder must count legal PWM1/PWM2 quadrature transitions"
    )

    await machine.writel(TIMROT_BASE + 0x004, 0x00001000)
    relative_count = await machine.readl(TIMROT_BASE + 0x010)
    assert (relative_count & 0xFFFF) != 0, (
        "TIMROT relative ROTCOUNT read must report the accumulated signed count"
    )
    assert await machine.readl(TIMROT_BASE + 0x010) == 0, (
        "TIMROT relative ROTCOUNT read must clear the counter as a side effect"
    )


@pytest.mark.asyncio
async def test_timrot_rotary_invalid_transition_contract(machine):
    """TIMROT rotary invalid transition contract"""
    pwm_active = 0x27100000
    pwm_period = 0x000B4E20

    await machine.writel(TIMROT_BASE + 0x000, 0x00000C32)
    await machine.writel(PWM_BASE + 0x008, 0xC0000000)
    await machine.writel(PWM_BASE + 0x030, pwm_active)
    await machine.writel(PWM_BASE + 0x040, pwm_period)
    await machine.writel(PWM_BASE + 0x050, pwm_active)
    await machine.writel(PWM_BASE + 0x060, pwm_period)

    await machine.writel(PWM_BASE + 0x004, 0x00000006)
    await machine.clock_step(2_000_000)

    assert await machine.readl(TIMROT_BASE + 0x010) == 0, (
        "TIMROT rotary decoder must ignore invalid direct BA=00 to BA=11 transitions"
    )
