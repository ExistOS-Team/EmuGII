import pytest

from framework.constants import ICOLL_BASE, LRADC_BASE


@pytest.mark.asyncio
async def test_lradc_register_contract(machine):
    """LRADC register contract"""
    ctrl0 = await machine.readl(LRADC_BASE + 0x000)
    assert ctrl0 == 0xC0000000, f"LRADC CTRL0 must reset with SFTRST/CLKGATE"

    ctrl2 = await machine.readl(LRADC_BASE + 0x020)
    assert ctrl2 == 0x00008000, f"LRADC CTRL2 must reset with TEMPSENSE_PWD asserted"

    await machine.writel(LRADC_BASE + 0x010, 0xFFFFFFFF)
    assert (await machine.readl(LRADC_BASE + 0x010)) == 0x01FF01FF, f"LRADC CTRL1 must mask reserved bits 31:25 and 15:9"

    await machine.writel(LRADC_BASE + 0x020, 0xFFFFFFFF)
    assert (await machine.readl(LRADC_BASE + 0x020)) == 0xFFFFB3FF, f"LRADC CTRL2 must mask reserved bits 14 and 11:10"

    await machine.writel(LRADC_BASE + 0x030, 0xFFFFFFFF)
    assert (await machine.readl(LRADC_BASE + 0x030)) == 0x03C00333, f"LRADC CTRL3 must mask reserved bits 31:26, 21:14, 13:10, 7:6, 3:2"

    await machine.writel(LRADC_BASE + 0x130, 0xFFFFFFFF)
    assert (await machine.readl(LRADC_BASE + 0x130)) == 0x001303FF, f"LRADC CONVERSION must mask reserved bits 31:21, 19:18, 15:10"

    assert ((await machine.readl(LRADC_BASE + 0x0C0)) & 0x3FFFF) == 2748, f"LRADC CH7 VALUE must reset to 2748 (disconnected battery)"

    await machine.writel(LRADC_BASE + 0x050, 0xFFFFFFFF)
    assert (await machine.readl(LRADC_BASE + 0x050)) == 0xBF03FFFF, f"LRADC CH0 must mask reserved bits 30 and 23:18"

    await machine.writel(LRADC_BASE + 0x0C0, 0xFFFFFFFF)
    assert ((await machine.readl(LRADC_BASE + 0x0C0)) & 0x3FFFF) == 0x3FFFF, f"LRADC CH7 VALUE must be writable (software value semantics)"

    await machine.writel(LRADC_BASE + 0x000, 0x80000000)
    assert (await machine.readl(LRADC_BASE + 0x000)) == 0xC0000000, f"LRADC SFTRST must gate clock and remain asserted"
    assert (await machine.readl(LRADC_BASE + 0x010)) == 0, f"LRADC SFTRST must clear CTRL1"
    assert (await machine.readl(LRADC_BASE + 0x020)) == 0x00008000, f"LRADC SFTRST must restore CTRL2 TEMPSENSE_PWD"
    assert ((await machine.readl(LRADC_BASE + 0x0C0)) & 0x3FFFF) == 2748, f"LRADC SFTRST must restore CH7 default value"


@pytest.mark.asyncio
async def test_lradc_irq_contract(machine):
    """LRADC IRQ contract"""
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)
    await machine.writel(LRADC_BASE + 0x010, 0x00810081)

    await machine.writel(LRADC_BASE + 0x000, 0x00000081)

    ctrl1 = await machine.readl(LRADC_BASE + 0x010)
    assert (ctrl1 & 0x0001) != 0, f"LRADC0 IRQ status must be set after schedule"
    assert (ctrl1 & 0x0080) != 0, f"LRADC7 IRQ status must be set after schedule"

    raw1 = await machine.readl(ICOLL_BASE + 0x050)
    assert (raw1 & (1 << 5)) != 0, f"LRADC0 must assert ICOLL source 37"
    assert (raw1 & (1 << 12)) != 0, f"LRADC7 must assert ICOLL source 44"

    await machine.writel(LRADC_BASE + 0x018, 0x00810081)
    assert (await machine.readl(LRADC_BASE + 0x010)) == 0, f"LRADC0/7 IRQ status must clear after CLR write"
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & ((1 << 5) | (1 << 12))) == 0, f"LRADC0/7 ICOLL sources must deassert when IRQ cleared"

    await machine.writel(LRADC_BASE + 0x014, 0x01000000)
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 4)) == 0, f"TOUCH_DETECT_IRQ must not assert when status is clear"

    await machine.writel(LRADC_BASE + 0x014, 0x00000100)
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 4)) != 0, f"TOUCH_DETECT_IRQ must assert when status is set and enabled"

    await machine.writel(LRADC_BASE + 0x018, 0x01000100)


@pytest.mark.asyncio
async def test_lradc_scheduler_contract(machine):
    """LRADC scheduler contract"""
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)
    await machine.writel(LRADC_BASE + 0x010, 0x00030000)

    await machine.writel(LRADC_BASE + 0x050, 0x23000000)

    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0001) == 0, f"LRADC0 IRQ must not assert after first accumulated sample"
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 value must be 0xabc after first accumulated sample"

    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0001) != 0, f"LRADC0 IRQ must assert after third accumulated sample"
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x2034, f"CH0 value must be 0x2034 after three accumulated samples"

    await machine.writel(LRADC_BASE + 0x018, 0x00010001)
    await machine.writel(LRADC_BASE + 0x050, 0x00000000)

    await machine.writel(LRADC_BASE + 0x0D0, 0x01100005)
    await machine.clock_step(5 * 500_000)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 value must be 0xabc after DELAY0 triggers CH0"
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0001) != 0, f"LRADC0 IRQ must assert after DELAY0 triggers CH0"

    await machine.writel(LRADC_BASE + 0x018, 0x00010001)

    await machine.writel(LRADC_BASE + 0x0D0, 0x01100805)
    await machine.clock_step(5 * 500_000)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 value must be 0xabc after first DELAY0 loop iteration"
    await machine.clock_step(5 * 500_000)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 value must be 0xabc after second DELAY0 loop iteration"
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0001) != 0, f"LRADC0 IRQ must assert after second DELAY0 loop iteration"

    await machine.writel(LRADC_BASE + 0x0D0, 0x01120005)
    await machine.writel(LRADC_BASE + 0x0E0, 0x02000005)
    await machine.clock_step(10 * 500_000)
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0002) != 0, f"LRADC1 IRQ must assert after DELAY1 is triggered by DELAY0"
    assert ((await machine.readl(LRADC_BASE + 0x060)) & 0x3FFFF) == 0xABC, f"CH1 value must be 0xabc after DELAY1 triggers CH1"


@pytest.mark.asyncio
async def test_lradc_touch_temperature_contract(machine):
    """LRADC touch/temperature contract"""
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0000, f"LRADC STATUS must report touch panel and all channels present"

    await machine.writel(LRADC_BASE + 0x000, 0x00100000)
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0000, f"TOUCH_DETECT_RAW must be 0 when no touch is active"

    await machine.writel(LRADC_BASE + 0x010, 0x01000100)
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 4)) != 0, f"TOUCH_DETECT_IRQ must assert ICOLL source 36"

    await machine.writel(LRADC_BASE + 0x018, 0x01000100)
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 4)) == 0, f"TOUCH_DETECT_IRQ must deassert when cleared"

    await machine.writel(LRADC_BASE + 0x010, 0x01000000)
    await machine.set_irq_in('/machine/soc/lradc', 'touch-detect', 0, 1)
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0001, f"TOUCH_DETECT_RAW must be 1 when touch-detect input is active and enabled"
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0100) != 0, f"TOUCH_DETECT_IRQ status must be set by the touch-detect input"
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 4)) != 0, f"TOUCH_DETECT_IRQ must assert ICOLL source 36 when touch-detect input is active"

    await machine.set_irq_in('/machine/soc/lradc', 'touch-detect', 0, 0)
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0000, f"TOUCH_DETECT_RAW must return to 0 when touch-detect input is released"
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0100) != 0, f"TOUCH_DETECT_IRQ status must remain sticky when touch-detect input is released"

    await machine.writel(LRADC_BASE + 0x018, 0x00000100)
    assert ((await machine.readl(LRADC_BASE + 0x010)) & 0x0100) == 0, f"TOUCH_DETECT_IRQ status must clear when input is released and software clears it"
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 4)) == 0, f"TOUCH_DETECT_IRQ must deassert when status is cleared"

    await machine.writel(LRADC_BASE + 0x140, 0x76543218)
    await machine.writel(LRADC_BASE + 0x020, 0x00000000)
    await machine.writel(LRADC_BASE + 0x010, 0x00010001)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x400, f"CH0 mapped to physical 8 with TEMPSENSE enabled must be 0x400"

    await machine.writel(LRADC_BASE + 0x018, 0x00010001)
    await machine.writel(LRADC_BASE + 0x140, 0x76543219)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x800, f"CH0 mapped to physical 9 with TEMPSENSE enabled must be 0x800"

    await machine.writel(LRADC_BASE + 0x018, 0x00010001)
    await machine.writel(LRADC_BASE + 0x020, 0x00008000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"CH0 mapped to physical 9 with TEMPSENSE powered down must be 0"

    await machine.writel(LRADC_BASE + 0x018, 0x00010001)
    await machine.writel(LRADC_BASE + 0x140, 0x76543210)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 mapped to physical 0 must be 0xabc"


@pytest.mark.asyncio
async def test_lradc_divide_by_two_contract(machine):
    """LRADC divide-by-two contract"""
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)

    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 physical 0 must be 0xabc without divide-by-two"

    await machine.writel(LRADC_BASE + 0x020, 0x01000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x55E, f"CH0 physical 0 must be halved to 0x55e when DIVIDE_BY_TWO is set"

    await machine.writel(LRADC_BASE + 0x140, 0x76543218)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x200, f"CH0 physical 8 must be 0x200 with DIVIDE_BY_TWO and TEMPSENSE enabled"

    await machine.writel(LRADC_BASE + 0x140, 0x76543219)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x400, f"CH0 physical 9 must be 0x400 with DIVIDE_BY_TWO and TEMPSENSE enabled"

    await machine.writel(LRADC_BASE + 0x020, 0x01008000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"CH0 physical 9 must read 0 when TEMPSENSE_PWD is set even with DIVIDE_BY_TWO"


@pytest.mark.asyncio
async def test_lradc_temp_current_contract(machine):
    """LRADC temperature current source contract"""
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)

    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 physical 0 must be 0xabc when TEMP_SENSOR_IENABLE0 is disabled"

    await machine.writel(LRADC_BASE + 0x020, 0x0000010F)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xF00, f"CH0 physical 0 must be 0xf00 when TEMP_SENSOR_IENABLE0 is enabled with ISRC=0xF"

    await machine.writel(LRADC_BASE + 0x020, 0x00000108)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x800, f"CH0 physical 0 must be 0x800 when TEMP_SENSOR_IENABLE0 is enabled with ISRC=0x8"

    await machine.writel(LRADC_BASE + 0x020, 0x00000100)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"CH0 physical 0 must read 0 when TEMP_SENSOR_IENABLE0 is enabled with ISRC=0"

    await machine.writel(LRADC_BASE + 0x020, 0x00000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 physical 0 must return to 0xabc when TEMP_SENSOR_IENABLE0 is disabled"

    await machine.writel(LRADC_BASE + 0x140, 0x76543211)
    await machine.writel(LRADC_BASE + 0x020, 0x00000240)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x400, f"CH0 physical 1 must be 0x400 when TEMP_SENSOR_IENABLE1 is enabled with ISRC=0x4"

    await machine.writel(LRADC_BASE + 0x140, 0x76543210)
    await machine.writel(LRADC_BASE + 0x020, 0x0100010F)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0x780, f"CH0 physical 0 with ISRC=0xF and DIVIDE_BY_TWO must be halved to 0x780"


@pytest.mark.asyncio
async def test_lradc_ctrl3_power_and_discard_contract(machine):
    """LRADC CTRL3 power and discard contract"""
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)

    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"CH0 must read 0xabc when analog is powered normally"

    await machine.writel(LRADC_BASE + 0x030, 0x00400000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"FORCE_ANALOG_PWDN must force LRADC conversion to 0"

    await machine.writel(LRADC_BASE + 0x030, 0x00C00000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"FORCE_ANALOG_PWUP must override PWDN and restore 0xabc"

    await machine.writel(LRADC_BASE + 0x038, 0x00C00000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"clearing force bits must restore normal 0xabc"

    await machine.writel(LRADC_BASE + 0x030, 0x01000000)
    await machine.writel(LRADC_BASE + 0x000, 0x40000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"DISCARD=1 first sample after power-up must be discarded"
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"DISCARD=1 second sample after power-up must be 0xabc"

    await machine.writel(LRADC_BASE + 0x030, 0x02000000)
    await machine.writel(LRADC_BASE + 0x000, 0x40000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"DISCARD=2 first sample must be discarded"
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"DISCARD=2 second sample must be discarded"
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"DISCARD=2 third sample must be 0xabc"

    await machine.writel(LRADC_BASE + 0x030, 0x03000000)
    await machine.writel(LRADC_BASE + 0x000, 0x40000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000000)
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"DISCARD=3 first sample must be discarded"
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"DISCARD=3 second sample must be discarded"
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0, f"DISCARD=3 third sample must be discarded"
    await machine.writel(LRADC_BASE + 0x000, 0x00000001)
    assert ((await machine.readl(LRADC_BASE + 0x050)) & 0x3FFFF) == 0xABC, f"DISCARD=3 fourth sample must be 0xabc"


@pytest.mark.asyncio
async def test_lradc_status_and_ctrl3_clock_contract(machine):
    """LRADC STATUS and CTRL3 clock contract"""
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0000, f"LRADC STATUS must report all channels, touch and temperature sources present"

    await machine.set_irq_in('/machine/soc/lradc', 'touch-detect', 0, 1)
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0000, f"TOUCH_DETECT_RAW must stay 0 when TOUCH_DETECT_ENABLE is not set"

    await machine.writel(LRADC_BASE + 0x000, 0x00100000)
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0001, f"TOUCH_DETECT_RAW must follow touch-detect input when enabled by CTRL0"

    await machine.writel(LRADC_BASE + 0x000, 0x00000000)
    assert (await machine.readl(LRADC_BASE + 0x040)) == 0x07FF0000, f"TOUCH_DETECT_RAW must be gated off when TOUCH_DETECT_ENABLE is cleared"

    await machine.set_irq_in('/machine/soc/lradc', 'touch-detect', 0, 0)

    await machine.writel(LRADC_BASE + 0x030, 0x03000000)
    assert (await machine.readl(LRADC_BASE + 0x030)) == 0x03000000, f"CTRL3 CYCLE_TIME=0x3 and DISCARD=0x3 must be readable"

    await machine.writel(LRADC_BASE + 0x030, 0x00000033)
    assert (await machine.readl(LRADC_BASE + 0x030)) == 0x00000033, f"CTRL3 HIGH_TIME/DELAY_CLOCK/INVERT_CLOCK must be readable"

    await machine.writel(LRADC_BASE + 0x030, 0x00000000)
