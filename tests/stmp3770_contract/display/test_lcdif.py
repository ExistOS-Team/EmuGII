import pytest

from framework.constants import ICOLL_BASE, LCDIF_BASE


@pytest.mark.asyncio
async def test_lcdif_ctrl1_layout(machine):
    """LCDIF CTRL1 interrupt layout"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x010, 0x00001000)
    await machine.writel(LCDIF_BASE + 0x004, 0x00010000)
    await machine.clock_step(20_000_000)

    ctrl1 = await machine.readl(LCDIF_BASE + 0x010)
    raw1 = await machine.readl(ICOLL_BASE + 0x050)

    assert (ctrl1 & (1 << 12)) != 0, f"LCDIF VSYNC enable bit lost: ctrl1=0x{ctrl1:x}"
    assert (ctrl1 & (1 << 8)) != 0, f"LCDIF VSYNC status bit missing from CTRL1: ctrl1=0x{ctrl1:x}"
    assert (raw1 & (1 << 14)) != 0, f"LCDIF IRQ not asserted on ICOLL source 46: raw1=0x{raw1:x}"


@pytest.mark.asyncio
async def test_lcdif_register_map_contract(machine):
    """LCDIF register map contract"""
    assert await machine.readl(LCDIF_BASE + 0x010) == 0x000F0000, (
        "LCDIF CTRL1 reset must retain BYTE_PACKING_FORMAT=0xf"
    )
    assert await machine.readl(LCDIF_BASE + 0x0C0) == 0x90000000, (
        "LCDIF STAT reset must report PRESENT and RXFIFO_EMPTY only"
    )
    assert await machine.readl(LCDIF_BASE + 0x0D0) == 0x02000000, (
        "LCDIF VERSION must report Reference Manual v2.0"
    )
    assert await machine.readl(LCDIF_BASE + 0x0E0) == 0x0E810000, (
        "LCDIF DEBUG0 reset fields must be read-only Reference defaults"
    )

    cases = [
        [0x020, 0xFFFFFFFF, 0xFFFFFFFF, "TIMING"],
        [0x030, 0xFFFFFFFF, 0x3F3803FF, "VDCTRL0"],
        [0x040, 0xFFFFFFFF, 0xFFFFFFFF, "VDCTRL1"],
        [0x050, 0xFFFFFFFF, 0xFFFFFFFF, "VDCTRL2"],
        [0x060, 0xFFFFFFFF, 0x01FFF1FF, "VDCTRL3"],
        [0x070, 0xFFFFFFFF, 0xFFFFFFFF, "DVICTRL0"],
        [0x080, 0xFFFFFFFF, 0x3FFFFFFF, "DVICTRL1"],
        [0x090, 0xFFFFFFFF, 0x3FFFFFFF, "DVICTRL2"],
        [0x0A0, 0xFFFFFFFF, 0x03FF03FF, "DVICTRL3"],
    ]

    for offset, value, expected, name in cases:
        await machine.writel(LCDIF_BASE + offset, value)
        assert await machine.readl(LCDIF_BASE + offset) == expected, (
            f"LCDIF {name} must decode at its PDF address and preserve only documented fields"
        )

    await machine.writel(LCDIF_BASE + 0x034, 0xFFFFFFFF)
    assert await machine.readl(LCDIF_BASE + 0x030) == 0x3F3803FF, (
        "LCDIF VDCTRL0 SET alias must operate only on documented fields"
    )


@pytest.mark.asyncio
async def test_lcdif_clock_gate_contract(machine):
    """LCDIF clock gate contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x004, 0x40000000)
    assert await machine.readl(LCDIF_BASE + 0x000) & 0x40000000 != 0, (
        "LCDIF CLKGATE must remain set when SFTRST is clear"
    )

    await machine.writel(LCDIF_BASE + 0x004, 0x80000000)
    await machine.writel(LCDIF_BASE + 0x008, 0x80000000)
    assert await machine.readl(LCDIF_BASE + 0x000) & 0x40000000 != 0, (
        "LCDIF clearing SFTRST must not implicitly clear a separately gated clock"
    )


@pytest.mark.asyncio
async def test_lcdif_soft_reset_contract(machine):
    """LCDIF soft reset contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x010, 0x00030001)
    await machine.writel(LCDIF_BASE + 0x020, 0x11223344)
    await machine.writel(LCDIF_BASE + 0x040, 0x55667788)

    await machine.writel(LCDIF_BASE + 0x004, 0x80000000)
    assert await machine.readl(LCDIF_BASE + 0x010) == 0x000F0001, (
        "LCDIF SFTRST must restore CTRL1 defaults while preserving the external RESET line"
    )
    assert await machine.readl(LCDIF_BASE + 0x020) == 0, (
        "LCDIF SFTRST must restore TIMING defaults"
    )
    assert await machine.readl(LCDIF_BASE + 0x040) == 0, (
        "LCDIF SFTRST must restore VDCTRL1 defaults"
    )


@pytest.mark.asyncio
async def test_lcdif_byte_packing_contract(machine):
    """LCDIF byte packing contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2C)
    await machine.writel(LCDIF_BASE + 0x010, 0x00070000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00070003)
    await machine.writel(LCDIF_BASE + 0x0B0, 0xAABBCCDD)

    assert await machine.readl(LCDIF_BASE + 0x000) & 0x00010000 == 0, (
        "LCDIF must consume only the three valid BYTE_PACKING_FORMAT subwords"
    )

    await machine.writel(LCDIF_BASE + 0x000, 0x20020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2E)
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0xDD
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0xCC
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0xBB
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0, (
        "LCDIF must not transmit the byte masked by BYTE_PACKING_FORMAT"
    )


@pytest.mark.asyncio
async def test_lcdif_data_swizzle_contract(machine):
    """LCDIF data swizzle contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2C)
    await machine.writel(LCDIF_BASE + 0x000, 0x00270004)
    await machine.writel(LCDIF_BASE + 0x0B0, 0x11223344)

    await machine.writel(LCDIF_BASE + 0x000, 0x20020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2E)
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x11
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x22
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x33
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x44


@pytest.mark.asyncio
async def test_lcdif_data_shift_contract(machine):
    """LCDIF data shift contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2C)
    await machine.writel(LCDIF_BASE + 0x000, 0x0C070004)
    await machine.writel(LCDIF_BASE + 0x0B0, 0xAABBCCDD)

    await machine.writel(LCDIF_BASE + 0x000, 0x20020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2E)
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x37
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x33
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x2E
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x2A


@pytest.mark.asyncio
async def test_lcdif_idle_only_control_contract(machine):
    """LCDIF idle-only control contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00010001)
    await machine.writel(LCDIF_BASE + 0x004, 0x00040000)
    await machine.writel(LCDIF_BASE + 0x014, 0x00000002)
    assert await machine.readl(LCDIF_BASE + 0x000) & 0x00040000 == 0
    assert await machine.readl(LCDIF_BASE + 0x010) & 0x00000002 == 0

    await machine.writel(LCDIF_BASE + 0x008, 0x00010000)
    await machine.writel(LCDIF_BASE + 0x004, 0x00040000)
    await machine.writel(LCDIF_BASE + 0x014, 0x00000002)
    assert await machine.readl(LCDIF_BASE + 0x000) & 0x00040000 != 0
    assert await machine.readl(LCDIF_BASE + 0x010) & 0x00000002 != 0


@pytest.mark.asyncio
async def test_lcdif_fifo_status_contract(machine):
    """LCDIF FIFO status contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00030004)
    assert await machine.readl(LCDIF_BASE + 0x0C0) == 0xD4000000, (
        "LCDIF STAT must report an empty TX FIFO and asserted DMA request during an enabled write transfer"
    )


@pytest.mark.asyncio
async def test_lcdif_streaming_end_contract(machine):
    """LCDIF streaming end contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00910000)
    await machine.writel(LCDIF_BASE + 0x008, 0x00100000)
    assert await machine.readl(LCDIF_BASE + 0x000) & 0x00010000 == 0, (
        "LCDIF ending a bypassed VSYNC stream must clear RUN after its empty FIFO is flushed"
    )


@pytest.mark.asyncio
async def test_lcdif_first_read_dummy_contract(machine):
    """LCDIF first read dummy contract"""
    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, 0x00020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2C)
    await machine.writel(LCDIF_BASE + 0x000, 0x00070004)
    await machine.writel(LCDIF_BASE + 0x0B0, 0x44332211)

    await machine.writel(LCDIF_BASE + 0x000, 0x00020000)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0x2E)
    await machine.writel(LCDIF_BASE + 0x010, 0x000F0010)
    await machine.writel(LCDIF_BASE + 0x000, 0x20030003)
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x22, (
        "LCDIF FIRST_READ_DUMMY must discard the initial panel response before filling the read FIFO"
    )


@pytest.mark.asyncio
async def test_lcdif_data_access_contract(machine):
    """LCDIF data access contract"""
    ctrl = 0x00030001

    await machine.writel(LCDIF_BASE + 0x008, 0xC0000000)
    await machine.writel(LCDIF_BASE + 0x000, ctrl)
    await machine.writeb(LCDIF_BASE + 0x0B0, 0xDB)
    assert await machine.readl(LCDIF_BASE + 0x000) & 0x00010000 == 0, (
        "LCDIF byte DATA write must consume COUNT and clear RUN at transfer completion"
    )
    assert await machine.readb(LCDIF_BASE + 0x0B0) == 0x80, (
        "LCDIF DATA must support byte reads from the selected panel register"
    )
