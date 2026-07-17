import pytest

from framework.constants import OCROM_BASE, SRAM_BASE


@pytest.mark.asyncio
async def test_on_chip_rom_and_sram_mirror_contract(machine):
    """on-chip ROM and SRAM mirror contract"""
    await machine.writel(SRAM_BASE + 0x1234, 0x11223344)
    assert await machine.readl(0x00081234) == 0x11223344, (
        "STMP3770 OCRAM must mirror every 512 KiB across the documented low 1 GiB window"
    )
    assert await machine.readl(0x3FF81234) == 0x11223344, (
        "STMP3770 OCRAM last low-window mirror must alias physical OCRAM"
    )

    await machine.writel(0x3FF81234, 0xAABBCCDD)
    assert await machine.readl(SRAM_BASE + 0x1234) == 0xAABBCCDD, (
        "writes through an OCRAM mirror must update the base OCRAM instance"
    )

    assert await machine.readl(OCROM_BASE) == 0, (
        "STMP3770 OCROM reset vector storage must be mapped at 0xffff0000"
    )
    await machine.writel(OCROM_BASE, 0xDEADBEEF)
    assert await machine.readl(OCROM_BASE) == 0, (
        "STMP3770 OCROM must remain read-only to CPU writes"
    )
