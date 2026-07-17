import pytest

from framework.constants import APBX_BASE, ICOLL_BASE
from helpers.dma import write_descriptor

I2C_BASE = 0x80058000


@pytest.mark.asyncio
async def test_i2c_register_contract(machine):
    """I2C register contract"""
    assert (await machine.readl(I2C_BASE + 0x000)) == 0xC0000000, (
        f"I2C CTRL0 must reset with SFTRST and CLKGATE asserted"
    )
    assert (await machine.readl(I2C_BASE + 0x010)) == 0x00780030, (
        f"I2C TIMING0 must occupy 0x10 and expose its documented reset value"
    )
    assert (await machine.readl(I2C_BASE + 0x020)) == 0x00800030, (
        f"I2C TIMING1 must occupy 0x20 and expose its documented reset value"
    )
    assert (await machine.readl(I2C_BASE + 0x030)) == 0x00300030, (
        f"I2C TIMING2 must occupy 0x30 and expose its documented reset value"
    )
    assert (await machine.readl(I2C_BASE + 0x040)) == 0x00860000, (
        f"I2C CTRL1 must occupy 0x40 and reset with slave address byte 0x86"
    )
    assert (await machine.readl(I2C_BASE + 0x050)) == 0xC0000000, (
        f"I2C STAT must expose fixed master and slave presence bits"
    )
    assert (await machine.readl(I2C_BASE + 0x070)) == 0x00100000, (
        f"I2C DEBUG0 must expose the documented reset DMA state"
    )
    assert (await machine.readl(I2C_BASE + 0x080)) == 0xC0000000, (
        f"I2C DEBUG1 must expose idle-high pad inputs after reset"
    )
    assert (await machine.readl(I2C_BASE + 0x090)) == 0x01010000, (
        f"I2C VERSION must be v1.1 at its documented offset"
    )

    for offset in [0x010, 0x020, 0x030]:
        await machine.writel(I2C_BASE + offset, 0xFFFFFFFF)
        assert (await machine.readl(I2C_BASE + offset)) == 0x03FF03FF, (
            f"I2C timing register at 0x{offset:x} must ignore reserved bits"
        )

    await machine.writel(I2C_BASE + 0x040, 0xFFFFFFFF)
    assert (await machine.readl(I2C_BASE + 0x040)) == 0x01FFFFFF, (
        f"I2C CTRL1 must retain only documented status, enable, and slave-address fields"
    )
    assert (await machine.readl(I2C_BASE + 0x050)) == 0xE00000FF, (
        f"I2C STAT must summarize all enabled CTRL1 interrupt requests and reject writes"
    )
    raw0 = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw0 & (1 << 27)) != 0, (
        f"enabled I2C controller status must assert the I2C error/line-condition source"
    )
    assert (raw0 & (1 << 26)) == 0, (
        f"I2C controller status must not assert the APBX-owned I2C DMA source"
    )
    await machine.writel(I2C_BASE + 0x050, 0)
    assert (await machine.readl(I2C_BASE + 0x050)) == 0xE00000FF, (
        f"I2C STAT must be read-only"
    )

    await machine.writel(I2C_BASE + 0x060, 0x11223344)
    assert (await machine.readl(I2C_BASE + 0x060)) == 0x11223344, (
        f"I2C DATA must remain read/write at its documented base address"
    )
    await machine.writel(I2C_BASE + 0x064, 0x55667788)
    assert (await machine.readl(I2C_BASE + 0x060)) == 0x11223344, (
        f"I2C DATA must not decode undocumented SCT aliases"
    )

    await machine.writel(I2C_BASE + 0x070, 0xFFFFFFFF)
    assert (await machine.readl(I2C_BASE + 0x070)) == 0x1C100800, (
        f"I2C DEBUG0 must retain only TESTMODE and documented test fields"
    )
    await machine.writel(I2C_BASE + 0x080, 0xFFFFFFFF)
    assert (await machine.readl(I2C_BASE + 0x080)) == 0xC000073F, (
        f"I2C DEBUG1 must preserve input and reserved fields while retaining controls"
    )
    await machine.writel(I2C_BASE + 0x090, 0)
    assert (await machine.readl(I2C_BASE + 0x090)) == 0x01010000, (
        f"I2C VERSION must be read-only"
    )

    await machine.writel(I2C_BASE + 0x004, 0x80000000)
    assert (await machine.readl(I2C_BASE + 0x000)) == 0xC0000000, (
        f"I2C SFTRST must reset the block and automatically gate its clock"
    )
    assert (await machine.readl(I2C_BASE + 0x040)) == 0x00860000, (
        f"I2C SFTRST must restore CTRL1 reset state"
    )


@pytest.mark.asyncio
async def test_i2c_data_engine_complete_irq_contract(machine):
    """I2C data engine complete IRQ contract"""
    ctrl1_set = I2C_BASE + 0x044
    ctrl0_clr = I2C_BASE + 0x008
    ctrl0_set = I2C_BASE + 0x004

    await machine.writel(ctrl0_clr, 0xC0000000)
    await machine.writel(ctrl1_set, 0x00004000)
    await machine.writel(ctrl0_set, 0x20000001)

    await machine.clock_step(100_000)

    stat = await machine.readl(I2C_BASE + 0x050)
    assert (stat & (1 << 6)) != 0, (
        f"I2C DATA_ENGINE_CMPLT_IRQ must be summarized in STAT after RUN completes"
    )
    assert ((await machine.readl(I2C_BASE + 0x000)) & (1 << 29)) == 0, (
        f"I2C RUN must self-clear on completion"
    )
    raw0 = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw0 & (1 << 27)) != 0, (
        f"I2C DATA_ENGINE_CMPLT_IRQ must assert ICOLL source 27 when enabled"
    )


@pytest.mark.asyncio
async def test_i2c_dma_irq_ownership_contract(machine):
    """I2C DMA IRQ ownership contract"""
    descriptor = 0x00000400
    channel3_nxtcmdar = APBX_BASE + 0x1A0
    channel3_sema = APBX_BASE + 0x1D0

    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x014, 1 << 11)
    await write_descriptor(machine, descriptor, 0, (1 << 6) | (1 << 3), 0, 0)
    await machine.writel(channel3_nxtcmdar, descriptor)
    await machine.writel(channel3_sema, 1)
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 26)) != 0, (
        f"APBX channel 3 completion must assert the Table 38 I2C DMA source"
    )

    await machine.writel(I2C_BASE + 0x040, 0)
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 26)) != 0, (
        f"I2C device status writes must not clear the APBX-owned I2C DMA source"
    )


@pytest.mark.asyncio
async def test_i2c_dma_fifo_contract(machine):
    """I2C DMA FIFO data contract"""
    descriptor = 0x00000500
    buffer = 0x00001000
    channel3_nxtcmdar = APBX_BASE + 0x1A0
    channel3_sema = APBX_BASE + 0x1D0

    cmd = (
        (6 << 16) |  # XFER_COUNT
        (1 << 12) |  # CMDWORDS
        (1 << 7) |   # WAIT4ENDCMD
        (1 << 6) |   # SEMAPHORE
        (1 << 3) |   # IRQONCMPLT
        2            # DMA_READ
    )
    pio = (
        (1 << 29) |  # RUN
        (1 << 20) |  # POST_SEND_STOP
        (1 << 19) |  # PRE_SEND_START
        (1 << 17) |  # MASTER_MODE
        (1 << 16) |  # DIRECTION: TRANSMIT
        6            # XFER_COUNT
    )

    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x014, 1 << 11)
    await machine.writel(I2C_BASE + 0x044, 0x00004000)

    await machine.writel(buffer + 0x00, 0x03020156)
    await machine.writel(buffer + 0x04, 0x00000504)

    await write_descriptor(machine, descriptor, 0, cmd, buffer, pio)

    await machine.writel(channel3_nxtcmdar, descriptor)
    await machine.writel(channel3_sema, 1)

    await machine.clock_step(100_000)

    assert (await machine.readl(channel3_sema)) == 0, (
        f"APBX I2C channel semaphore must be decremented on completion"
    )
    assert ((await machine.readl(APBX_BASE + 0x010)) & (1 << 3)) == (1 << 3), (
        f"APBX channel 3 CMDCMPLT status must be set"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 26)) != 0, (
        f"APBX I2C DMA completion must assert ICOLL source 26"
    )

    assert ((await machine.readl(I2C_BASE + 0x000)) & (1 << 29)) == 0, (
        f"I2C RUN must be cleared after the DMA transfer completes"
    )
    assert ((await machine.readl(I2C_BASE + 0x040)) & (1 << 6)) == (1 << 6), (
        f"I2C DATA_ENGINE_CMPLT_IRQ must be set"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 27)) != 0, (
        f"I2C DATA_ENGINE_CMPLT_IRQ must assert ICOLL source 27"
    )
    assert ((await machine.readl(I2C_BASE + 0x050)) & (1 << 6)) == (1 << 6), (
        f"I2C STAT must summarize the DATA_ENGINE_CMPLT_IRQ"
    )


@pytest.mark.asyncio
async def test_i2c_master_write_read_contract(machine):
    """I2C master write-read contract"""
    i2c_data = I2C_BASE + 0x060
    i2c_ctrl0 = I2C_BASE + 0x000
    i2c_ctrl1_set = I2C_BASE + 0x044
    i2c_ctrl1 = I2C_BASE + 0x040
    i2c_stat = I2C_BASE + 0x050

    # Enable DATA_ENGINE_CMPLT, BUS_FREE and NO_SLAVE_ACK IRQs.
    await machine.writel(i2c_ctrl1_set, 0x0000E000)
    # Clear SFTRST/CLKGATE.
    await machine.writel(I2C_BASE + 0x008, 0xC0000000)

    # Write to SMBus EEPROM at 0x50: offset 0x00, data 0xAA.
    await machine.writeb(i2c_data, 0xA0)
    await machine.writeb(i2c_data, 0x00)
    await machine.writeb(i2c_data, 0xAA)
    ctrl0_write = (
        (1 << 29) |  # RUN
        (1 << 20) |  # POST_SEND_STOP
        (1 << 19) |  # PRE_SEND_START
        (1 << 17) |  # MASTER_MODE
        (1 << 16) |  # DIRECTION: TRANSMIT
        3            # XFER_COUNT
    )
    await machine.writel(i2c_ctrl0, ctrl0_write)
    await machine.clock_step(300_000)

    ctrl1_after_write = await machine.readl(i2c_ctrl1)
    assert (ctrl1_after_write & (1 << 6)) == (1 << 6), (
        f"I2C write DATA_ENGINE_CMPLT_IRQ must be set"
    )
    assert (ctrl1_after_write & (1 << 7)) == (1 << 7), (
        f"I2C write BUS_FREE_IRQ must be set after STOP"
    )

    # Load the EEPROM offset for the subsequent read (no STOP).
    await machine.writeb(i2c_data, 0xA0)
    await machine.writeb(i2c_data, 0x00)
    ctrl0_load_offset = (
        (1 << 29) |  # RUN
        (1 << 19) |  # PRE_SEND_START
        (1 << 17) |  # MASTER_MODE
        (1 << 16) |  # DIRECTION: TRANSMIT
        2            # XFER_COUNT
    )
    await machine.writel(i2c_ctrl0, ctrl0_load_offset)
    await machine.clock_step(200_000)

    ctrl1_after_offset = await machine.readl(i2c_ctrl1)
    assert (ctrl1_after_offset & (1 << 6)) == (1 << 6), (
        f"I2C offset-load DATA_ENGINE_CMPLT_IRQ must be set"
    )

    # Repeated start: send read address and retain the clock.
    await machine.writeb(i2c_data, 0xA1)
    ctrl0_read_addr = (
        (1 << 29) |  # RUN
        (1 << 21) |  # RETAIN_CLOCK
        (1 << 19) |  # PRE_SEND_START
        (1 << 17) |  # MASTER_MODE
        (1 << 16) |  # DIRECTION: TRANSMIT
        1            # XFER_COUNT
    )
    await machine.writel(i2c_ctrl0, ctrl0_read_addr)
    await machine.clock_step(100_000)

    ctrl1_after_addr = await machine.readl(i2c_ctrl1)
    assert (ctrl1_after_addr & (1 << 6)) == (1 << 6), (
        f"I2C read-address DATA_ENGINE_CMPLT_IRQ must be set"
    )

    # Receive one byte with NACK and STOP.
    ctrl0_read_data = (
        (1 << 29) |  # RUN
        (1 << 25) |  # SEND_NAK_ON_LAST
        (1 << 20) |  # POST_SEND_STOP
        (1 << 17) |  # MASTER_MODE
        1            # XFER_COUNT
    )
    await machine.writel(i2c_ctrl0, ctrl0_read_data)
    await machine.clock_step(100_000)

    rx_data = await machine.readl(i2c_data)
    assert (rx_data & 0xFF) == 0xAA, (
        f"I2C read must return the previously written byte"
    )

    stat = await machine.readl(i2c_stat)
    assert (stat & (1 << 6)) == (1 << 6), (
        f"I2C STAT must summarize DATA_ENGINE_CMPLT_IRQ"
    )
    assert (stat & (1 << 7)) == (1 << 7), (
        f"I2C STAT must summarize BUS_FREE_IRQ"
    )


@pytest.mark.asyncio
async def test_i2c_no_slave_ack_contract(machine):
    """I2C no slave NACK contract"""
    i2c_data = I2C_BASE + 0x060
    i2c_ctrl0 = I2C_BASE + 0x000
    i2c_ctrl1_set = I2C_BASE + 0x044
    i2c_ctrl1 = I2C_BASE + 0x040

    # Enable NO_SLAVE_ACK and DATA_ENGINE_CMPLT IRQs.
    await machine.writel(i2c_ctrl1_set, 0x00006000)
    # Clear SFTRST/CLKGATE.
    await machine.writel(I2C_BASE + 0x008, 0xC0000000)

    # Address 0x40 (write) has no slave on the bus.
    await machine.writeb(i2c_data, 0x80)
    ctrl0 = (
        (1 << 29) |  # RUN
        (1 << 20) |  # POST_SEND_STOP
        (1 << 19) |  # PRE_SEND_START
        (1 << 17) |  # MASTER_MODE
        (1 << 16) |  # DIRECTION: TRANSMIT
        1            # XFER_COUNT
    )
    await machine.writel(i2c_ctrl0, ctrl0)
    await machine.clock_step(100_000)

    ctrl1 = await machine.readl(i2c_ctrl1)
    assert (ctrl1 & (1 << 5)) == (1 << 5), (
        f"I2C NO_SLAVE_ACK_IRQ must be set for missing slave"
    )
    assert (ctrl1 & (1 << 6)) == (1 << 6), (
        f"I2C DATA_ENGINE_CMPLT_IRQ must be set on NACK"
    )


@pytest.mark.asyncio
async def test_i2c_slave_local_test_contract(machine):
    """I2C slave local test contract"""
    i2c_ctrl0 = I2C_BASE + 0x000
    i2c_ctrl1_set = I2C_BASE + 0x044
    i2c_ctrl1 = I2C_BASE + 0x040
    i2c_stat = I2C_BASE + 0x050
    i2c_debug0 = I2C_BASE + 0x070
    i2c_debug1 = I2C_BASE + 0x080

    # Clear SFTRST/CLKGATE and enable slave interrupts.
    await machine.writel(I2C_BASE + 0x008, 0xC0000000)
    await machine.writel(i2c_ctrl1_set, 0x00000300)
    # Enable slave address decoder.
    await machine.writel(i2c_ctrl0, (1 << 18))

    # Trigger LOCAL_SLAVE_TEST in MY_WRITE mode (default address 0x86).
    await machine.writel(i2c_debug1, (1 << 8) | (1 << 9))

    stat_after_match = await machine.readl(i2c_stat)
    assert (stat_after_match & (1 << 14)) != 0, (
        f"I2C SLAVE_FOUND must be set after LOCAL_SLAVE_TEST match"
    )
    assert ((stat_after_match >> 16) & 0xFF) == 0x86, (
        f"I2C RCVD_SLAVE_ADDR must match the programmed slave address"
    )
    assert (stat_after_match & (1 << 8)) != 0, (
        f"I2C SLAVE_BUSY must be set after LOCAL_SLAVE_TEST match"
    )

    debug0_after_match = await machine.readl(i2c_debug0)
    assert (debug0_after_match & (1 << 10)) != 0, (
        f"I2C SLAVE_HOLD_CLK must be set after LOCAL_SLAVE_TEST match"
    )
    assert (debug0_after_match & 0x3FF) == 2, (
        f"I2C SLAVE_STATE must be FOUND after LOCAL_SLAVE_TEST match"
    )

    ctrl1_after_match = await machine.readl(i2c_ctrl1)
    assert (ctrl1_after_match & (1 << 0)) != 0, (
        f"I2C SLAVE_IRQ must be set after LOCAL_SLAVE_TEST match"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 27)) != 0, (
        f"I2C SLAVE_IRQ must assert ICOLL source 27 when enabled"
    )

    # Clear LOCAL_SLAVE_TEST to simulate a stop condition.
    await machine.writel(i2c_debug1, 0x00000000)

    stat_after_stop = await machine.readl(i2c_stat)
    assert (stat_after_stop & (1 << 14)) == 0, (
        f"I2C SLAVE_FOUND must be cleared after LOCAL_SLAVE_TEST cleared"
    )
    assert (stat_after_stop & (1 << 1)) != 0, (
        f"I2C SLAVE_STOP_IRQ must be summarized in STAT after LOCAL_SLAVE_TEST cleared"
    )

    ctrl1_after_stop = await machine.readl(i2c_ctrl1)
    assert (ctrl1_after_stop & (1 << 1)) != 0, (
        f"I2C SLAVE_STOP_IRQ must be set after LOCAL_SLAVE_TEST cleared"
    )


@pytest.mark.asyncio
async def test_i2c_fifo_threshold_contract(machine):
    """I2C FIFO DMAREQ threshold contract"""
    i2c_ctrl0 = I2C_BASE + 0x000
    i2c_ctrl1_set = I2C_BASE + 0x044
    i2c_debug0 = I2C_BASE + 0x070
    i2c_stat = I2C_BASE + 0x050

    # Clear SFTRST/CLKGATE and enable completion interrupt.
    await machine.writel(I2C_BASE + 0x008, 0xC0000000)
    await machine.writel(i2c_ctrl1_set, 0x00004000)

    # Run a receive of 8 bytes from an empty bus (no external slave).
    await machine.writel(i2c_ctrl0, (1 << 29) | 8)
    # Wait for four bytes to be received (half the FIFO depth).
    await machine.clock_step(400_000)

    debug0 = await machine.readl(i2c_debug0)
    assert (debug0 & (1 << 31)) != 0, (
        f"I2C DMAREQ must be set when FIFO reaches half threshold"
    )

    stat = await machine.readl(i2c_stat)
    assert (stat & (1 << 9)) != 0, (
        f"I2C DATA_ENGINE_BUSY must be set during FIFO threshold test"
    )
    assert (stat & (1 << 12)) == 0, (
        f"I2C DATA_ENGINE_DMA_WAIT must not be set at half threshold"
    )

    # Drain the FIFO and check DMAREQ drops.
    await machine.readl(I2C_BASE + 0x060)
    debug0_after_drain = await machine.readl(i2c_debug0)
    assert (debug0_after_drain & (1 << 31)) == 0, (
        f"I2C DMAREQ must drop when FIFO falls below half threshold"
    )

    # Let the remaining four bytes complete the transfer.
    await machine.clock_step(1_000_000)
    assert ((await machine.readl(i2c_ctrl0)) & (1 << 29)) == 0, (
        f"I2C RUN must self-clear after completion"
    )
    assert ((await machine.readl(I2C_BASE + 0x040)) & (1 << 6)) != 0, (
        f"I2C DATA_ENGINE_CMPLT_IRQ must be set after completion"
    )
