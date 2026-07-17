import pytest

from framework.constants import DBGUART_BASE


@pytest.mark.asyncio
async def test_rom_boot_init_contract(machine):
    """ROM boot init contract"""
    ibrd = await machine.readl(DBGUART_BASE + 0x024)
    fbrd = await machine.readl(DBGUART_BASE + 0x028)
    lcrh = await machine.readl(DBGUART_BASE + 0x02C)
    cr = await machine.readl(DBGUART_BASE + 0x030)
    assert ibrd == 0x0000000D and fbrd == 0x00000001 and lcrh == 0x00000070, (
        f"ROM boot init mismatch: IBRD=0x{ibrd:x} FBRD=0x{fbrd:x} "
        f"LCR_H=0x{lcrh:x} CR=0x{cr:x} stderr={machine.stderr}"
    )
