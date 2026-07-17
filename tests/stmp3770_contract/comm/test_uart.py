import pytest

from framework.constants import APBX_BASE, ICOLL_BASE, APPUART_BASE, DBGUART_BASE
from helpers.dma import write_descriptor


@pytest.mark.asyncio
async def test_app_uart_register_contract(machine):
    """Application UART register contract"""
    assert (await machine.readl(APPUART_BASE + 0x000)) == 0xC0030000, (
        f"UARTAPP CTRL0 must reset with SFTRST, CLKGATE, and RXTIMEOUT=3"
    )
    assert (await machine.readl(APPUART_BASE + 0x010)) == 0, (
        f"UARTAPP CTRL1 must reset with no TX DMA command pending"
    )
    assert (await machine.readl(APPUART_BASE + 0x020)) == 0x00220300, (
        f"UARTAPP CTRL2 must reset with both FIFOs half-level and RX/TX enabled"
    )
    assert (await machine.readl(APPUART_BASE + 0x070)) == 0xC9F00000, (
        f"UARTAPP STAT must reset with present/high-speed, empty FIFOs, and four invalid RX bytes"
    )
    assert (await machine.readl(APPUART_BASE + 0x080)) == 0, (
        f"UARTAPP DEBUG must reset with all DMA signal state low"
    )
    assert (await machine.readl(APPUART_BASE + 0x090)) == 0x02000000, (
        f"UARTAPP VERSION must report block v2.0"
    )

    await machine.writel(APPUART_BASE + 0x010, 0xFFFFFFFF)
    assert (await machine.readl(APPUART_BASE + 0x010)) == 0x1000FFFF, (
        f"UARTAPP CTRL1 must retain only RUN and XFER_COUNT"
    )
    await machine.writel(APPUART_BASE + 0x020, 0xFFFFFFFF)
    assert (await machine.readl(APPUART_BASE + 0x020)) == 0xFF77FFC7, (
        f"UARTAPP CTRL2 must ignore its documented reserved fields"
    )
    await machine.writel(APPUART_BASE + 0x030, 0xFFFFFFFF)
    assert (await machine.readl(APPUART_BASE + 0x030)) == 0xFFFF3FFF, (
        f"UARTAPP LINECTRL must retain only its documented baud and framing fields"
    )
    await machine.writel(APPUART_BASE + 0x040, 0xFFFFFFFF)
    assert (await machine.readl(APPUART_BASE + 0x040)) == 0xFFFF3FFE, (
        f"UARTAPP LINECTRL2 must retain its documented fields and reject BRK"
    )
    await machine.writel(APPUART_BASE + 0x050, 0xFFFFFFFF)
    assert (await machine.readl(APPUART_BASE + 0x050)) == 0x07FF07FF, (
        f"UARTAPP INTR must retain only documented enable and status bits"
    )
    raw0 = await machine.readl(ICOLL_BASE + 0x040)
    assert (raw0 & (1 << 24)) != 0, (
        f"enabled UARTAPP interrupt status must assert ICOLL source 24"
    )
    assert (raw0 & ((1 << 23) | (1 << 25))) == 0, (
        f"UARTAPP device status must not assert APBX-owned TX/RX DMA sources"
    )

    await machine.writel(APPUART_BASE + 0x004, 0x80000000)
    assert (await machine.readl(APPUART_BASE + 0x000)) == 0xC0030000, (
        f"UARTAPP SFTRST must restore the block reset state and gate clocks"
    )


@pytest.mark.asyncio
async def test_app_uart_fifo_ifls_contract(machine):
    """Application UART FIFO IFLS threshold contract"""
    await machine.writel(APPUART_BASE + 0x030, 0x10)
    await machine.writel(APPUART_BASE + 0x020, 0x00220381)
    await machine.writel(APPUART_BASE + 0x050, 0x00200020)

    assert (await machine.readl(APPUART_BASE + 0x050)) == 0x00200020, (
        f"UARTAPP TXIS must be set when TX FIFO is empty below the default threshold"
    )

    await machine.writel(APPUART_BASE + 0x060, 0x5A)
    assert (await machine.readl(APPUART_BASE + 0x050)) == 0x00200020, (
        f"UARTAPP TXIS must remain the only active status after the first four bytes"
    )

    await machine.writel(APPUART_BASE + 0x060, 0x5A)
    assert (await machine.readl(APPUART_BASE + 0x050)) == 0x00200030, (
        f"UARTAPP RXIS must be set when RX FIFO reaches the half-level threshold"
    )

    assert (await machine.readl(APPUART_BASE + 0x060)) == 0x0000005A, (
        f"UARTAPP LBE must return the looped-back TX data on DATA read"
    )
    assert (await machine.readl(APPUART_BASE + 0x050)) == 0x00200020, (
        f"UARTAPP RXIS must clear after RX FIFO drops below the half-level threshold"
    )

    await machine.writel(APPUART_BASE + 0x020, 0x00000381)
    assert (await machine.readl(APPUART_BASE + 0x050)) == 0x00200030, (
        f"UARTAPP RXIS and TXIS must both be set at the one-eighth threshold"
    )


@pytest.mark.asyncio
async def test_app_uart_dma_fifo_contract(machine):
    """Application UART DMA FIFO data contract"""
    tx_descriptor = 0x00000600
    rx_descriptor = 0x00000620
    tx_buffer = 0x00001000
    rx_buffer = 0x00001010
    ch7_nxtcmdar = APBX_BASE + 0x360
    ch7_sema = APBX_BASE + 0x390
    ch6_nxtcmdar = APBX_BASE + 0x2F0
    ch6_sema = APBX_BASE + 0x320

    tx_cmd = (
        (4 << 16) |  # XFER_COUNT
        (1 << 12) |  # CMDWORDS
        (1 << 7) |   # WAIT4ENDCMD
        (1 << 6) |   # SEMAPHORE
        (1 << 3) |   # IRQONCMPLT
        2            # DMA_READ
    )
    tx_pio = (1 << 28) | 4  # RUN + XFER_COUNT

    rx_cmd = (
        (4 << 16) |  # XFER_COUNT
        (1 << 12) |  # CMDWORDS
        (1 << 7) |   # WAIT4ENDCMD
        (1 << 6) |   # SEMAPHORE
        (1 << 3) |   # IRQONCMPLT
        1            # DMA_WRITE
    )
    rx_pio = (1 << 29) | 4  # RUN + XFER_COUNT

    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x014, 0x0000C000)

    await machine.writel(APPUART_BASE + 0x030, 0x10)
    await machine.writel(APPUART_BASE + 0x020, 0x00220381)

    await machine.writel(tx_buffer, 0x05040302)
    await write_descriptor(machine, tx_descriptor, 0, tx_cmd, tx_buffer, tx_pio)

    await write_descriptor(machine, rx_descriptor, 0, rx_cmd, rx_buffer, rx_pio)

    await machine.writel(ch7_nxtcmdar, tx_descriptor)
    await machine.writel(ch7_sema, 1)

    assert (await machine.readl(ch7_sema)) == 0, (
        f"APBX UART TX channel semaphore must be decremented on completion"
    )
    assert ((await machine.readl(APBX_BASE + 0x010)) & (1 << 7)) == (1 << 7), (
        f"APBX UART TX channel CMDCMPLT status must be set"
    )

    await machine.writel(ch6_nxtcmdar, rx_descriptor)
    await machine.writel(ch6_sema, 1)

    assert (await machine.readl(ch6_sema)) == 0, (
        f"APBX UART RX channel semaphore must be decremented on completion"
    )
    assert ((await machine.readl(APBX_BASE + 0x010)) & (1 << 6)) == (1 << 6), (
        f"APBX UART RX channel CMDCMPLT status must be set"
    )

    assert (await machine.readl(rx_buffer)) == 0x05040302, (
        f"APBX UART RX DMA must read back the looped-back TX bytes"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 23)) != 0, (
        f"APBX UART TX DMA completion must assert ICOLL source 23"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 25)) != 0, (
        f"APBX UART RX DMA completion must assert ICOLL source 25"
    )


@pytest.mark.asyncio
async def test_app_uart_serial_timing_contract(machine):
    """Application UART serial timing contract"""
    # LINECTRL: FEN=1, WLEN=3 (8 bits), BAUD_DIVINT=3, BAUD_DIVFRAC=44
    # divisor = 3*64 + 44 = 0xEC (3.25 Mbit/s from 24 MHz UARTCLK)
    await machine.writel(APPUART_BASE + 0x030, 0x00032C70)
    await machine.writel(APPUART_BASE + 0x020, 0x00000381)
    await machine.writel(APPUART_BASE + 0x050, 0x00300000)

    assert ((await machine.readl(APPUART_BASE + 0x070)) & (1 << 29)) == 0, (
        f"UARTAPP STAT.BUSY must be low when idle"
    )

    await machine.writel(APPUART_BASE + 0x060, 0x0000005A)
    assert ((await machine.readl(APPUART_BASE + 0x070)) & (1 << 29)) != 0, (
        f"UARTAPP STAT.BUSY must be high after a DATA write"
    )
    assert (await machine.readl(APPUART_BASE + 0x060)) == 0, (
        f"UARTAPP DATA must be empty before the first byte-time"
    )

    await machine.clock_step(5000)
    assert (await machine.readl(APPUART_BASE + 0x060)) == 0x0000005A, (
        f"UARTAPP LBE data must be received after one byte-time"
    )
    assert ((await machine.readl(APPUART_BASE + 0x070)) & (1 << 29)) != 0, (
        f"UARTAPP STAT.BUSY must remain high while TX FIFO is not empty"
    )

    await machine.clock_step(15000)
    assert ((await machine.readl(APPUART_BASE + 0x070)) & (1 << 29)) == 0, (
        f"UARTAPP STAT.BUSY must be low after TX FIFO is empty"
    )
    assert ((await machine.readl(APPUART_BASE + 0x050)) & 0x30) == 0x30, (
        f"UARTAPP TXIS and RXIS must be set once transmission completes"
    )


@pytest.mark.asyncio
async def test_debug_uart_register_contract(machine):
    """Debug UART register contract"""
    # After ROM boot init, CR is 0x301 (UARTEN|TXE|RXE) and IBRD/FBRD/LCR_H
    # are configured for 115200 baud.  The RW mask test below still works
    # because writing 0xffffffff masks to the writable bits.
    assert (await machine.readl(DBGUART_BASE + 0x030)) == 0x00000301, (
        f"UARTDBG CR must reflect ROM boot init (UARTEN|TXE|RXE)"
    )
    assert (await machine.readl(DBGUART_BASE + 0x034)) == 0x00000012, (
        f"UARTDBG IFLS must reset both FIFO levels to half"
    )

    await machine.writel(DBGUART_BASE + 0x030, 0xFFFFFFFF)
    assert (await machine.readl(DBGUART_BASE + 0x030)) == 0x0000FFC7, (
        f"UARTDBG CR must reject unavailable and reserved bits"
    )
    await machine.writel(DBGUART_BASE + 0x034, 0xFFFFFFFF)
    assert (await machine.readl(DBGUART_BASE + 0x034)) == 0x0000003F, (
        f"UARTDBG IFLS must expose only RX/TX FIFO level fields"
    )
    await machine.writel(DBGUART_BASE + 0x038, 0xFFFFFFFF)
    assert (await machine.readl(DBGUART_BASE + 0x038)) == 0x000007FF, (
        f"UARTDBG IMSC must expose only documented interrupt masks"
    )
    await machine.writel(DBGUART_BASE + 0x048, 0xFFFFFFFF)
    assert (await machine.readl(DBGUART_BASE + 0x048)) == 0x00000007, (
        f"UARTDBG DMACR must expose only RXDMAE, TXDMAE, and DMAONERR"
    )

    await machine.writel(DBGUART_BASE + 0x030, 0x00000381)
    # Clear IBRD/FBRD so byte_time=0 and LBE loopback is synchronous
    await machine.writel(DBGUART_BASE + 0x024, 0x00000000)
    await machine.writel(DBGUART_BASE + 0x028, 0x00000000)
    await machine.writel(DBGUART_BASE + 0x000, 0x0000005A)
    assert (await machine.readl(DBGUART_BASE + 0x000)) == 0x0000005A, (
        f"UARTDBG LBE must feed normal-mode transmitted data back to the receive FIFO"
    )


@pytest.mark.asyncio
async def test_debug_uart_fifo_ifls_contract(machine):
    """Debug UART FIFO IFLS threshold contract"""
    await machine.writel(DBGUART_BASE + 0x030, 0x00000381)
    # Clear IBRD/FBRD so byte_time=0 and LBE loopback is synchronous
    await machine.writel(DBGUART_BASE + 0x024, 0x00000000)
    await machine.writel(DBGUART_BASE + 0x028, 0x00000000)
    await machine.writel(DBGUART_BASE + 0x02C, 0x00000010)
    await machine.writel(DBGUART_BASE + 0x034, 0x0000000A)
    await machine.writel(DBGUART_BASE + 0x038, 0x00000030)

    assert (await machine.readl(DBGUART_BASE + 0x040)) == 0x00000020, (
        f"UARTDBG MIS must reflect TXRIS only while RX FIFO is below one-quarter"
    )

    await machine.writel(DBGUART_BASE + 0x000, 0x00000041)
    await machine.writel(DBGUART_BASE + 0x000, 0x00000042)
    await machine.writel(DBGUART_BASE + 0x000, 0x00000043)
    assert (await machine.readl(DBGUART_BASE + 0x040)) == 0x00000020, (
        f"UARTDBG MIS must still reflect only TXRIS with three RX entries"
    )

    await machine.writel(DBGUART_BASE + 0x000, 0x00000044)
    assert (await machine.readl(DBGUART_BASE + 0x040)) == 0x00000030, (
        f"UARTDBG MIS must set RXRIS once one-quarter FIFO threshold is reached"
    )

    await machine.writel(DBGUART_BASE + 0x044, 0x00000030)
    assert (await machine.readl(DBGUART_BASE + 0x03C)) == 0x00000030, (
        f"UARTDBG RIS must reassert RXRIS while RX FIFO remains at one-quarter"
    )

    await machine.readl(DBGUART_BASE + 0x000)
    assert (await machine.readl(DBGUART_BASE + 0x040)) == 0x00000020, (
        f"UARTDBG MIS must clear RXRIS once RX FIFO drops below one-quarter"
    )

    await machine.writel(DBGUART_BASE + 0x034, 0x00000000)
    await machine.writel(DBGUART_BASE + 0x044, 0x00000030)
    await machine.writel(DBGUART_BASE + 0x000, 0x00000055)
    assert (await machine.readl(DBGUART_BASE + 0x040)) == 0x00000030, (
        f"UARTDBG MIS must set RXRIS immediately at RXIFLSEL=NOT_EMPTY"
    )


@pytest.mark.asyncio
async def test_debug_uart_serial_timing_contract(machine):
    """Debug UART serial timing contract"""
    # CR: UARTEN, TXE, RXE, LBE; LCR_H: FEN, WLEN=3 (8 bits)
    # IBRD=1, FBRD=0 => 24 MHz / (16 * 1) = 1.5 Mbit/s, byte ~6.7 us
    await machine.writel(DBGUART_BASE + 0x030, 0x00000381)
    await machine.writel(DBGUART_BASE + 0x02C, 0x00000070)
    await machine.writel(DBGUART_BASE + 0x024, 0x00000001)
    await machine.writel(DBGUART_BASE + 0x028, 0x00000000)
    await machine.writel(DBGUART_BASE + 0x034, 0x00000000)
    await machine.writel(DBGUART_BASE + 0x038, 0x00000030)

    assert ((await machine.readl(DBGUART_BASE + 0x018)) & (1 << 3)) == 0, (
        f"UARTDBG FR.BUSY must be low when idle"
    )

    await machine.writel(DBGUART_BASE + 0x000, 0x00000055)
    assert ((await machine.readl(DBGUART_BASE + 0x018)) & (1 << 3)) != 0, (
        f"UARTDBG FR.BUSY must be high after a DR write"
    )
    assert (await machine.readl(DBGUART_BASE + 0x000)) == 0, (
        f"UARTDBG DR must be empty before the first byte-time"
    )

    await machine.clock_step(10000)
    assert ((await machine.readl(DBGUART_BASE + 0x040)) & 0x30) == 0x30, (
        f"UARTDBG MIS must reflect TXRIS and RXRIS once transmission completes"
    )
    assert (await machine.readl(DBGUART_BASE + 0x000)) == 0x00000055, (
        f"UARTDBG LBE data must be received after one byte-time"
    )
    assert ((await machine.readl(DBGUART_BASE + 0x018)) & (1 << 3)) == 0, (
        f"UARTDBG FR.BUSY must be low after TX completes"
    )
