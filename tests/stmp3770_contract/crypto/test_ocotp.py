import pytest

from framework.constants import OCOTP_BASE


@pytest.mark.asyncio
async def test_ocotp_bank_open_contract(machine):
    """OCOTP bank-open contract"""
    await machine.writel(OCOTP_BASE + 0x000, 0x3E770000)
    await machine.writel(OCOTP_BASE + 0x010, 0x11223344)

    custcap = await machine.readl(OCOTP_BASE + 0x110)
    cust0_closed = await machine.readl(OCOTP_BASE + 0x020)
    ctrl_after_closed_read = await machine.readl(OCOTP_BASE + 0x000)

    assert custcap == 0, f"OCOTP CUSTCAP shadow should be readable without bank open: got 0x{custcap:x}"
    assert cust0_closed == 0xBADABADA, f"OCOTP CUST0 should return BADABADA when bank is closed: got 0x{cust0_closed:x}"
    assert (
        ctrl_after_closed_read & (1 << 9)
    ) != 0, f"OCOTP CTRL.ERROR should latch after closed-bank read: ctrl=0x{ctrl_after_closed_read:x}"

    await machine.writel(OCOTP_BASE + 0x008, 0x00000200)
    ctrl_after_clr = await machine.readl(OCOTP_BASE + 0x000)
    assert (
        ctrl_after_clr & (1 << 9)
    ) == 0, f"OCOTP CTRL_CLR should clear ERROR via SCT clear space: ctrl=0x{ctrl_after_clr:x}"

    await machine.writel(OCOTP_BASE + 0x004, 0x00001000)
    cust0_open = await machine.readl(OCOTP_BASE + 0x020)
    assert cust0_open == 0x11223344, f"OCOTP CUST0 should expose programmed OTP bits once bank is open: got 0x{cust0_open:x}"


@pytest.mark.asyncio
async def test_ocotp_lock_and_shadow_contract(machine):
    """OCOTP lock and shadow contract"""
    await machine.writel(OCOTP_BASE + 0x110, 0x12345678)
    custcap_before_lock = await machine.readl(OCOTP_BASE + 0x110)
    assert custcap_before_lock == 0x12345678, f"OCOTP CUSTCAP shadow should be writable before lock: got 0x{custcap_before_lock:x}"

    await machine.writel(OCOTP_BASE + 0x000, 0x3E77000F)
    await machine.writel(OCOTP_BASE + 0x010, 0x12345678)

    await machine.writel(OCOTP_BASE + 0x000, 0x3E770010)
    await machine.writel(OCOTP_BASE + 0x010, 0x00000090)

    ctrl_after_lock_program = await machine.readl(OCOTP_BASE + 0x000)
    assert (
        ctrl_after_lock_program & 0xFFFF0000
    ) == 0, f"OCOTP successful DATA write should clear WR_UNLOCK: ctrl=0x{ctrl_after_lock_program:x}"

    await machine.writel(OCOTP_BASE + 0x004, 0x00002000)
    lock_shadow = await machine.readl(OCOTP_BASE + 0x120)
    custcap_reloaded = await machine.readl(OCOTP_BASE + 0x110)
    assert lock_shadow == 0x00000090, f"OCOTP LOCK shadow should reload programmed lock bits: got 0x{lock_shadow:x}"
    assert custcap_reloaded == 0x12345678, f"OCOTP reload should repopulate CUSTCAP shadow from OTP bank 1 word 7: got 0x{custcap_reloaded:x}"

    await machine.writel(OCOTP_BASE + 0x110, 0xDEADBEEF)
    custcap_after_lock = await machine.readl(OCOTP_BASE + 0x110)
    ctrl_after_locked_shadow_write = await machine.readl(OCOTP_BASE + 0x000)

    assert custcap_after_lock == 0x12345678, f"OCOTP CUSTCAP shadow should ignore writes after CUSTCAP_SHADOW lock: got 0x{custcap_after_lock:x}"
    assert (
        ctrl_after_locked_shadow_write & (1 << 9)
    ) != 0, f"OCOTP locked shadow write should raise CTRL.ERROR: ctrl=0x{ctrl_after_locked_shadow_write:x}"

    await machine.writel(OCOTP_BASE + 0x008, 0x00000200)
    await machine.writel(OCOTP_BASE + 0x004, 0x00001000)
    crypto0 = await machine.readl(OCOTP_BASE + 0x060)
    ctrl_after_crypto_read = await machine.readl(OCOTP_BASE + 0x000)

    assert crypto0 == 0xBADABADA, f"OCOTP locked CRYPTO0 should return BADABADA: got 0x{crypto0:x}"
    assert (
        ctrl_after_crypto_read & (1 << 9)
    ) != 0, f"OCOTP locked crypto read should raise CTRL.ERROR: ctrl=0x{ctrl_after_crypto_read:x}"
