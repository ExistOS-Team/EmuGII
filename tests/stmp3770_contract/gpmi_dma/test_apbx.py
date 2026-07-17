import pytest

from framework.constants import APBX_BASE, ICOLL_BASE, SRAM_BASE
from helpers.dma import (
    DMA_CHAIN,
    DMA_CMD_DMA_SENSE,
    DMA_CMD_DMA_WRITE,
    DMA_IRQONCMPLT,
    DMA_SEMAPHORE,
    write_descriptor,
)


@pytest.mark.asyncio
async def test_apbx_dma_64k_and_ahb_error_contract(machine):
    """APBX DMA 64 KiB and AHB error contract"""
    apbx_ch2_nxtcmdar = APBX_BASE + 0x130
    apbx_ch2_cmd = APBX_BASE + 0x140
    apbx_ch2_bar = APBX_BASE + 0x150
    apbx_ch2_sema = APBX_BASE + 0x160

    await machine.writel(APBX_BASE + 0x008, 0xC0000000)

    ok_descriptor = 0x00000500
    await write_descriptor(
        machine, ok_descriptor, 0, DMA_SEMAPHORE | DMA_CMD_DMA_WRITE, 0x00010000
    )

    await machine.writel(0x00010000, 0xDEADBEEF)
    await machine.writel(apbx_ch2_nxtcmdar, ok_descriptor)
    await machine.writel(apbx_ch2_sema, 1)
    value = await machine.readl(0x00010000)
    assert value == 0, (
        f"APBX XFER_COUNT=0 must transfer 64 KiB bytes to the byte address in BAR: got 0x{value:x}"
    )
    bar = await machine.readl(apbx_ch2_bar)
    assert bar == 0x00010000, (
        f"APBX CH2 BAR must reflect the loaded descriptor buffer address: got 0x{bar:x}"
    )
    cmd = await machine.readl(apbx_ch2_cmd)
    assert (cmd & 0x0000FFFF) == 0x41, (
        f"APBX CH2 CMD must preserve the loaded descriptor command word: got 0x{cmd:x}"
    )

    err_descriptor = 0x00000510
    await write_descriptor(
        machine, err_descriptor, 0, DMA_SEMAPHORE | DMA_CMD_DMA_WRITE, 0xDEAD0000
    )
    await machine.writel(apbx_ch2_nxtcmdar, err_descriptor)
    await machine.writel(apbx_ch2_sema, 1)
    ctrl1 = await machine.readl(APBX_BASE + 0x010)
    assert (ctrl1 & (1 << 18)) == (1 << 18), (
        f"APBX CH2 AHB_ERROR_IRQ status must be set on a bus error: ctrl1=0x{ctrl1:x}"
    )
    raw = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw & (1 << 9)) != 0, (
        f"APBX CH2 AHB error must assert the SPDIF_DMA ICOLL source (raw bit 9): raw=0x{raw:x}"
    )


@pytest.mark.asyncio
async def test_apbx_dma_sense_reserved_contract(machine):
    """APBX DMA SENSE reserved contract"""
    apbx_ch0_cur = APBX_BASE + 0x040
    apbx_ch0_nxt = APBX_BASE + 0x050
    apbx_ch0_cmd = APBX_BASE + 0x060
    apbx_ch0_bar = APBX_BASE + 0x070
    apbx_ch0_sema = APBX_BASE + 0x080
    sense_descriptor = 0x00000520
    success_descriptor = 0x00000530
    error_target = 0x00000540

    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x018, 0x00FFFFFF)

    # APBX COMMAND=3 is reserved. It must not act like APBH DMA_SENSE
    # and instead should be treated as a NO_DMA_XFER with CHAIN/SEMAPHORE/IRQ.
    await machine.writel(error_target, 0xDEADBEEF)

    await write_descriptor(
        machine,
        sense_descriptor,
        success_descriptor,
        DMA_CMD_DMA_SENSE | DMA_CHAIN | DMA_IRQONCMPLT | DMA_SEMAPHORE,
        error_target,
    )
    await write_descriptor(
        machine, success_descriptor, 0, DMA_SEMAPHORE | DMA_IRQONCMPLT, 0
    )

    await machine.writel(apbx_ch0_nxt, sense_descriptor)
    await machine.writel(apbx_ch0_sema, 1)

    current = await machine.readl(apbx_ch0_cur)
    assert current == success_descriptor, (
        f"APBX COMMAND=3 reserved must chain to NXTCMDAR instead of branching to BAR: got 0x{current:x}"
    )
    cmd = await machine.readl(apbx_ch0_cmd)
    assert (cmd & 0x00000003) == 0, (
        f"APBX COMMAND=3 reserved must leave the loaded command as the next descriptor: got 0x{cmd:x}"
    )
    bar = await machine.readl(apbx_ch0_bar)
    assert bar == 0, (
        f"APBX COMMAND=3 reserved must not use the sense descriptor BAR as a transfer address: got 0x{bar:x}"
    )
    target = await machine.readl(error_target)
    assert target == 0xDEADBEEF, (
        f"APBX COMMAND=3 reserved must not write to the BAR target: got 0x{target:x}"
    )
    sema = await machine.readl(apbx_ch0_sema)
    assert sema == 0, (
        f"APBX COMMAND=3 reserved must consume the semaphore: got 0x{sema:x}"
    )
    ctrl1 = await machine.readl(APBX_BASE + 0x010)
    assert (ctrl1 & 1) != 0, (
        f"APBX COMMAND=3 reserved must still honor IRQONCMPLT: ctrl1=0x{ctrl1:x}"
    )
