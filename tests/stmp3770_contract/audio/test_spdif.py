import pytest

from framework.constants import APBX_BASE, ICOLL_BASE, SPDIF_BASE
from helpers.dma import write_descriptor


@pytest.mark.asyncio
async def test_spdif_register_contract(machine):
    """SPDIF register contract"""
    assert (await machine.readl(SPDIF_BASE + 0x000)) == 0xC0000020, (
        "SPDIF CTRL must reset with SFTRST, CLKGATE and WAIT_END_XFER"
    )
    assert (await machine.readl(SPDIF_BASE + 0x010)) == 0x80000000, (
        "SPDIF STAT must report PRESENT with END_XFER clear"
    )
    assert (await machine.readl(SPDIF_BASE + 0x020)) == 0x00020000, (
        "SPDIF FRAMECTRL must reset with V_CONFIG set"
    )
    assert (await machine.readl(SPDIF_BASE + 0x030)) == 0x10000000, (
        "SPDIF SRR must reset to single-rate with a zeroed RATE"
    )
    assert (await machine.readl(SPDIF_BASE + 0x040)) == 0x00000001, (
        "SPDIF DEBUG must report empty FIFO space after reset"
    )
    assert (await machine.readl(SPDIF_BASE + 0x060)) == 0x01010000, (
        "SPDIF VERSION must report block v1.1"
    )
    assert (await machine.readl(SPDIF_BASE + 0x004)) == 0, (
        "SPDIF CTRL_SET must read as zero (SCT alias contract)"
    )

    await machine.writel(SPDIF_BASE + 0x000, 0x3FFFFFFF)
    assert (await machine.readl(SPDIF_BASE + 0x000)) == 0x001F0033, (
        "SPDIF CTRL must mask reserved bits and preserve W1C status bits on base writes"
    )
    await machine.writel(SPDIF_BASE + 0x004, 0x0000000C)
    assert ((await machine.readl(SPDIF_BASE + 0x000)) & 0xC) == 0xC, (
        "SPDIF CTRL_SET must raise the FIFO error status bits"
    )
    await machine.writel(SPDIF_BASE + 0x000, 0)
    assert ((await machine.readl(SPDIF_BASE + 0x000)) & 0xC) == 0xC, (
        "SPDIF FIFO error status bits must survive general writes (W1C only)"
    )
    await machine.writel(SPDIF_BASE + 0x008, 0x0000000C)
    assert ((await machine.readl(SPDIF_BASE + 0x000)) & 0xC) == 0, (
        "SPDIF CTRL_CLR must clear the FIFO error status bits"
    )

    await machine.writel(SPDIF_BASE + 0x020, 0xFFFFFFFF)
    assert (await machine.readl(SPDIF_BASE + 0x020)) == 0x000377FF, (
        "SPDIF FRAMECTRL must retain only documented subcode bits"
    )
    await machine.writel(SPDIF_BASE + 0x030, 0xFFFFFFFF)
    assert (await machine.readl(SPDIF_BASE + 0x030)) == 0x700FFFFF, (
        "SPDIF SRR must retain only BASEMULT and RATE fields"
    )
    await machine.writel(SPDIF_BASE + 0x010, 0)
    assert (await machine.readl(SPDIF_BASE + 0x010)) == 0x80000000, (
        "SPDIF STAT must ignore writes (read-only)"
    )

    await machine.writel(SPDIF_BASE + 0x004, 0x80000000)
    assert (await machine.readl(SPDIF_BASE + 0x000)) == 0xC0000020, (
        "SPDIF SFTRST must restore the documented reset contract"
    )
    assert (await machine.readl(SPDIF_BASE + 0x020)) == 0x00020000, (
        "SPDIF SFTRST must reset FRAMECTRL"
    )


@pytest.mark.asyncio
async def test_spdif_fifo_and_dma_contract(machine):
    """SPDIF FIFO and DMA contract"""
    descriptor = 0x00000500
    buffer = 0x00001000
    channel2_nxtcmdar = APBX_BASE + 0x130
    channel2_sema = APBX_BASE + 0x160

    await machine.writel(SPDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(SPDIF_BASE + 0x030, 0x1000BB80)
    await machine.writel(SPDIF_BASE + 0x004, 0x00000002)

    cmd = (
        (8 << 16) |  # XFER_COUNT
        (1 << 12) |  # CMDWORDS
        (1 << 6) |   # SEMAPHORE
        (1 << 3) |   # IRQONCMPLT
        2            # DMA_READ (memory -> peripheral)
    )
    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x014, 1 << 10)
    await machine.writel(buffer + 0x00, 0x11111111)
    await machine.writel(buffer + 0x04, 0x22222222)
    await write_descriptor(machine, descriptor, 0, cmd, buffer, 0x00000003)
    await machine.writel(channel2_nxtcmdar, descriptor)
    await machine.writel(channel2_sema, 1)
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 9)) != 0, (
        "APBX channel 2 completion must assert the SPDIF DMA source on ICOLL"
    )
    assert (await machine.readl(SPDIF_BASE + 0x040)) == 0x00000001, (
        "SPDIF DEBUG must still report FIFO space below the 32-bit capacity"
    )

    await machine.writel(SPDIF_BASE + 0x050, 0x33333333)
    await machine.writel(SPDIF_BASE + 0x050, 0x44444444)
    assert ((await machine.readl(SPDIF_BASE + 0x040)) & 1) == 0, (
        "SPDIF DEBUG must report a full FIFO in 32-bit mode"
    )
    await machine.clock_step(100000)
    assert ((await machine.readl(SPDIF_BASE + 0x000)) & 8) != 0, (
        "SPDIF must raise FIFO_UNDERFLOW_IRQ after the stream starves"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 10)) != 0, (
        "SPDIF FIFO error must assert ICOLL source 10"
    )
    assert ((await machine.readl(SPDIF_BASE + 0x040)) & 1) == 1, (
        "SPDIF DEBUG must report FIFO space again after the drain"
    )

    await machine.writel(SPDIF_BASE + 0x008, 0x00000001)
    assert (await machine.readl(SPDIF_BASE + 0x010)) == 0x80000001, (
        "SPDIF STAT must report END_XFER after the transfer completes"
    )

    await machine.writel(SPDIF_BASE + 0x050, 0x55555555)
    await machine.writel(SPDIF_BASE + 0x050, 0x66666666)
    await machine.writel(SPDIF_BASE + 0x050, 0x77777777)
    await machine.writel(SPDIF_BASE + 0x050, 0x88888888)
    await machine.writel(SPDIF_BASE + 0x050, 0x99999999)
    assert ((await machine.readl(SPDIF_BASE + 0x000)) & 4) != 0, (
        "SPDIF must raise FIFO_OVERFLOW_IRQ when the FIFO is overfilled"
    )
