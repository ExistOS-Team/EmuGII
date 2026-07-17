import pytest

from framework.constants import PINCTRL_BASE


@pytest.mark.asyncio
async def test_pinctrl_ctrl(machine):
    """PINCTRL CTRL contract"""
    ctrl = await machine.readl(PINCTRL_BASE + 0x000)
    assert (ctrl & 0xFC00000F) == 0x1C000000, (
        "PINCTRL CTRL must have SFTRST/CLKGATE cleared by ROM boot init with PRESENT0/1/2 set"
    )
    assert (ctrl & (1 << 29)) == 0, "PINCTRL PRESENT3 must be 0 on STMP3770"

    await machine.writel(PINCTRL_BASE + 0x600, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x700, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x800, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x900, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0xA00, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x400, 0x00000001)

    ctrl_irq = await machine.readl(PINCTRL_BASE + 0x000)
    assert (ctrl_irq & 0xF) == 0x1, (
        "PINCTRL CTRL IRQOUT0 must reflect the active level-sensitive GPIO0 interrupt"
    )

    await machine.writel(PINCTRL_BASE + 0x000, 0xFFFFFFFF)
    ctrl_after = await machine.readl(PINCTRL_BASE + 0x000)
    assert (ctrl_after & 0xFC00000F) == 0xDC000000, (
        "PINCTRL CTRL must re-enter reset state (SFTRST/CLKGATE/PRESENT preserved, IRQOUT cleared)"
    )


@pytest.mark.asyncio
async def test_pinctrl_bank3_absent(machine):
    """PINCTRL Bank 3 absence"""
    ctrl = await machine.readl(PINCTRL_BASE + 0x000)
    before = await machine.readl(PINCTRL_BASE + 0x430)
    await machine.writel(PINCTRL_BASE + 0x430, 0xFFFFFFFF)
    after = await machine.readl(PINCTRL_BASE + 0x430)

    assert (ctrl & (1 << 29)) == 0, f"PINCTRL PRESENT3 should be 0 on STMP3770: ctrl=0x{ctrl:x}"
    assert before == 0, f"Bank 3 DOUT should reset to 0: before=0x{before:x}"
    assert after == 0, f"Bank 3 DOUT should remain inactive when GPIO is absent: after=0x{after:x}"


@pytest.mark.asyncio
async def test_pinctrl_drive_and_pull_masks(machine):
    """PINCTRL drive and pull masks"""
    assert await machine.readl(PINCTRL_BASE + 0x270) == 0x00044444, (
        "PINCTRL DRIVE7 must reset every documented voltage-select field high"
    )
    assert await machine.readl(PINCTRL_BASE + 0x200) == 0x44444444, (
        "PINCTRL DRIVE0 must reset every documented voltage-select field high"
    )
    assert await machine.readl(PINCTRL_BASE + 0x280) == 0x44444444, (
        "PINCTRL DRIVE8 must reset every documented voltage-select field high"
    )
    assert await machine.readl(PINCTRL_BASE + 0x2E0) == 0x00444444, (
        "PINCTRL DRIVE14 must reset every documented voltage-select field high"
    )
    assert await machine.readl(PINCTRL_BASE + 0x230) == 0x00444444, (
        "PINCTRL DRIVE3 must reset every documented voltage-select field high"
    )

    await machine.writel(PINCTRL_BASE + 0x270, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x270) == 0x00077777, (
        "PINCTRL DRIVE7 must expose only the Bank 1 pin 24-28 fields"
    )

    await machine.writel(PINCTRL_BASE + 0x280, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x280) == 0x77777777, (
        "PINCTRL DRIVE8 must keep every per-pin reserved bit clear"
    )

    await machine.writel(PINCTRL_BASE + 0x2E0, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x2E0) == 0x00777777, (
        "PINCTRL DRIVE14 must hide bits 31:24 and each reserved pad bit"
    )

    await machine.writel(PINCTRL_BASE + 0x230, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x230) == 0x00777777, (
        "PINCTRL DRIVE3 must hide bits 31:24 and each reserved pad bit"
    )

    await machine.writel(PINCTRL_BASE + 0x300, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x300) == 0x3C1000FE, (
        "PINCTRL PULL0 must retain only documented pullup-enable bits"
    )

    await machine.writel(PINCTRL_BASE + 0x310, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x310) == 0x0F400000, (
        "PINCTRL PULL1 must retain only documented pullup-enable bits"
    )

    await machine.writel(PINCTRL_BASE + 0x320, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x320) == 0x00004000, (
        "PINCTRL PULL2 must retain only the EMI_CE2N pullup-enable bit"
    )

    assert await machine.readl(PINCTRL_BASE + 0x330) == 0, (
        "PINCTRL PULL3 must reset to 0 (all pad keepers enabled)"
    )
    await machine.writel(PINCTRL_BASE + 0x330, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x330) == 0x0003FFFF, (
        "PINCTRL PULL3 must retain only bits 17:0 (pad-keeper disable bits)"
    )

    assert await machine.readl(PINCTRL_BASE + 0x304) == 0, (
        "PINCTRL PULL0_SET is write-only and must read back zero"
    )
    assert await machine.readl(PINCTRL_BASE + 0x278) == 0, (
        "PINCTRL DRIVE7_CLR is write-only and must read back zero"
    )


@pytest.mark.asyncio
async def test_pinctrl_muxsel_default_and_mask(machine):
    """PINCTRL MUXSEL default and reserved mask"""
    assert await machine.readl(PINCTRL_BASE + 0x100) == 0xFFFFFFFF, (
        "PINCTRL MUXSEL0 must reset to GPIO for all 16 pins"
    )
    assert await machine.readl(PINCTRL_BASE + 0x110) == 0x0FFFFFFF, (
        "PINCTRL MUXSEL1 must reset to GPIO for pins 16-29"
    )
    assert await machine.readl(PINCTRL_BASE + 0x120) == 0xFFFFFFFF, (
        "PINCTRL MUXSEL2 must reset to GPIO for all 16 pins"
    )
    assert await machine.readl(PINCTRL_BASE + 0x130) == 0x03FFFFFF, (
        "PINCTRL MUXSEL3 must reset to GPIO for pins 16-28"
    )
    assert await machine.readl(PINCTRL_BASE + 0x140) == 0xFFFFFFFF, (
        "PINCTRL MUXSEL4 must reset to GPIO for all 16 pins"
    )
    assert await machine.readl(PINCTRL_BASE + 0x150) == 0xFFFFFFFF, (
        "PINCTRL MUXSEL5 must reset to GPIO for all 16 pins"
    )
    assert await machine.readl(PINCTRL_BASE + 0x160) == 0xFFFFFFFF, (
        "PINCTRL MUXSEL6 must reset to GPIO for all 16 pins"
    )
    assert await machine.readl(PINCTRL_BASE + 0x170) == 0x00000FFF, (
        "PINCTRL MUXSEL7 must reset to GPIO for pins 16-21"
    )

    await machine.writel(PINCTRL_BASE + 0x110, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x110) == 0x0FFFFFFF, (
        "PINCTRL MUXSEL1 must preserve reserved bits 31:28"
    )

    await machine.writel(PINCTRL_BASE + 0x130, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x130) == 0x03FFFFFF, (
        "PINCTRL MUXSEL3 must preserve reserved bits 31:26"
    )

    await machine.writel(PINCTRL_BASE + 0x170, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x170) == 0x00000FFF, (
        "PINCTRL MUXSEL7 must preserve reserved bits 31:12"
    )

    await machine.writel(PINCTRL_BASE + 0x100, 0xFFFFFFFF)
    assert await machine.readl(PINCTRL_BASE + 0x100) == 0xFFFFFFFF, (
        "PINCTRL MUXSEL0 must accept all bits"
    )


@pytest.mark.asyncio
async def test_pinctrl_gpio_irqstat_contract(machine):
    """PINCTRL GPIO IRQSTAT edge/level contract"""
    await machine.writel(PINCTRL_BASE + 0x600, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x700, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x800, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x900, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0xA00, 0x00000001)

    await machine.writel(PINCTRL_BASE + 0x400, 0x00000001)
    assert (await machine.readl(PINCTRL_BASE + 0xB00) & 0x1) == 0x1, (
        "PINCTRL IRQSTAT level-sensitive must set when active high input is asserted"
    )

    await machine.writel(PINCTRL_BASE + 0xB08, 0x00000001)
    assert (await machine.readl(PINCTRL_BASE + 0xB00) & 0x1) == 0x1, (
        "PINCTRL IRQSTAT level-sensitive must remain set while input stays active"
    )

    await machine.writel(PINCTRL_BASE + 0x400, 0x00000000)
    assert (await machine.readl(PINCTRL_BASE + 0xB00) & 0x1) == 0x0, (
        "PINCTRL IRQSTAT level-sensitive must clear when input returns inactive"
    )

    await machine.writel(PINCTRL_BASE + 0x900, 0x00000000)
    await machine.writel(PINCTRL_BASE + 0xB08, 0x00000001)
    await machine.writel(PINCTRL_BASE + 0x400, 0x00000001)
    assert (await machine.readl(PINCTRL_BASE + 0xB00) & 0x1) == 0x1, (
        "PINCTRL IRQSTAT edge-sensitive must set on active high rising edge"
    )

    await machine.writel(PINCTRL_BASE + 0x400, 0x00000000)
    assert (await machine.readl(PINCTRL_BASE + 0xB00) & 0x1) == 0x1, (
        "PINCTRL IRQSTAT edge-sensitive must remain latched after input deasserts"
    )

    await machine.writel(PINCTRL_BASE + 0xB08, 0x00000001)
    assert (await machine.readl(PINCTRL_BASE + 0xB00) & 0x1) == 0x0, (
        "PINCTRL IRQSTAT edge-sensitive must clear on software clear"
    )
