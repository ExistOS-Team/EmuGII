import pytest

from framework.constants import APBH_BASE, CLKCTRL_BASE, GPMI_BASE, ICOLL_BASE, SRAM_BASE
from helpers.dma import (
    DMA_CHAIN,
    DMA_CMD_DMA_WRITE,
    DMA_IRQONCMPLT,
    DMA_NANDWAIT4READY,
    DMA_SEMAPHORE,
    DMA_WAIT4ENDCMD,
    DMA_ONE_PIO_WORD,
    GPMI_RUN_BIT,
    write_descriptor,
)


@pytest.mark.asyncio
async def test_apbh_dma_debug2_remaining_byte_contract(machine):
    """APBH DMA DEBUG2 remaining byte contract"""
    apbh_channel4_current_command = APBH_BASE + 0x200
    apbh_channel4_next_command = APBH_BASE + 0x210
    apbh_channel4_semaphore = APBH_BASE + 0x240
    apbh_channel4_debug2 = APBH_BASE + 0x260
    wait_descriptor = SRAM_BASE + 0x3100
    done_descriptor = SRAM_BASE + 0x3140
    bar = SRAM_BASE + 0x00010000
    xfer_count = 512

    wait_ctrl0 = GPMI_RUN_BIT | (3 << 24) | (1 << 23)
    wait_command = (
        (xfer_count << 16)
        | DMA_ONE_PIO_WORD
        | DMA_WAIT4ENDCMD
        | DMA_NANDWAIT4READY
        | DMA_CHAIN
        | DMA_CMD_DMA_WRITE
    )

    await machine.writel(CLKCTRL_BASE + 0x080, 0x00000001)
    await machine.writel(GPMI_BASE + 0x000, 0)
    await machine.writel(APBH_BASE + 0x008, 0xC0000000)
    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)

    await write_descriptor(machine, wait_descriptor, done_descriptor, wait_command, bar, wait_ctrl0)
    await write_descriptor(
        machine, done_descriptor, 0, DMA_SEMAPHORE | DMA_IRQONCMPLT, 0
    )

    await machine.writel(apbh_channel4_next_command, wait_descriptor)
    await machine.writel(apbh_channel4_semaphore, 1)

    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor, (
        f"APBH CH4 DEBUG2 must keep the current descriptor while WAIT4ENDCMD is pending: got 0x{current:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    expected_debug2 = (xfer_count << 16) | 0
    assert debug2 == expected_debug2, (
        f"APBH CH4 DEBUG2.APB_BYTES must hold the remaining XFER_COUNT while WAIT4ENDCMD is pending: got 0x{debug2:x}"
    )
    bar_value = await machine.readl(bar)
    assert bar_value == 0, (
        f"APBH CH4 DMA_WRITE must write the XFER_COUNT bytes to BAR while WAIT4ENDCMD is pending: got 0x{bar_value:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 1)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == done_descriptor, (
        f"APBH CH4 DEBUG2 must advance to the next descriptor after WAIT4ENDCMD completes: got 0x{current:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == 0, (
        f"APBH CH4 DEBUG2 must clear remaining bytes after WAIT4ENDCMD completes: got 0x{debug2:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0, (
        f"APBH CH4 semaphore must be consumed after the terminal descriptor runs: got 0x{sema:x}"
    )
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert (ctrl1 & (1 << 4)) != 0, (
        f"APBH CH4 CMDCMPLT_IRQ must be set after the terminal descriptor completes: ctrl1=0x{ctrl1:x}"
    )
    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)


@pytest.mark.asyncio
async def test_apbh_dma_wait4endcmd_freeze_clkgate_reset_contract(machine):
    """APBH DMA WAIT4ENDCMD freeze/clkgate/reset contract"""
    apbh_channel4_current_command = APBH_BASE + 0x200
    apbh_channel4_next_command = APBH_BASE + 0x210
    apbh_channel4_semaphore = APBH_BASE + 0x240
    apbh_channel4_debug2 = APBH_BASE + 0x260
    wait_descriptor = SRAM_BASE + 0x3300
    done_descriptor = SRAM_BASE + 0x3340
    wait_descriptor2 = SRAM_BASE + 0x3380
    done_descriptor2 = SRAM_BASE + 0x33C0
    wait_descriptor3 = SRAM_BASE + 0x3400
    done_descriptor3 = SRAM_BASE + 0x3440
    bar = SRAM_BASE + 0x00011000
    bar2 = SRAM_BASE + 0x00012000
    bar3 = SRAM_BASE + 0x00013000
    xfer_count = 512
    expected_debug2 = (xfer_count << 16) | 0

    wait_ctrl0 = GPMI_RUN_BIT | (3 << 24) | (1 << 23)
    wait_command = (
        (xfer_count << 16)
        | DMA_ONE_PIO_WORD
        | DMA_WAIT4ENDCMD
        | DMA_CHAIN
        | DMA_CMD_DMA_WRITE
    )

    async def start_wait4endcmd(nxt, wait_desc, done_desc, use_bar):
        await write_descriptor(
            machine, wait_desc, done_desc, wait_command, use_bar, wait_ctrl0
        )
        await write_descriptor(machine, done_desc, 0, DMA_SEMAPHORE | DMA_IRQONCMPLT, 0)
        await machine.writel(nxt, wait_desc)
        await machine.writel(apbh_channel4_semaphore, 1)

    await machine.writel(CLKCTRL_BASE + 0x080, 0x00000001)
    await machine.writel(GPMI_BASE + 0x000, 0)
    await machine.writel(APBH_BASE + 0x008, 0xC0000000)
    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)

    # FREEZE while WAIT4ENDCMD is pending must defer the completion until the
    # channel is unfrozen. The peripheral end-of-command is not lost.
    await start_wait4endcmd(apbh_channel4_next_command, wait_descriptor, done_descriptor, bar)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor, (
        f"APBH CH4 WAIT4ENDCMD must hold the descriptor while waiting for ready: got 0x{current:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == expected_debug2, (
        f"APBH CH4 DEBUG2 must keep remaining APB bytes while WAIT4ENDCMD is pending: got 0x{debug2:x}"
    )
    bar_value = await machine.readl(bar)
    assert bar_value == 0, (
        f"APBH CH4 DMA_WRITE must zero the BAR while waiting for ready: got 0x{bar_value:x}"
    )

    await machine.writel(APBH_BASE + 0x004, 1 << 4)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor, (
        f"FREEZE_CHANNEL must not retire the WAIT4ENDCMD descriptor immediately: got 0x{current:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 1)
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 28)) != 0, (
        f"GPMI READY0 view must be high while frozen: debug=0x{debug:x}"
    )
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor, (
        f"WAIT4ENDCMD completion must be deferred while the channel is frozen: got 0x{current:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0x00010000, (
        f"APBH CH4 semaphore must not be consumed while the completion is deferred: got 0x{sema:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == expected_debug2, (
        f"APBH CH4 DEBUG2 must keep remaining bytes while the completion is deferred: got 0x{debug2:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)
    await machine.writel(APBH_BASE + 0x008, 1 << 4)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == done_descriptor, (
        f"Unfreezing APBH CH4 must complete the deferred WAIT4ENDCMD and load the next descriptor: got 0x{current:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == 0, (
        f"APBH CH4 DEBUG2 must clear after the deferred WAIT4ENDCMD completes: got 0x{debug2:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0, (
        f"APBH CH4 semaphore must be consumed after the deferred completion finishes: got 0x{sema:x}"
    )
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert (ctrl1 & (1 << 4)) != 0, (
        f"APBH CH4 CMDCMPLT_IRQ must be set after the deferred completion finishes: ctrl1=0x{ctrl1:x}"
    )
    await machine.writel(APBH_BASE + 0x018, 0x00FFFFFF)

    # CLKGATE while WAIT4ENDCMD is pending must also defer the completion.
    await start_wait4endcmd(apbh_channel4_next_command, wait_descriptor2, done_descriptor2, bar2)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor2, (
        f"APBH CH4 WAIT4ENDCMD must hold the second descriptor while waiting for ready: got 0x{current:x}"
    )

    await machine.writel(APBH_BASE + 0x004, 1 << 12)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor2, (
        f"CLKGATE_CHANNEL must not retire the WAIT4ENDCMD descriptor immediately: got 0x{current:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 1)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor2, (
        f"WAIT4ENDCMD completion must be deferred while the channel is clock-gated: got 0x{current:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0x00010000, (
        f"APBH CH4 semaphore must not be consumed while the completion is clock-gated: got 0x{sema:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == expected_debug2, (
        f"APBH CH4 DEBUG2 must keep remaining bytes while the completion is clock-gated: got 0x{debug2:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)
    await machine.writel(APBH_BASE + 0x008, 1 << 12)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == done_descriptor2, (
        f"Un-gating APBH CH4 clock must complete the deferred WAIT4ENDCMD and load the next descriptor: got 0x{current:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == 0, (
        f"APBH CH4 DEBUG2 must clear after the clock-gated completion finishes: got 0x{debug2:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0, (
        f"APBH CH4 semaphore must be consumed after the clock-gated completion finishes: got 0x{sema:x}"
    )
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert (ctrl1 & (1 << 4)) != 0, (
        f"APBH CH4 CMDCMPLT_IRQ must be set after the clock-gated completion finishes: ctrl1=0x{ctrl1:x}"
    )
    await machine.writel(APBH_BASE + 0x018, 0x00FFFFFF)

    # RESET while WAIT4ENDCMD is pending must cancel the descriptor and not
    # resume after the peripheral completion arrives.
    await start_wait4endcmd(apbh_channel4_next_command, wait_descriptor3, done_descriptor3, bar3)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor3, (
        f"APBH CH4 WAIT4ENDCMD must hold the third descriptor while waiting for ready: got 0x{current:x}"
    )

    await machine.writel(APBH_BASE + 0x004, 1 << 20)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == 0, (
        f"RESET_CHANNEL must clear the WAIT4ENDCMD descriptor immediately: got 0x{current:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0, (
        f"RESET_CHANNEL must clear the semaphore immediately: got 0x{sema:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == 0, (
        f"RESET_CHANNEL must clear DEBUG2 immediately: got 0x{debug2:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 1)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == 0, (
        f"WAIT4ENDCMD completion must be ignored after RESET_CHANNEL cancels the descriptor: got 0x{current:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0, (
        f"APBH CH4 semaphore must remain zero after a reset-cancelled completion: got 0x{sema:x}"
    )
    debug2 = await machine.readl(apbh_channel4_debug2)
    assert debug2 == 0, (
        f"APBH CH4 DEBUG2 must remain zero after a reset-cancelled completion: got 0x{debug2:x}"
    )
    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)


@pytest.mark.asyncio
async def test_apbh_dma_64k_and_ahb_error_contract(machine):
    """APBH DMA 64 KiB and AHB error contract"""
    apbh_ch0_nxt = APBH_BASE + 0x050
    apbh_ch0_cmd = APBH_BASE + 0x060
    apbh_ch0_bar = APBH_BASE + 0x070
    apbh_ch0_sema = APBH_BASE + 0x080

    await machine.writel(APBH_BASE + 0x008, 0xC0000000)

    ok_descriptor = 0x00000500
    test_bar = 0x00018000
    await write_descriptor(
        machine, ok_descriptor, 0, DMA_SEMAPHORE | DMA_CMD_DMA_WRITE, test_bar
    )

    await machine.writel(test_bar, 0xDEADBEEF)
    await machine.writel(apbh_ch0_nxt, ok_descriptor)
    await machine.writel(apbh_ch0_sema, 1)
    value = await machine.readl(test_bar)
    assert value == 0, (
        f"APBH CH0 XFER_COUNT=0 must transfer 64 KiB bytes to the byte address in BAR: got 0x{value:x}"
    )
    bar = await machine.readl(apbh_ch0_bar)
    assert bar == test_bar, (
        f"APBH CH0 BAR must reflect the loaded descriptor buffer address: got 0x{bar:x}"
    )
    cmd = await machine.readl(apbh_ch0_cmd)
    assert (cmd & 0x0000FFFF) == 0x41, (
        f"APBH CH0 CMD must preserve the loaded descriptor command word: got 0x{cmd:x}"
    )

    err_descriptor = 0x00000510
    await write_descriptor(
        machine, err_descriptor, 0, DMA_SEMAPHORE | DMA_CMD_DMA_WRITE, 0xDEAD0000
    )
    await machine.writel(apbh_ch0_nxt, err_descriptor)
    await machine.writel(apbh_ch0_sema, 1)
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert (ctrl1 & (1 << 16)) == (1 << 16), (
        f"APBH CH0 AHB_ERROR_IRQ status must be set on a bus error: ctrl1=0x{ctrl1:x}"
    )
    raw = await machine.readl(ICOLL_BASE + 0x050)
    assert (raw & (1 << 13)) != 0, (
        f"APBH CH0 AHB error must assert the LCDIF_DMA ICOLL source (raw bit 45): raw=0x{raw:x}"
    )
