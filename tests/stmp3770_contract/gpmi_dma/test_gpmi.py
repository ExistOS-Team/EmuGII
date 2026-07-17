import pytest

from framework.constants import APBH_BASE, CLKCTRL_BASE, GPMI_BASE, SRAM_BASE
from helpers.dma import (
    DMA_CHAIN,
    DMA_CMD_DMA_SENSE,
    DMA_CMD_NO_DMA_XFER,
    DMA_IRQONCMPLT,
    DMA_NANDWAIT4READY,
    DMA_ONE_PIO_WORD,
    DMA_SEMAPHORE,
    DMA_WAIT4ENDCMD,
    GPMI_RUN_BIT,
    write_descriptor,
)


@pytest.mark.asyncio
async def test_gpmi_timing2_contract(machine):
    """GPMI TIMING2 contract"""
    await machine.writel(GPMI_BASE + 0x080, 0xFFFFFFFF)
    timing1 = await machine.readl(GPMI_BASE + 0x080)
    assert timing1 == 0xFFFF0000, (
        f"GPMI TIMING1 must retain only DEVICE_BUSY_TIMEOUT and read its lower reserved field as zero: got 0x{timing1:x}"
    )

    timing2 = await machine.readl(GPMI_BASE + 0x090)
    assert timing2 == 0x09020101, (
        f"GPMI TIMING2 must occupy 0x90 and expose all four documented reset bytes: got 0x{timing2:x}"
    )

    await machine.writel(GPMI_BASE + 0x090, 0x5A3C1708)
    timing2 = await machine.readl(GPMI_BASE + 0x090)
    assert timing2 == 0x5A3C1708, (
        f"GPMI TIMING2 must retain all four documented UDMA timing fields: got 0x{timing2:x}"
    )

    for offset in [0x094, 0x098, 0x09C]:
        await machine.writel(GPMI_BASE + offset, 0xFFFFFFFF)
        timing2 = await machine.readl(GPMI_BASE + 0x090)
        assert timing2 == 0x5A3C1708, (
            f"GPMI TIMING2 must not decode an undocumented alias at 0x{offset:x}: got 0x{timing2:x}"
        )


@pytest.mark.asyncio
async def test_gpmi_ctrl1_contract(machine):
    """GPMI CTRL1 contract"""
    ctrl1 = await machine.readl(GPMI_BASE + 0x060)
    assert ctrl1 == 0x00000004, (
        f"GPMI CTRL1 must reset with ATA_IRQRDY_POLARITY asserted: got 0x{ctrl1:x}"
    )

    await machine.writel(GPMI_BASE + 0x064, 0x00004001)
    ctrl1 = await machine.readl(GPMI_BASE + 0x060)
    assert ctrl1 == 0x00004005, (
        f"GPMI CTRL1_SET must affect only documented control fields: got 0x{ctrl1:x}"
    )

    await machine.writel(GPMI_BASE + 0x068, 0x00004001)
    ctrl1 = await machine.readl(GPMI_BASE + 0x060)
    assert ctrl1 == 0x00000004, (
        f"GPMI CTRL1_CLR must clear documented control fields: got 0x{ctrl1:x}"
    )

    await machine.writel(GPMI_BASE + 0x060, 0xFFFFFFFF)
    ctrl1 = await machine.readl(GPMI_BASE + 0x060)
    assert ctrl1 == 0x000079FF, (
        f"GPMI CTRL1 must ignore reserved bits and not software-set IRQ status: got 0x{ctrl1:x}"
    )

    await machine.writel(GPMI_BASE + 0x06C, 0x00004001)
    ctrl1 = await machine.readl(GPMI_BASE + 0x060)
    assert ctrl1 == 0x000039FE, (
        f"GPMI CTRL1_TOG must affect only documented control fields: got 0x{ctrl1:x}"
    )


@pytest.mark.asyncio
async def test_gpmi_ecc_register_contract(machine):
    """GPMI ECC register contract"""
    await machine.writel(GPMI_BASE + 0x020, 0xFFFFFFFF)
    eccctrl = await machine.readl(GPMI_BASE + 0x020)
    assert eccctrl == 0xFFFF71FF, (
        f"GPMI ECCCTRL must retain only HANDLE, ECC_CMD, ENABLE_ECC, and BUFFER_MASK: got 0x{eccctrl:x}"
    )

    await machine.writel(GPMI_BASE + 0x028, 0x00005001)
    eccctrl = await machine.readl(GPMI_BASE + 0x020)
    assert eccctrl == 0xFFFF21FE, (
        f"GPMI ECCCTRL_CLR must clear documented fields: got 0x{eccctrl:x}"
    )

    await machine.writel(GPMI_BASE + 0x02C, 0x00002002)
    eccctrl = await machine.readl(GPMI_BASE + 0x020)
    assert eccctrl == 0xFFFF01FC, (
        f"GPMI ECCCTRL_TOG must toggle documented fields: got 0x{eccctrl:x}"
    )

    await machine.writel(GPMI_BASE + 0x010, 0x12345678)
    for offset in [0x014, 0x018, 0x01C]:
        await machine.writel(GPMI_BASE + offset, 0xFFFFFFFF)
        compare = await machine.readl(GPMI_BASE + 0x010)
        assert compare == 0x12345678, (
            f"GPMI COMPARE must not decode an undocumented alias at 0x{offset:x}: got 0x{compare:x}"
        )

    await machine.writel(GPMI_BASE + 0x030, 0xFFFF1234)
    for offset in [0x034, 0x038, 0x03C]:
        await machine.writel(GPMI_BASE + offset, 0xFFFFFFFF)
        ecccount = await machine.readl(GPMI_BASE + 0x030)
        assert ecccount == 0x00001234, (
            f"GPMI ECCCOUNT must retain only its documented count and reject alias 0x{offset:x}: got 0x{ecccount:x}"
        )

    await machine.writel(GPMI_BASE + 0x040, 0x12345679)
    for offset in [0x044, 0x048, 0x04C]:
        await machine.writel(GPMI_BASE + offset, 0xFFFFFFFF)
        payload = await machine.readl(GPMI_BASE + 0x040)
        assert payload == 0x12345678, (
            f"GPMI PAYLOAD must remain word-aligned and reject alias 0x{offset:x}: got 0x{payload:x}"
        )

    await machine.writel(GPMI_BASE + 0x050, 0xCAFEBABF)
    for offset in [0x054, 0x058, 0x05C]:
        await machine.writel(GPMI_BASE + offset, 0xFFFFFFFF)
        auxiliary = await machine.readl(GPMI_BASE + 0x050)
        assert auxiliary == 0xCAFEBABC, (
            f"GPMI AUXILIARY must remain word-aligned and reject alias 0x{offset:x}: got 0x{auxiliary:x}"
        )


@pytest.mark.asyncio
async def test_gpmi_compare_sense_contract(machine):
    """GPMI compare and DMA sense contract"""
    sense_descriptor = SRAM_BASE + 0x3000
    success_descriptor = SRAM_BASE + 0x3040
    error_descriptor = SRAM_BASE + 0x3080
    compare_descriptor = SRAM_BASE + 0x30C0
    apbh_channel4_next_command = APBH_BASE + 0x210
    apbh_channel4_current_command = APBH_BASE + 0x200
    apbh_channel4_semaphore = APBH_BASE + 0x240
    dma_terminal = DMA_SEMAPHORE | DMA_IRQONCMPLT

    async def run_status_compare(compare, cs=0, eight_bit=True):
        await machine.writel(GPMI_BASE + 0x000, 1 << 23)
        await machine.writeb(GPMI_BASE + 0x0A0, 0x70)
        await machine.writel(
            GPMI_BASE + 0x000,
            (1 << 29) | (1 << 23) | (cs << 20) | (1 << 17) | 1,
        )
        await machine.writel(GPMI_BASE + 0x010, compare)
        await machine.writel(
            GPMI_BASE + 0x000,
            (1 << 29)
            | (2 << 24)
            | ((1 << 23) if eight_bit else 0)
            | (cs << 20)
            | 1,
        )

    async def run_sense_descriptor():
        await machine.writel(apbh_channel4_next_command, sense_descriptor)
        await machine.writel(apbh_channel4_semaphore, 1)
        return await machine.readl(apbh_channel4_current_command)

    async def run_status_compare_on_channel4(compare, cs):
        await machine.writel(GPMI_BASE + 0x000, 1 << 23)
        await machine.writeb(GPMI_BASE + 0x0A0, 0x70)
        await machine.writel(
            GPMI_BASE + 0x000,
            (1 << 29) | (1 << 23) | (cs << 20) | (1 << 17) | 1,
        )
        await write_descriptor(machine, compare_descriptor, 0, 2 << 12, 0)
        await machine.writel(compare_descriptor + 0x0C, (2 << 24) | (1 << 23) | (cs << 20) | 1)
        await machine.writel(compare_descriptor + 0x10, compare)
        await machine.writel(apbh_channel4_next_command, compare_descriptor)
        await machine.writel(apbh_channel4_semaphore, 1)

    await machine.writel(GPMI_BASE + 0x000, 0)
    await machine.writel(APBH_BASE + 0x008, 0xC0000000)
    await write_descriptor(
        machine, sense_descriptor, success_descriptor, DMA_CMD_DMA_SENSE, error_descriptor
    )
    await write_descriptor(machine, success_descriptor, 0, dma_terminal, 0)
    await write_descriptor(machine, error_descriptor, 0, dma_terminal, 0)

    await run_status_compare(0x00FF00E0)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 1) == 0, (
        f"GPMI matching compare must keep DEV0_ERROR clear: status=0x{status:x}"
    )
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 20)) == 0, (
        f"GPMI matching compare must clear SENSE0: debug=0x{debug:x}"
    )
    current = await run_sense_descriptor()
    assert current == success_descriptor, (
        f"APBH DMA_SENSE must follow NXTCMDAR when the GPMI sense line is false: got 0x{current:x}"
    )

    await run_status_compare(0x00FF0040)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 1) != 0, (
        f"GPMI compare mismatch must set DEV0_ERROR: status=0x{status:x}"
    )
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 20)) != 0, (
        f"GPMI compare mismatch must set SENSE0: debug=0x{debug:x}"
    )
    current = await run_sense_descriptor()
    assert current == error_descriptor, (
        f"APBH DMA_SENSE must follow BAR when the GPMI sense line is true: got 0x{current:x}"
    )

    await run_status_compare(0xFF0000E0, 0, False)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 1) != 0, (
        f"GPMI compare must apply the upper 8 bits of its 16-bit mask: status=0x{status:x}"
    )

    await run_status_compare_on_channel4(0x00FF0040, 1)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & (1 << 1)) != 0, (
        f"GPMI compare must report DEV1_ERROR for a failure on chip select 1: status=0x{status:x}"
    )
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 20)) != 0, (
        f"APBH channel 4 must sample GPMI SENSE0 even when the command uses chip select 1: debug=0x{debug:x}"
    )
    assert (debug & (1 << 21)) == 0, (
        f"chip select must not select the GPMI SENSE line: debug=0x{debug:x}"
    )
    current = await run_sense_descriptor()
    assert current == error_descriptor, (
        f"APBH channel 4 must branch on its own GPMI SENSE0 result: got 0x{current:x}"
    )


@pytest.mark.asyncio
async def test_gpmi_wait_for_ready_contract(machine):
    """GPMI WAIT_FOR_READY contract"""
    apbh_channel4_current_command = APBH_BASE + 0x200
    apbh_channel4_next_command = APBH_BASE + 0x210
    apbh_channel4_semaphore = APBH_BASE + 0x240
    wait_descriptor = SRAM_BASE + 0x3100
    done_descriptor = SRAM_BASE + 0x3140
    timeout_sense_descriptor = SRAM_BASE + 0x3180
    timeout_success_descriptor = SRAM_BASE + 0x31C0
    timeout_error_descriptor = SRAM_BASE + 0x3200
    command_wait_for_ready = 3 << 24
    word_length_8bit = 1 << 23
    run_bit = 1 << 29
    dma_terminal = DMA_SEMAPHORE | DMA_IRQONCMPLT

    wait_ctrl0 = run_bit | command_wait_for_ready | word_length_8bit

    await machine.writel(CLKCTRL_BASE + 0x080, 0x00000001)
    await machine.writel(GPMI_BASE + 0x000, 0)
    await machine.writel(APBH_BASE + 0x008, 0xC0000000)
    for cs in range(4):
        await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", cs, 0)

    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert debug == 0, (
        f"GPMI DEBUG reset value must clear READY, WAIT_FOR_READY_END, SENSE, and CMD_END views: got 0x{debug:x}"
    )

    await machine.writel(GPMI_BASE + 0x000, wait_ctrl0)
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & ((1 << 24) | (1 << 12))) == 0, (
        f"PIO WAIT_FOR_READY must not complete immediately before the ready input changes: debug=0x{debug:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 1)
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 28)) != 0, (
        f"GPMI READY0 view must track the normalized ready input state: debug=0x{debug:x}"
    )
    assert (debug & ((1 << 24) | (1 << 12))) != 0, (
        f"PIO WAIT_FOR_READY must toggle WAIT_FOR_READY_END0 and CMD_END0 when ready arrives: debug=0x{debug:x}"
    )
    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)

    await write_descriptor(
        machine,
        wait_descriptor,
        done_descriptor,
        DMA_ONE_PIO_WORD | DMA_WAIT4ENDCMD | DMA_NANDWAIT4READY | DMA_CHAIN | DMA_CMD_NO_DMA_XFER,
        0,
        command_wait_for_ready | word_length_8bit,
    )
    await write_descriptor(machine, done_descriptor, 0, dma_terminal, 0)

    await machine.writel(apbh_channel4_next_command, wait_descriptor)
    await machine.writel(apbh_channel4_semaphore, 1)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == wait_descriptor, (
        f"APBH WAIT4ENDCMD + NANDWAIT4READY must hold the current descriptor until ready/endcmd occur: got 0x{current:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0x00010000, (
        f"APBH semaphore must remain non-zero while WAIT_FOR_READY is still pending: got 0x{sema:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 1)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == done_descriptor, (
        f"APBH WAIT_FOR_READY chain must resume at the next descriptor after ready/endcmd occur: got 0x{current:x}"
    )
    sema = await machine.readl(apbh_channel4_semaphore)
    assert sema == 0, (
        f"APBH completion path must consume the terminal semaphore after WAIT_FOR_READY finishes: got 0x{sema:x}"
    )
    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)

    await machine.writel(GPMI_BASE + 0x080, 0x00010000)
    await machine.writel(GPMI_BASE + 0x004, 1 << 27)
    await machine.writel(GPMI_BASE + 0x000, wait_ctrl0)
    await machine.clock_step(200_000)

    ctrl1 = await machine.readl(GPMI_BASE + 0x060)
    assert (ctrl1 & (1 << 9)) != 0, (
        f"GPMI CTRL1.TIMEOUT_IRQ must latch when WAIT_FOR_READY times out: ctrl1=0x{ctrl1:x}"
    )
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & (1 << 8)) != 0, (
        f"GPMI STAT.RDY_TIMEOUT0 must latch when channel 0 WAIT_FOR_READY times out: status=0x{status:x}"
    )
    assert (status & 1) != 0, (
        f"GPMI WAIT_FOR_READY timeout must report DEV0_ERROR: status=0x{status:x}"
    )
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 20)) != 0, (
        f"GPMI WAIT_FOR_READY timeout must set SENSE0: debug=0x{debug:x}"
    )

    await write_descriptor(
        machine,
        timeout_sense_descriptor,
        timeout_success_descriptor,
        DMA_CMD_DMA_SENSE,
        timeout_error_descriptor,
    )
    await write_descriptor(machine, timeout_success_descriptor, 0, dma_terminal, 0)
    await write_descriptor(machine, timeout_error_descriptor, 0, dma_terminal, 0)
    await machine.writel(apbh_channel4_next_command, timeout_sense_descriptor)
    await machine.writel(apbh_channel4_semaphore, 1)
    current = await machine.readl(apbh_channel4_current_command)
    assert current == timeout_error_descriptor, (
        f"APBH DMA_SENSE must branch to BAR after WAIT_FOR_READY timeout sets the GPMI sense flop: got 0x{current:x}"
    )


@pytest.mark.asyncio
async def test_gpmi_data_fifo_contract(machine):
    """GPMI DATA FIFO contract"""
    await machine.writel(GPMI_BASE + 0x000, 0)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI STAT must report an empty, non-full FIFO after reset is released: status=0x{status:x}"
    )

    await machine.writew(GPMI_BASE + 0x0A0, 0x3412)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0, (
        f"GPMI STAT must clear FIFO_EMPTY after a 16-bit DATA write: status=0x{status:x}"
    )
    data = await machine.readw(GPMI_BASE + 0x0A0)
    assert data == 0x3412, (
        f"GPMI DATA must preserve a 16-bit transfer in 16-bit mode: got 0x{data:x}"
    )
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI STAT must restore FIFO_EMPTY after the last DATA byte is read: status=0x{status:x}"
    )

    await machine.writel(GPMI_BASE + 0x004, 1 << 23)
    await machine.writeb(GPMI_BASE + 0x0A0, 0x5A)
    await machine.writew(GPMI_BASE + 0x0A0, 0x3412)
    await machine.writel(GPMI_BASE + 0x0A0, 0x88776655)
    assert await machine.readb(GPMI_BASE + 0x0A0) == 0x5A
    assert await machine.readw(GPMI_BASE + 0x0A0) == 0x3412
    assert await machine.readl(GPMI_BASE + 0x0A0) == 0x88776655

    await machine.writeb(GPMI_BASE + 0x0A0, 0xA1)
    await machine.writeb(GPMI_BASE + 0x0A0, 0xB2)
    await machine.writeb(GPMI_BASE + 0x0A0, 0xC3)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 23) | 3)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI WRITE command must consume every queued DATA byte through XFER_COUNT: status=0x{status:x}"
    )

    await machine.writel(GPMI_BASE + 0x0A4, 0xDEADBEEF)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI DATA must reject an undocumented SCT alias without altering FIFO state: status=0x{status:x}"
    )

    for byte in range(64):
        await machine.writeb(GPMI_BASE + 0x0A0, byte)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x10, (
        f"GPMI STAT must report a full, non-empty FIFO after 64 queued 8-bit bus cycles: status=0x{status:x}"
    )
    await machine.writeb(GPMI_BASE + 0x0A0, 0xFF)
    data = await machine.readb(GPMI_BASE + 0x0A0)
    assert data == 0, (
        f"GPMI DATA must leave the FIFO unchanged when it is full: got 0x{data:x}"
    )

    await machine.writel(GPMI_BASE + 0x000, 0)
    for word in range(32):
        await machine.writew(GPMI_BASE + 0x0A0, word)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x10, (
        f"GPMI STAT must report a full FIFO after 32 queued 16-bit bus cycles: status=0x{status:x}"
    )

    await machine.writel(GPMI_BASE + 0x000, 0)
    for word in range(32):
        await machine.writew(GPMI_BASE + 0x0A0, word)
    await machine.writel(GPMI_BASE + 0x000, (1 << 29) | (1 << 23))
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI XFER_COUNT=0 must consume the available 64K-word transfer stream rather than zero words: status=0x{status:x}"
    )


@pytest.mark.asyncio
async def test_gpmi_run_word_length_xfer_count_contract(machine):
    """GPMI RUN WORD_LENGTH XFER_COUNT contract"""
    run_bit = 1 << 29
    word_length_bit = 1 << 23
    command_write = 0 << 24
    command_read = 1 << 24
    command_wait_for_ready = 3 << 24
    address_data = 0 << 17
    address_cle = 1 << 17
    address_increment = 1 << 16
    cmd_end0 = 1 << 12

    await machine.writel(CLKCTRL_BASE + 0x080, 0x00000001)
    await machine.writel(GPMI_BASE + 0x000, 0)
    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 0)

    wait_ctrl0 = run_bit | command_wait_for_ready | word_length_bit
    await machine.writel(GPMI_BASE + 0x000, wait_ctrl0)
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 7)) != 0, (
        f"GPMI DEBUG must be busy while WAIT_FOR_READY is pending: debug=0x{debug:x}"
    )

    await machine.writel(GPMI_BASE + 0x000, wait_ctrl0 & ~word_length_bit)
    ctrl0 = await machine.readl(GPMI_BASE + 0x000)
    assert (ctrl0 & word_length_bit) != 0, (
        f"GPMI WORD_LENGTH must be ignored while RUN is set: ctrl0=0x{ctrl0:x}"
    )
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 7)) != 0, (
        f"GPMI must remain busy while RUN is set: debug=0x{debug:x}"
    )

    await machine.set_irq_in("/machine/soc/gpmi", "rdy-busy", 0, 1)
    ctrl0 = await machine.readl(GPMI_BASE + 0x000)
    assert (ctrl0 & run_bit) == 0, (
        f"GPMI RUN must clear after WAIT_FOR_READY completes: ctrl0=0x{ctrl0:x}"
    )
    debug = await machine.readl(GPMI_BASE + 0x0C0)
    assert (debug & (1 << 7)) == 0, (
        f"GPMI DEBUG must clear BUSY after WAIT_FOR_READY completes: debug=0x{debug:x}"
    )

    await machine.writel(GPMI_BASE + 0x000, 0)
    ctrl0 = await machine.readl(GPMI_BASE + 0x000)
    assert (ctrl0 & word_length_bit) == 0, (
        f"GPMI WORD_LENGTH must be writable when RUN is clear: ctrl0=0x{ctrl0:x}"
    )

    await machine.writew(GPMI_BASE + 0x0A0, 0x3412)
    await machine.writew(GPMI_BASE + 0x0A0, 0x7856)
    await machine.writew(GPMI_BASE + 0x0A0, 0xBC9A)
    write_ctrl0 = run_bit | command_write | address_data | 3
    debug_before_write = await machine.readl(GPMI_BASE + 0x0C0)
    await machine.writel(GPMI_BASE + 0x000, write_ctrl0)
    debug_after_write = await machine.readl(GPMI_BASE + 0x0C0)
    assert ((debug_after_write ^ debug_before_write) & cmd_end0) != 0, (
        f"GPMI PIO WRITE must toggle CMD_END0: before=0x{debug_before_write:x} after=0x{debug_after_write:x}"
    )
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI 16-bit WRITE XFER_COUNT=3 must consume 6 bytes: status=0x{status:x}"
    )
    ctrl0 = await machine.readl(GPMI_BASE + 0x000)
    assert (ctrl0 & run_bit) == 0, (
        f"GPMI RUN must clear after a PIO WRITE command completes: ctrl0=0x{ctrl0:x}"
    )

    await machine.writew(GPMI_BASE + 0x0A0, 0x0090)
    read_id_ctrl0 = run_bit | command_write | address_cle | address_increment | 1
    debug_before_read_id = await machine.readl(GPMI_BASE + 0x0C0)
    await machine.writel(GPMI_BASE + 0x000, read_id_ctrl0)
    debug_after_read_id = await machine.readl(GPMI_BASE + 0x0C0)
    assert ((debug_after_read_id ^ debug_before_read_id) & cmd_end0) != 0, (
        f"GPMI PIO WRITE CLE must toggle CMD_END0: before=0x{debug_before_read_id:x} after=0x{debug_after_read_id:x}"
    )

    read16_ctrl0 = run_bit | command_read | address_data | 2
    debug_before_read16 = await machine.readl(GPMI_BASE + 0x0C0)
    await machine.writel(GPMI_BASE + 0x000, read16_ctrl0)
    debug_after_read16 = await machine.readl(GPMI_BASE + 0x0C0)
    assert ((debug_after_read16 ^ debug_before_read16) & cmd_end0) != 0, (
        f"GPMI PIO READ must toggle CMD_END0: before=0x{debug_before_read16:x} after=0x{debug_after_read16:x}"
    )
    half0 = await machine.readw(GPMI_BASE + 0x0A0)
    half1 = await machine.readw(GPMI_BASE + 0x0A0)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI 16-bit READ must leave FIFO empty after consuming 2 halfwords: status=0x{status:x}"
    )

    read8_ctrl0 = run_bit | word_length_bit | command_read | address_data | 4
    debug_before_read8 = await machine.readl(GPMI_BASE + 0x0C0)
    await machine.writel(GPMI_BASE + 0x000, read8_ctrl0)
    debug_after_read8 = await machine.readl(GPMI_BASE + 0x0C0)
    assert ((debug_after_read8 ^ debug_before_read8) & cmd_end0) != 0, (
        f"GPMI PIO READ must toggle CMD_END0: before=0x{debug_before_read8:x} after=0x{debug_after_read8:x}"
    )
    word = await machine.readl(GPMI_BASE + 0x0A0)
    status = await machine.readl(GPMI_BASE + 0x0B0)
    assert (status & 0x30) == 0x20, (
        f"GPMI 8-bit READ must leave FIFO empty after consuming 4 bytes: status=0x{status:x}"
    )
    assert (((half1 << 16) | half0) & 0xFFFFFFFF) == word, (
        f"GPMI READ must interpret XFER_COUNT as words whose width follows WORD_LENGTH: got 0x{word:x}"
    )
