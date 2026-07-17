import pytest

from framework.constants import LRADC_BASE, PINCTRL_BASE, PWM_BASE


@pytest.mark.asyncio
async def test_pwm_register_contract(machine):
    """PWM register contract"""
    assert await machine.readl(PWM_BASE + 0x000) == 0xFE000000, (
        "PWM CTRL reset must retain SFTRST, CLKGATE, and five present bits"
    )
    assert await machine.readl(PWM_BASE + 0x0B0) == 0x01010000, (
        "PWM VERSION must be v1.1 at the documented offset"
    )

    await machine.writel(PWM_BASE + 0x000, 0x0000003F)
    assert await machine.readl(PWM_BASE + 0x000) == 0x3E00003F, (
        "PWM CTRL must preserve present bits and only store documented writable bits"
    )
    await machine.writel(PWM_BASE + 0x008, 0x0000003F)
    assert await machine.readl(PWM_BASE + 0x000) == 0x3E000000, (
        "PWM CTRL_CLR must only clear documented channel enable bits"
    )
    await machine.writel(PWM_BASE + 0x000, 0x80000000)
    assert await machine.readl(PWM_BASE + 0x000) == 0xFE000000, (
        "PWM SFTRST must reset the block and automatically gate its clock"
    )

    for channel in range(5):
        active_offset = 0x010 + channel * 0x020
        period_offset = 0x020 + channel * 0x020
        active = (0x10203040 + channel) & 0xFFFFFFFF
        period = (0xFF234567 + channel) & 0xFFFFFFFF

        await machine.writel(PWM_BASE + active_offset, active)
        await machine.writel(PWM_BASE + period_offset, period)
        assert await machine.readl(PWM_BASE + active_offset) == active, (
            f"PWM ACTIVE{channel} must use its documented register offset"
        )
        assert await machine.readl(PWM_BASE + period_offset) == (period & 0x00FFFFFF), (
            f"PWM PERIOD{channel} must ignore reserved bits 31:24 at its documented register offset"
        )

        await machine.writel(PWM_BASE + active_offset + 0x004, 0x00000003)
        await machine.writel(PWM_BASE + active_offset + 0x008, 0x00000001)
        await machine.writel(PWM_BASE + active_offset + 0x00C, 0x00000006)
        assert await machine.readl(PWM_BASE + active_offset) == (
            ((active | 0x00000003) & ~0x00000001) ^ 0x00000006
        ), (
            f"PWM ACTIVE{channel} SET/CLR/TOG aliases must update the documented register"
        )

        await machine.writel(PWM_BASE + period_offset + 0x004, 0x00000003)
        await machine.writel(PWM_BASE + period_offset + 0x008, 0x00000001)
        await machine.writel(PWM_BASE + period_offset + 0x00C, 0x00000006)
        assert await machine.readl(PWM_BASE + period_offset) == (
            ((((period & 0x00FFFFFF) | 0x00000003) & ~0x00000001) ^ 0x00000006)
            & 0x00FFFFFF
        ), (
            f"PWM PERIOD{channel} SET/CLR/TOG aliases must preserve reserved bits"
        )

    assert await machine.readl(PWM_BASE + 0x100) == 0, (
        "PWM must not expose the obsolete synthetic PERIOD register map"
    )


@pytest.mark.asyncio
async def test_pwm_waveform_contract(machine):
    """PWM waveform contract"""
    pwm0_period = 0x004B0003

    await machine.writel(PINCTRL_BASE + 0x140, 0)
    await machine.writel(PWM_BASE + 0x008, 0xC0000000)
    await machine.writel(PWM_BASE + 0x010, 0x00010000)
    await machine.writel(PWM_BASE + 0x020, pwm0_period)
    await machine.writel(PWM_BASE + 0x004, 0x00000001)

    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) != 0, (
        "PWM0 active state must drive Bank 2 Pin 0 when muxed to PWM0 and enabled"
    )
    await machine.clock_step(1_400)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) == 0, (
        "PWM0 must enter its programmed inactive state after the ACTIVE.INACTIVE count"
    )

    await machine.writel(PWM_BASE + 0x010, 0x00000000)
    await machine.writel(PWM_BASE + 0x020, pwm0_period)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) == 0, (
        "PWM0 ACTIVE/PERIOD rewrite must not take effect in the middle of a period"
    )
    await machine.clock_step(700)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) == 0, (
        "PWM0 staged parameters must remain pending until the next period boundary"
    )
    await machine.clock_step(700)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) != 0, (
        "PWM0 staged ACTIVE/PERIOD parameters must commit at the next period boundary"
    )

    await machine.writel(PWM_BASE + 0x004, 0x40000000)
    await machine.clock_step(1_400)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) != 0, (
        "PWM CLKGATE must freeze the currently driven output state"
    )
    await machine.writel(PWM_BASE + 0x008, 0x40000000)
    await machine.clock_step(700)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) == 0, (
        "PWM must resume its preserved phase after CLKGATE is cleared"
    )

    await machine.writel(PWM_BASE + 0x004, 0x80000000)
    assert await machine.readl(PWM_BASE + 0x000) == 0xFE000000, (
        "PWM SFTRST must reset the block and automatically gate its clock"
    )
    assert await machine.readl(PWM_BASE + 0x010) == 0, (
        "PWM SFTRST must clear staged ACTIVE state"
    )


@pytest.mark.asyncio
async def test_pwm_matt_contract(machine):
    """PWM MATT contract"""
    await machine.writel(PINCTRL_BASE + 0x140, 0)
    await machine.writel(PWM_BASE + 0x008, 0xC0000000)
    await machine.writel(PWM_BASE + 0x010, 0xFFFFFFFF)
    await machine.writel(PWM_BASE + 0x020, 0x00800000)
    await machine.writel(PWM_BASE + 0x004, 0x00000001)

    initial = (await machine.readl(PINCTRL_BASE + 0x520)) & 0x1
    await machine.clock_step(22)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) != initial, (
        "PWM MATT must route the 24 MHz crystal independently of ACTIVE and PERIOD fields"
    )
    await machine.clock_step(22)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x1) == initial, (
        "PWM MATT must return to the prior state after a 24 MHz clock period"
    )


@pytest.mark.asyncio
async def test_pwm2_analog_enable_contract(machine):
    """PWM2 analog enable contract"""
    await machine.writel(PINCTRL_BASE + 0x140, 0)
    await machine.writel(PWM_BASE + 0x008, 0xC0000000)
    await machine.writel(PWM_BASE + 0x050, 0xFFFFFFFF)
    await machine.writel(PWM_BASE + 0x060, 0x000F0003)
    await machine.writel(PWM_BASE + 0x004, 0x00000024)

    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x4) == 0, (
        "PWM2 analog path must disable PWM2 while LRADC BL_ENABLE is clear"
    )
    await machine.writel(LRADC_BASE + 0x024, 0x00400000)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x4) != 0, (
        "PWM2 analog path must enable PWM2 when LRADC BL_ENABLE is set"
    )
    await machine.writel(LRADC_BASE + 0x028, 0x00400000)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x4) == 0, (
        "clearing LRADC BL_ENABLE must disable PWM2 through the analog path"
    )
    await machine.writel(PWM_BASE + 0x008, 0x00000020)
    assert ((await machine.readl(PINCTRL_BASE + 0x520)) & 0x4) != 0, (
        "clearing PWM2_ANA_CTRL_ENABLE must restore ordinary PWM2 behavior"
    )
