import pytest

from framework.constants import APBH_BASE, APBX_BASE, SRAM_BASE
from helpers.dma import DMA_IRQONCMPLT, DMA_SEMAPHORE, write_descriptor


@pytest.mark.asyncio
async def test_dma_ctrl1_and_devsel_contract(machine):
    """DMA CTRL1 and DEVSEL writable mask contract"""
    await machine.writel(APBH_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x008, 0xC0000000)

    await machine.writel(APBH_BASE + 0x010, 0xFFFFFFFF)
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert ctrl1 == 0x00FFFFFF, (
        f"APBH CTRL1 must not accept writes to RSVD bits 31:24: got 0x{ctrl1:x}"
    )

    await machine.writel(APBH_BASE + 0x018, 0x00FFFFFF)
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert ctrl1 == 0, (
        f"APBH CTRL1 CLR must clear all writable bits: got 0x{ctrl1:x}"
    )

    await machine.writel(APBH_BASE + 0x014, 1 << 16)
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert (ctrl1 & (1 << 16)) == (1 << 16), (
        f"APBH CTRL1 SET must be able to set CH0_AHB_ERROR_IRQ: ctrl1=0x{ctrl1:x}"
    )
    await machine.writel(APBH_BASE + 0x018, 1 << 16)

    await machine.writel(APBH_BASE + 0x020, 0xFFFFFFFF)
    devsel = await machine.readl(APBH_BASE + 0x020)
    assert devsel == 0, (
        f"APBH DEVSEL must be entirely read-only: got 0x{devsel:x}"
    )

    await machine.writel(APBX_BASE + 0x020, 0xFFFFFFFF)
    apbx_devsel = await machine.readl(APBX_BASE + 0x020)
    assert apbx_devsel == 0xFF000F00, (
        f"APBX DEVSEL must only accept writes to CH7/CH6/CH2 fields: got 0x{apbx_devsel:x}"
    )

    await machine.writel(APBX_BASE + 0x028, 0xFFFFFFFF)
    apbx_devsel = await machine.readl(APBX_BASE + 0x020)
    assert apbx_devsel == 0, (
        f"APBX DEVSEL CLR must clear all writable fields: got 0x{apbx_devsel:x}"
    )

    await machine.writel(APBX_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x000, 0x0000FF00)
    ctrl0 = await machine.readl(APBX_BASE + 0x000)
    assert (ctrl0 & 0x0000FF00) == 0, (
        f"APBX CTRL0 bits 15:8 (CLKGATE_CHANNEL) must be read-only: ctrl0=0x{ctrl0:x}"
    )

    await machine.writel(APBH_BASE + 0x008, 0xC0000000)
    await machine.writel(APBH_BASE + 0x000, 0x0000FF00)
    ctrl0 = await machine.readl(APBH_BASE + 0x000)
    assert (ctrl0 & 0x0000FF00) != 0, (
        f"APBH CTRL0 bits 15:8 (CLKGATE_CHANNEL) must be writable: ctrl0=0x{ctrl0:x}"
    )
    await machine.writel(APBH_BASE + 0x008, 0x0000FF00)


@pytest.mark.asyncio
async def test_dma_reset_freeze_clkgate_contract(machine):
    """DMA reset/freeze/clkgate contract"""
    apbh_ch0_desc = SRAM_BASE + 0x4000
    apbh_ch1_desc = SRAM_BASE + 0x4040
    apbx_desc = SRAM_BASE + 0x4100
    apbh_ch0_cur = APBH_BASE + 0x040
    apbh_ch0_nxt = APBH_BASE + 0x050
    apbh_ch0_cmd = APBH_BASE + 0x060
    apbh_ch0_sema = APBH_BASE + 0x080
    apbh_ch1_cur = APBH_BASE + 0x0B0
    apbh_ch1_nxt = APBH_BASE + 0x0C0
    apbh_ch1_sema = APBH_BASE + 0x0F0
    apbx_ch0_cur = APBX_BASE + 0x040
    apbx_ch0_nxt = APBX_BASE + 0x050
    apbx_ch0_cmd = APBX_BASE + 0x060
    apbx_ch0_sema = APBX_BASE + 0x080

    terminal_command = DMA_SEMAPHORE | DMA_IRQONCMPLT

    async def write_descriptor_and_kick(nxt, sema, desc):
        await write_descriptor(machine, desc, 0, terminal_command, 0)
        await machine.writel(nxt, desc)
        await machine.writel(sema, 1)

    await machine.writel(APBH_BASE + 0x008, 0xC0000000)
    await machine.writel(APBX_BASE + 0x008, 0xC0000000)

    # APBH channel 0 RESET self-clears and resets channel registers.
    await write_descriptor_and_kick(apbh_ch0_nxt, apbh_ch0_sema, apbh_ch0_desc)
    current = await machine.readl(apbh_ch0_cur)
    assert current == apbh_ch0_desc, (
        f"APBH CH0 must load and run a NO_DMA_XFER command: got 0x{current:x}"
    )
    cmd = await machine.readl(apbh_ch0_cmd)
    assert cmd == 0x48, (
        f"APBH CH0 CMD must reflect the loaded command: got 0x{cmd:x}"
    )
    ctrl1 = await machine.readl(APBH_BASE + 0x010)
    assert ctrl1 == 1, (
        f"APBH CH0 must set CMDCMPLT_IRQ in CTRL1: got 0x{ctrl1:x}"
    )

    await machine.writel(APBH_BASE + 0x004, 0x00010000)
    ctrl0 = await machine.readl(APBH_BASE + 0x000)
    assert ctrl0 == 0, (
        f"APBH CH0 RESET bit must auto-clear: got 0x{ctrl0:x}"
    )
    current = await machine.readl(apbh_ch0_cur)
    assert current == 0, (
        f"APBH CH0 CURCMDAR must be cleared by RESET: got 0x{current:x}"
    )
    cmd = await machine.readl(apbh_ch0_cmd)
    assert cmd == 0, (
        f"APBH CH0 CMD must be cleared by RESET: got 0x{cmd:x}"
    )
    await machine.writel(APBH_BASE + 0x018, 0x00FFFFFF)

    # APBH CH0 FREEZE prevents command launch, clearing it resumes.
    await machine.writel(APBH_BASE + 0x004, 0x00000001)
    await write_descriptor_and_kick(apbh_ch0_nxt, apbh_ch0_sema, apbh_ch0_desc)
    current = await machine.readl(apbh_ch0_cur)
    assert current == 0, (
        f"APBH CH0 must not launch while FREEZE is set: got 0x{current:x}"
    )
    await machine.writel(APBH_BASE + 0x008, 0x00000001)
    current = await machine.readl(apbh_ch0_cur)
    assert current == apbh_ch0_desc, (
        f"APBH CH0 must resume and load the command when FREEZE is cleared: got 0x{current:x}"
    )
    sema = await machine.readl(apbh_ch0_sema)
    assert sema == 0, (
        f"APBH CH0 SEMA must be decremented after resumed launch: got 0x{sema:x}"
    )
    await machine.writel(APBH_BASE + 0x018, 0x00FFFFFF)

    # APBH CH1 CLKGATE_CHANNEL prevents command launch, clearing it resumes.
    await machine.writel(APBH_BASE + 0x004, 0x00000200)
    await write_descriptor_and_kick(apbh_ch1_nxt, apbh_ch1_sema, apbh_ch1_desc)
    current = await machine.readl(apbh_ch1_cur)
    assert current == 0, (
        f"APBH CH1 must not launch while CLKGATE_CHANNEL is set: got 0x{current:x}"
    )
    await machine.writel(APBH_BASE + 0x008, 0x00000200)
    current = await machine.readl(apbh_ch1_cur)
    assert current == apbh_ch1_desc, (
        f"APBH CH1 must resume and load the command when CLKGATE_CHANNEL is cleared: got 0x{current:x}"
    )
    await machine.writel(APBH_BASE + 0x018, 0x00FFFFFF)

    # APBX CH0 RESET and FREEZE behave the same.
    await write_descriptor_and_kick(apbx_ch0_nxt, apbx_ch0_sema, apbx_desc)
    current = await machine.readl(apbx_ch0_cur)
    assert current == apbx_desc, (
        f"APBX CH0 must load and run a NO_DMA_XFER command: got 0x{current:x}"
    )
    await machine.writel(APBX_BASE + 0x004, 0x00010000)
    ctrl0 = await machine.readl(APBX_BASE + 0x000)
    assert ctrl0 == 0, (
        f"APBX CH0 RESET bit must auto-clear: got 0x{ctrl0:x}"
    )
    current = await machine.readl(apbx_ch0_cur)
    assert current == 0, (
        f"APBX CH0 CURCMDAR must be cleared by RESET: got 0x{current:x}"
    )
    await machine.writel(APBX_BASE + 0x018, 0x00FFFFFF)

    await machine.writel(APBX_BASE + 0x004, 0x00000001)
    await write_descriptor_and_kick(apbx_ch0_nxt, apbx_ch0_sema, apbx_desc)
    current = await machine.readl(apbx_ch0_cur)
    assert current == 0, (
        f"APBX CH0 must not launch while FREEZE is set: got 0x{current:x}"
    )
    await machine.writel(APBX_BASE + 0x008, 0x00000001)
    current = await machine.readl(apbx_ch0_cur)
    assert current == apbx_desc, (
        f"APBX CH0 must resume and load the command when FREEZE is cleared: got 0x{current:x}"
    )
