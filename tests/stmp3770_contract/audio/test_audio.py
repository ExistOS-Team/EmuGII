import pytest

from framework.constants import APBX_BASE, AUDIOADC_BASE, AUDIODAC_BASE, ICOLL_BASE
from helpers.dma import write_descriptor


@pytest.mark.asyncio
async def test_audioout_register_contract(machine):
    """AUDIOOUT register contract"""
    resets = [
        [0x000, 0xC0000000, "CTRL"],
        [0x010, 0x80000000, "STAT"],
        [0x020, 0x10110037, "DACSRR"],
        [0x030, 0x01FE01FE, "DACVOLUME"],
        [0x040, 0x00000001, "DACDEBUG"],
        [0x050, 0x01000C0C, "HPVOL"],
        [0x060, 0x00000000, "RESERVED"],
        [0x070, 0x01001111, "PWRDN"],
        [0x080, 0x00000000, "REFCTRL"],
        [0x090, 0x00000000, "ANACTRL"],
        [0x0A0, 0x00000000, "TEST"],
        [0x0B0, 0x00000000, "BISTCTRL"],
        [0x0E0, 0x80000000, "ANACLKCTRL"],
        [0x100, 0x01404808, "LINEOUTCTRL"],
        [0x200, 0x01010000, "VERSION"],
    ]
    for offset, value, name in resets:
        assert (await machine.readl(AUDIODAC_BASE + offset)) == value, (
            f"AUDIOOUT {name} must have its documented reset value"
        )
    assert (await machine.readl(AUDIODAC_BASE + 0x004)) == 0, (
        "AUDIOOUT CTRL_SET must read as zero (SCT alias contract)"
    )
    assert (await machine.readl(AUDIODAC_BASE + 0x204)) == 0, (
        "AUDIOOUT VERSION must not respond on an undeclared alias"
    )

    masks = [
        [0x000, 0x3FFFFFFF, 0x001F7733, "CTRL"],
        [0x020, 0xFFFFFFFF, 0xF71F1FFF, "DACSRR"],
        [0x030, 0xFFFFFFFF, 0x03FF01FF, "DACVOLUME"],
        [0x040, 0xFFFFFFFF, 0x80000F01, "DACDEBUG"],
        [0x050, 0xFFFFFFFF, 0x03017F7F, "HPVOL"],
        [0x070, 0xFFFFFFFF, 0x01111111, "PWRDN"],
        [0x080, 0xFFFFFFFF, 0x07FF7FF7, "REFCTRL"],
        [0x090, 0xFFFFFFFF, 0x11367730, "ANACTRL"],
        [0x0A0, 0xFFFFFFFF, 0x77F03007, "TEST"],
        [0x0E0, 0xFFFFFFFF, 0x80000017, "ANACLKCTRL"],
        [0x100, 0xFFFFFFFF, 0x03FFFF1F, "LINEOUTCTRL"],
    ]
    for offset, inp, value, name in masks:
        await machine.writel(AUDIODAC_BASE + offset, inp)
        assert (await machine.readl(AUDIODAC_BASE + offset)) == value, (
            f"AUDIOOUT {name} must mask reserved bits read-only"
        )
    await machine.writel(AUDIODAC_BASE + 0x010, 0)
    assert (await machine.readl(AUDIODAC_BASE + 0x010)) == 0x80000000, (
        "AUDIOOUT STAT must ignore writes (read-only)"
    )
    await machine.writel(AUDIODAC_BASE + 0x060, 0xFFFFFFFF)
    assert (await machine.readl(AUDIODAC_BASE + 0x060)) == 0, (
        "AUDIOOUT RESERVED must read as zero"
    )
    await machine.writel(AUDIODAC_BASE + 0x0B0, 0xFFFFFFFF)
    assert (await machine.readl(AUDIODAC_BASE + 0x0B0)) == 0x00000006, (
        "AUDIOOUT BIST must complete with DONE and PASS after START"
    )

    await machine.writel(AUDIODAC_BASE + 0x004, 0x0000000C)
    assert ((await machine.readl(AUDIODAC_BASE + 0x000)) & 0xC) == 0xC, (
        "AUDIOOUT CTRL_SET must raise the FIFO error status bits"
    )
    await machine.writel(AUDIODAC_BASE + 0x000, 0)
    assert ((await machine.readl(AUDIODAC_BASE + 0x000)) & 0xC) == 0xC, (
        "AUDIOOUT FIFO error status must survive general writes (W1C only)"
    )
    await machine.writel(AUDIODAC_BASE + 0x008, 0x0000000C)
    assert ((await machine.readl(AUDIODAC_BASE + 0x000)) & 0xC) == 0, (
        "AUDIOOUT CTRL_CLR must clear the FIFO error status bits"
    )

    await machine.writel(AUDIODAC_BASE + 0x008, 0xC0000000)
    await machine.writel(AUDIODAC_BASE + 0x004, 0x00000001)
    await machine.writel(AUDIODAC_BASE + 0x008, 0x00000001)
    assert ((await machine.readl(AUDIODAC_BASE + 0x000)) & 0x40000000) == 0x40000000, (
        "AUDIOOUT clearing RUN must set CLKGATE"
    )

    await machine.writel(AUDIODAC_BASE + 0x008, 0xC0000000)
    await machine.writel(AUDIODAC_BASE + 0x050, 0x03017F7F)
    await machine.writel(AUDIODAC_BASE + 0x030, 0x03FF01FF)
    await machine.writel(AUDIODAC_BASE + 0x004, 0x80000000)
    assert (await machine.readl(AUDIODAC_BASE + 0x000)) == 0xC0000000, (
        "AUDIOOUT SFTRST must restore the CTRL reset contract"
    )
    assert (await machine.readl(AUDIODAC_BASE + 0x030)) == 0x01FE01FE, (
        "AUDIOOUT SFTRST must reset the digital volume register"
    )
    assert (await machine.readl(AUDIODAC_BASE + 0x050)) == 0x03017F7F, (
        "AUDIOOUT SFTRST must preserve the POR-only headphone register"
    )


@pytest.mark.asyncio
async def test_audioout_fifo_and_dma_contract(machine):
    """AUDIOOUT FIFO and DMA contract"""
    descriptor = 0x00000500
    buffer = 0x00001000
    channel1_nxtcmdar = APBX_BASE + 0x0C0
    channel1_sema = APBX_BASE + 0x0F0

    await machine.writel(AUDIODAC_BASE + 0x008, 0xC0000000)
    await machine.writel(AUDIODAC_BASE + 0x004, 0x00000002)

    cmd = (
        (16 << 16) |  # XFER_COUNT
        (1 << 12) |   # CMDWORDS
        (1 << 6) |    # SEMAPHORE
        (1 << 3) |    # IRQONCMPLT
        2             # DMA_READ (memory -> peripheral)
    )
    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x014, 1 << 9)
    for i, word in enumerate([0x11111111, 0x22222222, 0x33333333, 0x44444444]):
        await machine.writel(buffer + 4 * i, word)
    await write_descriptor(machine, descriptor, 0, cmd, buffer, 0x00000003)
    await machine.writel(channel1_nxtcmdar, descriptor)
    await machine.writel(channel1_sema, 1)
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 5)) != 0, (
        "APBX channel 1 completion must assert the DAC DMA source on ICOLL"
    )
    assert ((await machine.readl(AUDIODAC_BASE + 0x040)) & 1) == 1, (
        "AUDIOOUT DEBUG must report FIFO space below capacity"
    )

    for word in [0x55555555, 0x66666666, 0x77777777, 0x88888888]:
        await machine.writel(AUDIODAC_BASE + 0x0F0, word)
    assert ((await machine.readl(AUDIODAC_BASE + 0x040)) & 1) == 0, (
        "AUDIOOUT DEBUG must report a full FIFO"
    )
    await machine.clock_step(200000)
    assert ((await machine.readl(AUDIODAC_BASE + 0x000)) & 8) != 0, (
        "AUDIOOUT must raise FIFO_UNDERFLOW_IRQ after the stream starves"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 6)) != 0, (
        "AUDIOOUT FIFO error must assert ICOLL source 6"
    )

    for i in range(9):
        await machine.writel(AUDIODAC_BASE + 0x0F0, 0x1000 + i)
    assert ((await machine.readl(AUDIODAC_BASE + 0x000)) & 4) != 0, (
        "AUDIOOUT must raise FIFO_OVERFLOW_IRQ when the FIFO is overfilled"
    )

    await machine.writel(AUDIODAC_BASE + 0x008, 0x00000001)
    assert ((await machine.readl(AUDIODAC_BASE + 0x000)) & 0x40000000) == 0x40000000, (
        "AUDIOOUT clearing RUN must set CLKGATE"
    )


@pytest.mark.asyncio
async def test_audioin_register_contract(machine):
    """AUDIOIN register contract"""
    resets = [
        [0x000, 0xC00000C0, "CTRL"],
        [0x010, 0x80000000, "STAT"],
        [0x020, 0x10110037, "ADCSRR"],
        [0x030, 0x00FE00FE, "ADCVOLUME"],
        [0x040, 0x00000000, "ADCDEBUG"],
        [0x050, 0x01000000, "ADCVOL"],
        [0x060, 0x00000000, "MICLINE"],
        [0x070, 0x80000040, "ANACLKCTRL"],
        [0x080, 0x00000000, "DATA"],
        [0x200, 0x01010000, "VERSION"],
    ]
    for offset, value, name in resets:
        assert (await machine.readl(AUDIOADC_BASE + offset)) == value, (
            f"AUDIOIN {name} must have its documented reset value"
        )
    assert (await machine.readl(AUDIOADC_BASE + 0x004)) == 0, (
        "AUDIOIN CTRL_SET must read as zero (SCT alias contract)"
    )

    await machine.writel(AUDIOADC_BASE + 0x008, 0x0000000C)
    masks = [
        [0x000, 0x3FFFFFFF, 0x001F07F3, "CTRL"],
        [0x020, 0xFFFFFFFF, 0xF71F1FFF, "ADCSRR"],
        [0x030, 0xFFFFFFFF, 0x02FF00FF, "ADCVOLUME"],
        [0x040, 0xFFFFFFFF, 0x80000000, "ADCDEBUG"],
        [0x050, 0xFFFFFFFF, 0x03003F3F, "ADCVOL"],
        [0x060, 0xFFFFFFFF, 0x21370033, "MICLINE"],
        [0x070, 0xFFFFFFFF, 0x80000077, "ANACLKCTRL"],
    ]
    for offset, inp, value, name in masks:
        await machine.writel(AUDIOADC_BASE + offset, inp)
        assert (await machine.readl(AUDIOADC_BASE + offset)) == value, (
            f"AUDIOIN {name} must mask reserved bits read-only"
        )
    await machine.writel(AUDIOADC_BASE + 0x010, 0)
    assert (await machine.readl(AUDIOADC_BASE + 0x010)) == 0x80000000, (
        "AUDIOIN STAT must ignore writes (read-only)"
    )

    await machine.writel(AUDIOADC_BASE + 0x004, 0x0000000C)
    assert ((await machine.readl(AUDIOADC_BASE + 0x000)) & 0xC) == 0xC, (
        "AUDIOIN CTRL_SET must raise the FIFO error status bits"
    )
    await machine.writel(AUDIOADC_BASE + 0x008, 0x0000000C)
    assert ((await machine.readl(AUDIOADC_BASE + 0x000)) & 0xC) == 0, (
        "AUDIOIN CTRL_CLR must clear the FIFO error status bits"
    )
    await machine.writel(AUDIOADC_BASE + 0x008, 0xC0000000)
    await machine.writel(AUDIOADC_BASE + 0x004, 0x00000001)
    await machine.writel(AUDIOADC_BASE + 0x008, 0x00000001)
    assert ((await machine.readl(AUDIOADC_BASE + 0x000)) & 0x40000000) == 0x40000000, (
        "AUDIOIN clearing RUN must set CLKGATE"
    )

    await machine.writel(AUDIOADC_BASE + 0x008, 0xC0000000)
    await machine.writel(AUDIOADC_BASE + 0x050, 0x03003F3F)
    await machine.writel(AUDIOADC_BASE + 0x030, 0x02FF00FF)
    await machine.writel(AUDIOADC_BASE + 0x004, 0x80000000)
    assert (await machine.readl(AUDIOADC_BASE + 0x030)) == 0x00FE00FE, (
        "AUDIOIN SFTRST must reset the digital volume register"
    )
    assert (await machine.readl(AUDIOADC_BASE + 0x050)) == 0x03003F3F, (
        "AUDIOIN SFTRST must preserve the POR-only ADC mux register"
    )


@pytest.mark.asyncio
async def test_audioin_fifo_and_dma_contract(machine):
    """AUDIOIN FIFO and DMA contract"""
    descriptor = 0x00000500
    buffer = 0x00001000
    channel0_nxtcmdar = APBX_BASE + 0x050
    channel0_sema = APBX_BASE + 0x080

    await machine.writel(AUDIOADC_BASE + 0x008, 0xC0000000)
    await machine.writel(AUDIOADC_BASE + 0x004, 0x00000003)

    await machine.clock_step(100000)
    assert ((await machine.readl(AUDIOADC_BASE + 0x040)) & 1) == 1, (
        "AUDIOIN DEBUG must report collected FIFO data"
    )
    await machine.clock_step(100000)
    assert ((await machine.readl(AUDIOADC_BASE + 0x000)) & 4) != 0, (
        "AUDIOIN must raise FIFO_OVERFLOW_IRQ when the FIFO is not drained"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 8)) != 0, (
        "AUDIOIN FIFO error must assert ICOLL source 8"
    )
    assert ((await machine.readl(AUDIOADC_BASE + 0x040)) & 2) == 2, (
        "AUDIOIN DEBUG DMA_PREQ must toggle once 8 words are collected"
    )

    cmd = (
        (8 << 16) |  # XFER_COUNT
        (1 << 12) |  # CMDWORDS
        (1 << 6) |   # SEMAPHORE
        (1 << 3) |   # IRQONCMPLT
        1            # DMA_WRITE (peripheral -> memory)
    )
    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x014, 1 << 8)
    await write_descriptor(machine, descriptor, 0, cmd, buffer, 0x00000003)
    await machine.writel(channel0_nxtcmdar, descriptor)
    await machine.writel(channel0_sema, 1)
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 7)) != 0, (
        "APBX channel 0 completion must assert the ADC DMA source on ICOLL"
    )
    assert (await machine.readl(buffer)) == 0, (
        "AUDIOIN DMA must deliver the FIFO samples (silent without a voice)"
    )

    await machine.writel(AUDIOADC_BASE + 0x008, 0x00000001)
    await machine.writel(AUDIOADC_BASE + 0x008, 0x40000000)
    for i in range(8):
        await machine.readl(AUDIOADC_BASE + 0x080)
    assert ((await machine.readl(AUDIOADC_BASE + 0x040)) & 1) == 0, (
        "AUDIOIN DEBUG must report an empty FIFO after CPU reads"
    )
    await machine.readl(AUDIOADC_BASE + 0x080)
    assert ((await machine.readl(AUDIOADC_BASE + 0x000)) & 8) != 0, (
        "AUDIOIN must raise FIFO_UNDERFLOW_IRQ when the FIFO is read empty"
    )
