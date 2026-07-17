import pytest

from framework.constants import APBX_BASE, DRI_BASE, ICOLL_BASE
from helpers.dma import DMA_IRQONCMPLT, DMA_ONE_PIO_WORD, DMA_SEMAPHORE, write_descriptor


@pytest.mark.asyncio
async def test_dri_register_contract(machine):
    """DRI register contract"""
    assert (await machine.readl(DRI_BASE + 0x000)) == 0xC0010000, (
        "DRI CTRL must reset with SFTRST, CLKGATE and the spare delay field"
    )
    assert (await machine.readl(DRI_BASE + 0x010)) == 0x00080010, (
        "DRI TIMING must reset to the documented pilot rate and gap interval"
    )
    assert (await machine.readl(DRI_BASE + 0x020)) == 0x80000000, (
        "DRI STAT must report DRI_PRESENT with idle summaries"
    )
    assert (await machine.readl(DRI_BASE + 0x030)) == 0, (
        "DRI DATA must read empty without an external radio front-end"
    )
    assert (await machine.readl(DRI_BASE + 0x004)) == 0, (
        "DRI CTRL_SET must read as zero (SCT alias contract)"
    )

    await machine.writel(DRI_BASE + 0x000, 0x3FFFFFFF)
    assert (await machine.readl(DRI_BASE + 0x000)) == 0x261F8E01, (
        "DRI CTRL must mask reserved bits and preserve W1C status bits"
    )
    await machine.writel(DRI_BASE + 0x010, 0xFFFFFFFF)
    assert (await machine.readl(DRI_BASE + 0x010)) == 0x000F00FF, (
        "DRI TIMING must retain only documented timing fields"
    )
    await machine.writel(DRI_BASE + 0x040, 0xFFFFFFFF)
    assert (await machine.readl(DRI_BASE + 0x040)) == 0x0FFC0000, (
        "DRI DEBUG0 must keep read-only line state at zero"
    )
    await machine.writel(DRI_BASE + 0x050, 0xFFFFFFFF)
    assert (await machine.readl(DRI_BASE + 0x050)) == 0xF8000000, (
        "DRI DEBUG1 must retain only the invert/reverse controls"
    )

    await machine.writel(DRI_BASE + 0x004, 0x80000000)
    assert (await machine.readl(DRI_BASE + 0x000)) == 0xC0010000, (
        "DRI SFTRST must restore the documented reset contract"
    )


@pytest.mark.asyncio
async def test_dri_irq_and_dma_contract(machine):
    """DRI IRQ and DMA contract"""
    descriptor = 0x00000500
    channel5_nxtcmdar = APBX_BASE + 0x280
    channel5_sema = APBX_BASE + 0x2B0

    await machine.writel(DRI_BASE + 0x008, 0xC0000000)

    await machine.writel(DRI_BASE + 0x004, 0x00000E06)
    assert ((await machine.readl(DRI_BASE + 0x020)) & 6) == 6, (
        "DRI STAT summaries must AND the status and enable fields"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 18)) != 0, (
        "DRI enabled error status must assert ICOLL source 50"
    )
    await machine.writel(DRI_BASE + 0x008, 0x00000006)
    assert ((await machine.readl(DRI_BASE + 0x020)) & 6) == 0, (
        "DRI CTRL_CLR must clear the W1C status and drop the summaries"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 18)) == 0, (
        "DRI ICOLL source 50 must deassert after the status clears"
    )

    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x014, 1 << 13)
    cmd = DMA_ONE_PIO_WORD | DMA_SEMAPHORE | DMA_IRQONCMPLT
    await write_descriptor(machine, descriptor, 0, cmd, 0, 0x00000001)
    await machine.writel(channel5_nxtcmdar, descriptor)
    await machine.writel(channel5_sema, 1)
    assert ((await machine.readl(ICOLL_BASE + 0x050)) & (1 << 17)) != 0, (
        "APBX channel 5 completion must assert the DRI DMA source on ICOLL"
    )
    assert ((await machine.readl(DRI_BASE + 0x000)) & 1) == 1, (
        "DRI CTRL PIO write from the DMA must set RUN"
    )
