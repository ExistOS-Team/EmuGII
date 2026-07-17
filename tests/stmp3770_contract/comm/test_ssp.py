import pytest

from framework.constants import APBH_BASE, ICOLL_BASE, CLKCTRL_BASE, SRAM_BASE
from helpers.dma import write_descriptor

SSP1_BASE = 0x80010000
SSP2_BASE = 0x80034000


@pytest.mark.asyncio
async def test_ssp_register_layout_and_reset_contract(machine):
    """SSP register layout and reset contract"""
    for name, base in [["SSP1", SSP1_BASE], ["SSP2", SSP2_BASE]]:
        assert (await machine.readl(base + 0x000)) == 0xC0000001, (
            f"{name} CTRL0 must reset with SFTRST, CLKGATE, and XFER_COUNT=1"
        )
        assert (await machine.readl(base + 0x060)) == 0x00200080, (
            f"{name} CTRL1 must reset with FIFO_UNDERRUN_IRQ and eight-bit word length"
        )
        assert (await machine.readl(base + 0x0C0)) == 0xE0000020, (
            f"{name} STATUS must report present controllers and an empty FIFO"
        )
        assert (await machine.readl(base + 0x100)) == 0, (
            f"{name} DEBUG must be read-only and reset clear at its documented address"
        )
        assert (await machine.readl(base + 0x110)) == 0x02000000, (
            f"{name} VERSION must be 2.0 at its documented address"
        )

    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x010, 0x00123456)
    await machine.writel(SSP1_BASE + 0x020, 0x89ABCDEF)
    await machine.writel(SSP1_BASE + 0x030, 0x10203040)
    await machine.writel(SSP1_BASE + 0x040, 0x55667788)
    await machine.writel(SSP1_BASE + 0x050, 0x00001234)

    assert (await machine.readl(SSP1_BASE + 0x010)) == 0x00123456, (
        f"SSP CMD0 must be mapped at +0x10"
    )
    assert (await machine.readl(SSP1_BASE + 0x020)) == 0x89ABCDEF, (
        f"SSP CMD1 must be mapped at +0x20"
    )
    assert (await machine.readl(SSP1_BASE + 0x030)) == 0x10203040, (
        f"SSP COMPREF must be mapped at +0x30"
    )
    assert (await machine.readl(SSP1_BASE + 0x040)) == 0x55667788, (
        f"SSP COMPMASK must be mapped at +0x40"
    )
    assert (await machine.readl(SSP1_BASE + 0x050)) == 0x00001234, (
        f"SSP TIMING must be mapped at +0x50"
    )


@pytest.mark.asyncio
async def test_ssp_soft_reset_and_clock_gate_contract(machine):
    """SSP soft reset and clock gate contract"""
    await machine.writel(SSP1_BASE + 0x008, 0x80000000)
    assert (await machine.readl(SSP1_BASE + 0x000)) == 0x40000001, (
        f"SSP CTRL0_CLR.SFTRST must release reset without clearing CLKGATE"
    )

    await machine.writel(SSP1_BASE + 0x008, 0x40000000)
    assert (await machine.readl(SSP1_BASE + 0x000)) == 0x00000001, (
        f"SSP CTRL0_CLR.CLKGATE must independently release the clock gate"
    )

    await machine.writel(SSP1_BASE + 0x000, 0x80000000)
    assert (await machine.readl(SSP1_BASE + 0x000)) == 0xC0000001, (
        f"SSP soft reset must restore documented reset state including CLKGATE"
    )


@pytest.mark.asyncio
async def test_ssp_soft_reset_hold_contract(machine):
    """SSP soft reset hold contract"""
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x060, 0x13579BDF)
    await machine.writel(SSP1_BASE + 0x010, 0x00123456)

    await machine.writel(SSP1_BASE + 0x004, 0x80000000)
    assert (await machine.readl(SSP1_BASE + 0x000)) == 0xC0000001, (
        f"SSP SFTRST must hold the module in its documented reset state"
    )

    await machine.writel(SSP1_BASE + 0x060, 0xFFFFFFFF)
    await machine.writel(SSP1_BASE + 0x010, 0x001FFFFF)
    assert (await machine.readl(SSP1_BASE + 0x060)) == 0x00200080, (
        f"SSP configuration writes must not escape a held SFTRST"
    )
    assert (await machine.readl(SSP1_BASE + 0x010)) == 0, (
        f"SSP CMD0 must remain reset while SFTRST is held"
    )


@pytest.mark.asyncio
async def test_ssp_ctrl1_writable_mask_contract(machine):
    """SSP CTRL1 writable mask contract"""
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, 0xFFFFFFFF)
    assert (await machine.readl(SSP1_BASE + 0x060)) == 0, (
        f"SSP CTRL1_CLR must clear all documented writable fields"
    )

    await machine.writel(SSP1_BASE + 0x064, 0xFFFFFFFF)
    assert (await machine.readl(SSP1_BASE + 0x060)) == 0xFFFFFFFF, (
        f"SSP CTRL1 contains only documented writable status, enable, and mode fields"
    )

    await machine.writel(SSP1_BASE + 0x068, 1 << 21)
    assert ((await machine.readl(SSP1_BASE + 0x060)) & (1 << 21)) == 0, (
        f"SSP CTRL1_CLR must use write-one-to-clear semantics for FIFO_UNDERRUN_IRQ"
    )


@pytest.mark.asyncio
async def test_ssp_sct_and_cmd0_reserved_contract(machine):
    """SSP SCT and CMD0 reserved contract"""
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x010, 0xFFE12345)
    assert (await machine.readl(SSP1_BASE + 0x010)) == 0x00012345, (
        f"SSP CMD0 must retain only documented bits 20:0"
    )

    await machine.writel(SSP1_BASE + 0x014, 0x00100000)
    assert (await machine.readl(SSP1_BASE + 0x014)) == 0, (
        f"SSP CMD0_SET must read as a write-only SCT alias"
    )
    assert (await machine.readl(SSP1_BASE + 0x010)) == 0x00112345, (
        f"SSP CMD0_SET must update documented CMD0 bits"
    )

    await machine.writel(SSP1_BASE + 0x020, 0x11223344)
    await machine.writel(SSP1_BASE + 0x024, 0xAABBCCDD)
    assert (await machine.readl(SSP1_BASE + 0x024)) == 0, (
        f"SSP CMD1 must not decode an undocumented SCT alias"
    )
    assert (await machine.readl(SSP1_BASE + 0x020)) == 0x11223344, (
        f"SSP CMD1 must ignore an undocumented SCT alias write"
    )

    assert (await machine.readl(SSP1_BASE + 0x004)) == 0, (
        f"SSP CTRL0_SET must read as a write-only SCT alias"
    )
    assert (await machine.readl(SSP1_BASE + 0x064)) == 0, (
        f"SSP CTRL1_SET must read as a write-only SCT alias"
    )


@pytest.mark.asyncio
async def test_ssp_error_irq_pairing_contract(machine):
    """SSP error IRQ pairing contract"""
    error_pairs = [
        [31, 30, "SDIO"],
        [29, 28, "response error"],
        [27, 26, "response timeout"],
        [25, 24, "data timeout"],
        [23, 22, "data CRC"],
        [21, 20, "FIFO underrun"],
        [19, 18, "CE-ATA CCS error"],
        [17, 16, "receive timeout"],
        [15, 14, "FIFO overrun"],
    ]

    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, 0xFFFFFFFF)
    for status_bit, enable_bit, name in error_pairs:
        status_mask = 1 << status_bit
        enable_mask = 1 << enable_bit

        await machine.writel(SSP1_BASE + 0x064, status_mask | enable_mask)
        assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 15)) != 0, (
            f"SSP1 {name} status and enable must assert ICOLL source 15"
        )

        await machine.writel(SSP1_BASE + 0x068, status_mask)
        assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 15)) == 0, (
            f"SSP1 {name} status clear must deassert ICOLL source 15"
        )
        await machine.writel(SSP1_BASE + 0x068, enable_mask)


@pytest.mark.asyncio
async def test_ssp_data_empty_read_contract(machine):
    """SSP DATA empty read contract"""
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, 1 << 21)

    assert (await machine.readl(SSP1_BASE + 0x070)) == 0, (
        f"SSP DATA empty read must return zeroed FIFO content"
    )
    assert ((await machine.readl(SSP1_BASE + 0x060)) & (1 << 21)) == 0, (
        f"SSP DATA reads must not advance or underflow the FIFO while RUN is clear"
    )
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & (1 << 4)) == 0, (
        f"SSP STATUS.FIFO_UNDRFLW must remain clear while RUN is clear"
    )

    await machine.writel(SSP1_BASE + 0x004, 1 << 29)
    assert (await machine.readl(SSP1_BASE + 0x070)) == 0, (
        f"SSP DATA empty read must return zeroed FIFO content"
    )
    assert ((await machine.readl(SSP1_BASE + 0x060)) & (1 << 21)) != 0, (
        f"SSP DATA empty read must raise FIFO_UNDERRUN_IRQ when RUN is set"
    )
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & (1 << 4)) != 0, (
        f"SSP DATA empty read must expose STATUS.FIFO_UNDRFLW when RUN is set"
    )
    assert ((await machine.readl(SSP1_BASE + 0x000)) & (1 << 29)) == 0, (
        f"SSP RUN must clear after the reset XFER_COUNT of one word completes"
    )


@pytest.mark.asyncio
async def test_ssp_dma_read_write_contract(machine):
    """SSP APBH DMA read/write contract"""
    run_bit = 1 << 29
    one_pio_word = 1 << 12
    chain_bit = 1 << 2
    irq_on_complete_bit = 1 << 3
    semaphore_bit = 1 << 6
    dma_write = 1
    dma_read = 2
    xfer_count = 4
    pio_ctrl0 = run_bit | xfer_count

    async def run_ssp_dma_for(ssp_base, ch_cur, ch_nxt, ch_sema, ch_debug2, desc, done_desc, bar):
        terminal = semaphore_bit | irq_on_complete_bit
        write_command = (xfer_count << 16) | one_pio_word | chain_bit | dma_write
        read_command = (xfer_count << 16) | one_pio_word | chain_bit | dma_read
        read_desc = desc + 0x80
        read_done_desc = done_desc + 0x80
        read_bar = bar + 0x80

        # release SSP clock gate and reset, then seed DATA
        await machine.writel(CLKCTRL_BASE + 0x070, 0x00000001)
        await machine.writel(ssp_base + 0x008, 0xC0000000)
        await machine.writel(ssp_base + 0x070, 0x42)
        await machine.writel(bar, 0)

        # DMA_WRITE (peripheral -> memory)
        await write_descriptor(machine, desc, done_desc, write_command, bar, pio_ctrl0)
        await write_descriptor(machine, done_desc, 0, terminal, 0)
        await machine.writel(ch_nxt, desc)
        await machine.writel(ch_sema, 1)

        assert (await machine.readl(ch_cur)) == done_desc, (
            f"SSP DMA_WRITE chain must complete the terminal descriptor"
        )
        assert (await machine.readl(bar)) == 0x42424242, (
            f"SSP DMA_WRITE must copy the current DATA register to BAR"
        )
        assert (await machine.readl(ch_debug2)) == 0, (
            f"SSP DMA_WRITE must clear DEBUG2 after completion"
        )
        assert (await machine.readl(ch_sema)) == 0, (
            f"SSP DMA_WRITE must consume the terminal semaphore"
        )
        assert ((await machine.readl(ssp_base + 0x000)) & (1 << 29)) == 0, (
            f"SSP DMA_WRITE must clear RUN after XFER_COUNT bytes"
        )
        assert ((await machine.readl(ssp_base + 0x0C0)) & (1 << 5)) != 0, (
            f"SSP DMA_WRITE must leave FIFO_EMPTY set after completion"
        )

        # DMA_READ (memory -> peripheral)
        await machine.writel(read_bar, 0x04030201)
        await write_descriptor(machine, read_desc, read_done_desc, read_command, read_bar, pio_ctrl0)
        await write_descriptor(machine, read_done_desc, 0, terminal, 0)
        await machine.writel(ch_nxt, read_desc)
        await machine.writel(ch_sema, 1)

        assert (await machine.readl(ch_cur)) == read_done_desc, (
            f"SSP DMA_READ chain must complete the terminal descriptor"
        )
        assert (await machine.readl(ssp_base + 0x070)) == 0x04, (
            f"SSP DMA_READ must leave the last memory byte in DATA"
        )
        assert (await machine.readl(ch_debug2)) == 0, (
            f"SSP DMA_READ must clear DEBUG2 after completion"
        )
        assert (await machine.readl(ch_sema)) == 0, (
            f"SSP DMA_READ must consume the terminal semaphore"
        )
        assert ((await machine.readl(ssp_base + 0x000)) & (1 << 29)) == 0, (
            f"SSP DMA_READ must clear RUN after XFER_COUNT bytes"
        )

    # release APBH reset/clock gate
    await machine.writel(APBH_BASE + 0x008, 0xC0000000)

    await run_ssp_dma_for(
        SSP1_BASE,
        APBH_BASE + 0x0B0, APBH_BASE + 0x0C0, APBH_BASE + 0x0F0, APBH_BASE + 0x110,
        SRAM_BASE + 0x3100, SRAM_BASE + 0x3140, SRAM_BASE + 0x00010000,
    )
    await run_ssp_dma_for(
        SSP2_BASE,
        APBH_BASE + 0x120, APBH_BASE + 0x130, APBH_BASE + 0x160, APBH_BASE + 0x180,
        SRAM_BASE + 0x3200, SRAM_BASE + 0x3240, SRAM_BASE + 0x00010004,
    )


@pytest.mark.asyncio
async def test_ssp_xfer_count_word_width_contract(machine):
    """SSP XFER_COUNT word-width contract"""
    run_bit = 1 << 29
    one_pio_word = 1 << 12
    chain_bit = 1 << 2
    irq_on_complete_bit = 1 << 3
    semaphore_bit = 1 << 6
    dma_write = 1
    dma_read = 2
    word_length = 0xF  # 16-bit

    # release APBH reset/clock gate
    await machine.writel(APBH_BASE + 0x008, 0xC0000000)

    # release SSP clock gate and reset; configure 16-bit word width
    await machine.writel(CLKCTRL_BASE + 0x070, 0x00000001)
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x060, word_length << 4)
    await machine.writel(SSP1_BASE + 0x050, 0x00000200)

    xfer_words = 2
    byte_count = 4
    pio_ctrl0 = run_bit | xfer_words
    desc = SRAM_BASE + 0x4000
    done_desc = SRAM_BASE + 0x4040
    bar = SRAM_BASE + 0x00010008
    terminal = semaphore_bit | irq_on_complete_bit
    write_command = (byte_count << 16) | one_pio_word | chain_bit | dma_write
    read_command = (byte_count << 16) | one_pio_word | chain_bit | dma_read
    read_bar = bar + 0x80

    # DMA_WRITE: 16-bit SSP produces two 16-bit words of the same DATA value
    await machine.writel(SSP1_BASE + 0x070, 0x12345678)
    await machine.writel(bar, 0)
    await write_descriptor(machine, desc, done_desc, write_command, bar, pio_ctrl0)
    await write_descriptor(machine, done_desc, 0, terminal, 0)
    await machine.writel(APBH_BASE + 0x0C0, desc)
    await machine.writel(APBH_BASE + 0x0F0, 1)

    assert (await machine.readl(bar)) == 0x56785678, (
        f"16-bit SSP DMA_WRITE must transfer XFER_COUNT words, not bytes"
    )
    assert ((await machine.readl(SSP1_BASE + 0x000)) & run_bit) == 0, (
        f"16-bit SSP DMA_WRITE must clear RUN after XFER_COUNT words"
    )

    # DMA_READ: 16-bit SSP consumes two 16-bit words and leaves the last in DATA
    await machine.writel(read_bar, 0x04030201)
    await write_descriptor(machine, desc + 0x100, done_desc + 0x100, read_command, read_bar, pio_ctrl0)
    await write_descriptor(machine, done_desc + 0x100, 0, terminal, 0)
    await machine.writel(APBH_BASE + 0x0C0, desc + 0x100)
    await machine.writel(APBH_BASE + 0x0F0, 1)

    assert (await machine.readl(SSP1_BASE + 0x070)) == 0x0403, (
        f"16-bit SSP DMA_READ must leave the last 16-bit word in DATA"
    )
    assert ((await machine.readl(SSP1_BASE + 0x000)) & run_bit) == 0, (
        f"16-bit SSP DMA_READ must clear RUN after XFER_COUNT words"
    )


@pytest.mark.asyncio
async def test_ssp_fifo_occupancy_contract(machine):
    """SSP FIFO occupancy contract"""
    run_bit = 1 << 29
    fifo_full_bit = 1 << 8
    fifo_ovrflw_bit = 1 << 9
    fifo_empty_bit = 1 << 5
    fifo_undrflw_bit = 1 << 4
    fifo_overrun_irq_bit = 1 << 15
    fifo_overrun_en_bit = 1 << 14
    fifo_underrun_irq_bit = 1 << 21
    fifo_underrun_en_bit = 1 << 20

    # release SFTRST/CLKGATE and clear default FIFO_UNDERRUN_IRQ status
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, fifo_underrun_irq_bit)
    await machine.writel(SSP1_BASE + 0x068, fifo_overrun_irq_bit)

    # reset state: empty FIFO
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_empty_bit) == fifo_empty_bit, (
        f"SSP STATUS.FIFO_EMPTY must be set at reset"
    )
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_full_bit) == 0, (
        f"SSP STATUS.FIFO_FULL must be clear at reset"
    )

    # DATA write while RUN is clear fills the FIFO
    await machine.writel(SSP1_BASE + 0x070, 0x12345678)
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_full_bit) == fifo_full_bit, (
        f"SSP DATA write while RUN is clear must set FIFO_FULL"
    )
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_empty_bit) == 0, (
        f"SSP DATA write while RUN is clear must clear FIFO_EMPTY"
    )

    # another DATA write while RUN is clear overflows
    await machine.writel(SSP1_BASE + 0x070, 0x9ABCDEF0)
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_ovrflw_bit) == fifo_ovrflw_bit, (
        f"SSP DATA write on a full FIFO must set FIFO_OVRFLW"
    )
    assert ((await machine.readl(SSP1_BASE + 0x060)) & fifo_overrun_irq_bit) == fifo_overrun_irq_bit, (
        f"SSP FIFO overrun must set CTRL1.FIFO_OVERRUN_IRQ"
    )
    # enable the overrun IRQ and route it to the ICOLL
    await machine.writel(SSP1_BASE + 0x064, fifo_overrun_irq_bit | fifo_overrun_en_bit)
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 15)) == (1 << 15), (
        f"SSP FIFO overrun IRQ must assert ICOLL source 15 when enabled"
    )
    await machine.writel(SSP1_BASE + 0x068, fifo_overrun_irq_bit)
    await machine.writel(SSP1_BASE + 0x068, fifo_overrun_en_bit)

    # RUN rise clears the FIFO error flags and sets busy/full
    await machine.writel(SSP1_BASE + 0x004, 0x20000000 | 1)
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_ovrflw_bit) == 0, (
        f"SSP RUN rise must clear FIFO_OVRFLW"
    )
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_full_bit) == fifo_full_bit, (
        f"SSP RUN rise must keep FIFO_FULL when a word is already loaded"
    )
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & 0xD) == 0xD, (
        f"SSP RUN rise must set BUSY, CMD_BUSY, DATA_BUSY"
    )

    # DATA read while RUN is set consumes the word
    assert (await machine.readl(SSP1_BASE + 0x070)) == 0x9ABCDEF0, (
        f"SSP DATA read must return the most recently written DATA word"
    )
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_empty_bit) == fifo_empty_bit, (
        f"SSP DATA read must set FIFO_EMPTY after consuming the word"
    )
    assert ((await machine.readl(SSP1_BASE + 0x000)) & run_bit) == 0, (
        f"SSP RUN must clear after the single loaded word is consumed"
    )

    # another DATA read with RUN set and empty FIFO causes underflow
    await machine.writel(SSP1_BASE + 0x004, 0x20000000 | 1)
    await machine.writel(SSP1_BASE + 0x064, fifo_underrun_irq_bit | fifo_underrun_en_bit)
    await machine.readl(SSP1_BASE + 0x070)
    assert ((await machine.readl(SSP1_BASE + 0x0C0)) & fifo_undrflw_bit) == fifo_undrflw_bit, (
        f"SSP DATA read with RUN set and empty FIFO must set FIFO_UNDRFLW"
    )
    assert ((await machine.readl(SSP1_BASE + 0x060)) & fifo_underrun_irq_bit) == fifo_underrun_irq_bit, (
        f"SSP FIFO underrun must set CTRL1.FIFO_UNDERRUN_IRQ"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 15)) == (1 << 15), (
        f"SSP FIFO underrun IRQ must assert ICOLL source 15 when enabled"
    )


@pytest.mark.asyncio
async def test_ssp_ctrl1_run_lock_contract(machine):
    """SSP CTRL1 RUN lock contract"""
    # release SFTRST/CLKGATE, set WORD_LENGTH=8 and SSP_MODE=SPI
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, 0xFFFFFFFF)
    await machine.writel(SSP1_BASE + 0x064, 0x00000080)

    # set RUN with XFER_COUNT=1 and then try to change WORD_LENGTH/SSP_MODE
    await machine.writel(SSP1_BASE + 0x004, 0x20000000 | 1)
    await machine.writel(SSP1_BASE + 0x060, 0x000000F0)
    assert (await machine.readl(SSP1_BASE + 0x060)) == 0x00000080, (
        f"SSP CTRL1.WORD_LENGTH and SSP_MODE must be locked while RUN is set"
    )

    # clear RUN and verify the fields can be changed again
    await machine.writel(SSP1_BASE + 0x008, 0x20000000)
    await machine.writel(SSP1_BASE + 0x060, 0x000000F0)
    assert (await machine.readl(SSP1_BASE + 0x060)) == 0x000000F0, (
        f"SSP CTRL1.WORD_LENGTH and SSP_MODE must be writable after RUN is clear"
    )


@pytest.mark.asyncio
async def test_ssp_recv_timeout_contract(machine):
    """SSP RECV_TIMEOUT contract"""
    run_bit = 1 << 29
    fifo_full_bit = 1 << 8
    recv_timeout_stat_bit = 1 << 11
    recv_timeout_irq_bit = 1 << 17
    recv_timeout_en_bit = 1 << 16
    fifo_underrun_irq_bit = 1 << 21

    # release SFTRST/CLKGATE and clear default FIFO_UNDERRUN_IRQ status
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, fifo_underrun_irq_bit)

    # enable RECV_TIMEOUT_IRQ
    await machine.writel(SSP1_BASE + 0x064, recv_timeout_en_bit)

    # preload DATA with RUN not set so FIFO becomes full
    await machine.writel(SSP1_BASE + 0x070, 0x12345678)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & fifo_full_bit) == fifo_full_bit, (
        f"SSP FIFO must be full after DATA write with RUN not set"
    )
    assert (status & recv_timeout_stat_bit) == 0, (
        f"SSP RECV_TIMEOUT_STAT must not be set before RUN"
    )

    # set RUN with XFER_COUNT=1, this starts the 128 HCLK receive timeout
    await machine.writel(SSP1_BASE + 0x000, 0x20000001 | run_bit)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & fifo_full_bit) == fifo_full_bit, (
        f"SSP FIFO must remain full right after RUN rise"
    )
    assert (status & recv_timeout_stat_bit) == 0, (
        f"SSP RECV_TIMEOUT_STAT must remain clear right after RUN rise"
    )

    # 128 HCLK cycles at 24 MHz is ~5.3 us; step 10 us to be safe
    await machine.clock_step(10000)

    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & recv_timeout_stat_bit) == recv_timeout_stat_bit, (
        f"SSP RECV_TIMEOUT_STAT must set after 128 HCLK cycles without FIFO read"
    )
    ctrl1 = await machine.readl(SSP1_BASE + 0x060)
    assert (ctrl1 & recv_timeout_irq_bit) == recv_timeout_irq_bit, (
        f"SSP RECV_TIMEOUT_IRQ must be set on timeout"
    )
    raw0 = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw0 & (1 << 15)) != 0, (
        f"SSP1 error must assert ICOLL source 15 when RECV_TIMEOUT_IRQ is enabled"
    )

    # reading DATA consumes the FIFO and clears RECV_TIMEOUT_STAT
    data = await machine.readl(SSP1_BASE + 0x070)
    assert data == 0x12345678, (
        f"SSP DATA read must return the preloaded value"
    )
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & recv_timeout_stat_bit) == 0, (
        f"SSP RECV_TIMEOUT_STAT must clear after FIFO read"
    )

    # clear RECV_TIMEOUT_IRQ and deassert the error interrupt
    await machine.writel(SSP1_BASE + 0x068, recv_timeout_irq_bit)
    raw0_after = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw0_after & (1 << 15)) == 0, (
        f"SSP1 error must deassert after clearing RECV_TIMEOUT_IRQ"
    )


@pytest.mark.asyncio
async def test_ssp_debug_and_dma_status_contract(machine):
    """SSP DEBUG and DMA status contract"""
    run_bit = 1 << 29
    enable_bit = 1 << 16
    data_xfer_bit = 1 << 24
    read_bit = 1 << 25
    dma_req_bit = 1 << 19
    dma_end_bit = 1 << 18
    dma_term_bit = 1 << 20
    busy_bit = 1 << 0
    data_busy_bit = 1 << 2
    cmd_busy_bit = 1 << 3
    fifo_full_bit = 1 << 8

    debug_cmd_sm_shift = 10
    debug_mmc_sm_shift = 12
    debug_dat_sm_shift = 24
    debug_dma_sm_shift = 16
    debug_cmd_oe_bit = 1 << 19

    # release SFTRST/CLKGATE
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)

    # SD/MMC mode: 8-bit word, DMA enabled, command + data write
    await machine.writel(SSP1_BASE + 0x060, 0x00002073)
    await machine.writel(SSP1_BASE + 0x070, 0x12345678)
    await machine.writel(
        SSP1_BASE + 0x000,
        run_bit | data_xfer_bit | enable_bit | 1,
    )

    debug = await machine.readl(SSP1_BASE + 0x100)
    assert ((debug >> debug_cmd_sm_shift) & 0x3) == 0x1, (
        f"SSP CMD_SM must be INDEX in SD/MMC command phase"
    )
    assert ((debug >> debug_mmc_sm_shift) & 0xF) == 0x5, (
        f"SSP MMC_SM must be TX in SD/MMC data write"
    )
    assert ((debug >> debug_dat_sm_shift) & 0x7) == 0x2, (
        f"SSP DAT_SM must be WORD during SD/MMC data transfer"
    )
    assert ((debug >> debug_dma_sm_shift) & 0x7) == 0x4, (
        f"SSP DMA_SM must be BUSY when DMA_ENABLE is set and RUN is active"
    )
    assert (debug & debug_cmd_oe_bit) != 0, (
        f"SSP CMD_OE must be asserted during SD/MMC command"
    )

    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & (busy_bit | cmd_busy_bit | data_busy_bit)) == (busy_bit | cmd_busy_bit | data_busy_bit), (
        f"SSP BUSY/CMD_BUSY/DATA_BUSY must be set during SD/MMC transfer"
    )
    assert (status & fifo_full_bit) == fifo_full_bit, (
        f"SSP FIFO must be full after preloading DATA"
    )
    assert (status & dma_req_bit) == dma_req_bit, (
        f"SSP DMAREQ must be asserted while RUN is active with DMA_ENABLE"
    )
    assert (status & (dma_end_bit | dma_term_bit)) == 0, (
        f"SSP DMAEND/DMATERM must be clear while RUN is active"
    )

    # clear RUN, DMA command ends/terminates
    await machine.writel(SSP1_BASE + 0x008, run_bit)

    debug = await machine.readl(SSP1_BASE + 0x100)
    assert ((debug >> debug_dma_sm_shift) & 0x7) == 0x5, (
        f"SSP DMA_SM must be DONE after RUN fall"
    )
    assert (debug & debug_cmd_oe_bit) == 0, (
        f"SSP CMD_OE must be deasserted after RUN fall"
    )

    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & dma_req_bit) == 0, (
        f"SSP DMAREQ must clear after RUN fall"
    )
    assert (status & (dma_end_bit | dma_term_bit)) == (dma_end_bit | dma_term_bit), (
        f"SSP DMAEND and DMATERM must set after RUN fall"
    )

    # MS mode: command-only (no DATA_XFER) should not show DAT_SM
    await machine.writel(SSP1_BASE + 0x060, 0x00002074)
    await machine.writel(SSP1_BASE + 0x000, run_bit | enable_bit | 1)

    debug = await machine.readl(SSP1_BASE + 0x100)
    assert ((debug >> debug_mmc_sm_shift) & 0xF) == 0x0, (
        f"SSP MMC_SM must be idle in MS mode"
    )
    assert ((debug >> debug_dat_sm_shift) & 0x7) == 0x0, (
        f"SSP DAT_SM must be idle in MS command-only transfer"
    )
    assert (debug & debug_cmd_oe_bit) == debug_cmd_oe_bit, (
        f"SSP CMD_OE must be asserted during MS command phase"
    )

    # reset and verify DEBUG returns to idle
    await machine.writel(SSP1_BASE + 0x000, 0x80000000)
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    debug = await machine.readl(SSP1_BASE + 0x100)
    assert debug == 0x0, (
        f"SSP DEBUG must return to idle after soft reset"
    )


@pytest.mark.asyncio
async def test_ssp_timeout_and_error_status_contract(machine):
    """SSP timeout and error status contract"""
    run_bit = 1 << 29
    enable_bit = 1 << 16
    get_resp_bit = 1 << 17
    data_xfer_bit = 1 << 24
    dma_enable_bit = 1 << 13
    resp_timeout_bit = 1 << 14
    timeout_bit = 1 << 12
    data_crc_err_bit = 1 << 13
    ceata_ccs_err_bit = 1 << 10
    resp_err_bit = 1 << 15
    resp_crc_err_bit = 1 << 16
    sdio_irq_bit = 1 << 17
    dma_sense_bit = 1 << 21
    resp_timeout_irq_bit = 1 << 27
    resp_timeout_en_bit = 1 << 26
    data_timeout_irq_bit = 1 << 25
    data_timeout_en_bit = 1 << 24
    data_crc_irq_bit = 1 << 23
    resp_err_irq_bit = 1 << 29
    ceata_ccs_err_irq_bit = 1 << 19
    sdio_irq_set = 0xC0000000
    sdio_irq_clear = 0x80000000

    # ungate SSP clock so SSPCLK is 24 MHz (XTAL bypass)
    await machine.writel(CLKCTRL_BASE + 0x078, 0x80000000)

    # release SFTRST/CLKGATE and clear default FIFO_UNDERRUN_IRQ
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, 0x00200000)

    # response timeout in SD/MMC command-only mode
    await machine.writel(
        SSP1_BASE + 0x060,
        0x04002000 | (0x7 << 4) | 0x3,
    )
    await machine.writel(
        SSP1_BASE + 0x000,
        run_bit | enable_bit | get_resp_bit | 1,
    )

    await machine.clock_step(10000)

    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & resp_timeout_bit) == resp_timeout_bit, (
        f"SSP RESP_TIMEOUT must set after 64 SCK cycles with no response"
    )
    ctrl1 = await machine.readl(SSP1_BASE + 0x060)
    assert (ctrl1 & resp_timeout_irq_bit) == resp_timeout_irq_bit, (
        f"SSP RESP_TIMEOUT_IRQ must be set on response timeout"
    )
    raw0 = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw0 & (1 << 15)) != 0, (
        f"SSP1 error must assert ICOLL source 15 when RESP_TIMEOUT_IRQ is enabled"
    )

    # clear RUN, then reset and prepare data timeout
    await machine.writel(SSP1_BASE + 0x008, run_bit)
    await machine.writel(SSP1_BASE + 0x000, 0x80000000)
    await machine.writel(SSP1_BASE + 0x008, 0xC0000000)
    await machine.writel(SSP1_BASE + 0x068, 0x00200000)

    # data timeout with TIMEOUT=1 (4096 SCK cycles) and DATA_XFER
    await machine.writel(
        SSP1_BASE + 0x060,
        data_timeout_en_bit | dma_enable_bit | (0x7 << 4) | 0x3,
    )
    await machine.writel(SSP1_BASE + 0x050, 0x00010000)
    await machine.writel(
        SSP1_BASE + 0x000,
        run_bit | data_xfer_bit | enable_bit | 1,
    )

    await machine.clock_step(200000)

    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & timeout_bit) == timeout_bit, (
        f"SSP TIMEOUT must set after TIMEOUT*4096 SCK cycles without data"
    )
    assert (status & dma_sense_bit) == dma_sense_bit, (
        f"SSP DMASENSE must set when DMA-enabled data transfer times out"
    )
    ctrl1 = await machine.readl(SSP1_BASE + 0x060)
    assert (ctrl1 & data_timeout_irq_bit) == data_timeout_irq_bit, (
        f"SSP DATA_TIMEOUT_IRQ must be set on data timeout"
    )
    raw0 = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw0 & (1 << 15)) != 0, (
        f"SSP1 error must assert ICOLL source 15 when DATA_TIMEOUT_IRQ is enabled"
    )

    # RUN rise clears sticky TIMEOUT/DMASENSE status
    await machine.writel(SSP1_BASE + 0x008, run_bit)
    await machine.writel(
        SSP1_BASE + 0x000,
        run_bit | data_xfer_bit | enable_bit | 1,
    )
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & (timeout_bit | dma_sense_bit)) == 0, (
        f"SSP TIMEOUT/DMASENSE must clear on RUN rise"
    )
    # clear RUN to avoid further timeouts
    await machine.writel(SSP1_BASE + 0x008, run_bit)

    # software-set error statuses (DATA_CRC_ERR, CEATA_CCS_ERR, RESP_ERR)
    await machine.writel(SSP1_BASE + 0x064, data_crc_irq_bit)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & data_crc_err_bit) == data_crc_err_bit, (
        f"SSP DATA_CRC_ERR must mirror DATA_CRC_IRQ set"
    )
    assert (status & dma_sense_bit) == dma_sense_bit, (
        f"SSP DMASENSE must set when DATA_CRC_ERR is set with DMA_ENABLE"
    )
    await machine.writel(SSP1_BASE + 0x068, data_crc_irq_bit)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & data_crc_err_bit) == data_crc_err_bit, (
        f"SSP DATA_CRC_ERR must be sticky (not cleared by CTRL1_CLR)"
    )

    await machine.writel(SSP1_BASE + 0x064, ceata_ccs_err_irq_bit)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & ceata_ccs_err_bit) == ceata_ccs_err_bit, (
        f"SSP CEATA_CCS_ERR must mirror CEATA_CCS_ERR_IRQ set"
    )

    await machine.writel(SSP1_BASE + 0x064, resp_err_irq_bit)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & (resp_err_bit | resp_crc_err_bit)) == (resp_err_bit | resp_crc_err_bit), (
        f"SSP RESP_ERR and RESP_CRC_ERR must mirror RESP_ERR_IRQ set"
    )

    # SDIO_IRQ follows CTRL1 SDIO_IRQ (copy, not sticky)
    await machine.writel(SSP1_BASE + 0x060, sdio_irq_set)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & sdio_irq_bit) == sdio_irq_bit, (
        f"SSP SDIO_IRQ status must follow CTRL1 SDIO_IRQ set"
    )
    await machine.writel(SSP1_BASE + 0x068, sdio_irq_clear)
    status = await machine.readl(SSP1_BASE + 0x0C0)
    assert (status & sdio_irq_bit) == 0, (
        f"SSP SDIO_IRQ status must clear when CTRL1 SDIO_IRQ is cleared"
    )
