from framework.constants import DFLPT_BASE, DIGCTL_BASE


async def test_dflpt_pte_2048_contract(machine):
    """DFLPT PTE_2048 contract"""
    pte2048 = await machine.readl(DFLPT_BASE + 0x2000)

    assert pte2048 == 0x80000c12, f"DFLPT PTE_2048 reset mismatch: got 0x{pte2048:x}"

    await machine.writel(DFLPT_BASE + 0x2000, 0xffffffff)
    updated = await machine.readl(DFLPT_BASE + 0x2000)

    assert updated == 0x80000df6, f"DFLPT PTE_2048 should only expose AP/DOMAIN/BUFFERABLE fields: got 0x{updated:x}"


async def test_dflpt_mpte_tracks_locator(machine):
    """DFLPT MPTE locator remap"""
    mpte0_reset = await machine.readl(DFLPT_BASE + 0x0000)
    pte5_reset = await machine.readl(DFLPT_BASE + (5 << 2))

    assert mpte0_reset == 0, f"DFLPT MPTE0 reset contents should be 0: got 0x{mpte0_reset:x}"
    assert pte5_reset == 0, f"DFLPT unbound PTE5 should reset to 0: got 0x{pte5_reset:x}"

    await machine.writel(DFLPT_BASE + 0x0000, 0x11223344)
    mpte0_written = await machine.readl(DFLPT_BASE + 0x0000)
    assert mpte0_written == 0x11223344, f"DFLPT MPTE0 write should stick at reset locator: got 0x{mpte0_written:x}"

    await machine.writel(DIGCTL_BASE + 0x0400, 0x00000020)
    old_location = await machine.readl(DFLPT_BASE + 0x0000)
    new_location = await machine.readl(DFLPT_BASE + (0x20 << 2))

    assert old_location == 0, f"DFLPT old MPTE0 location should become unbound after locator move: got 0x{old_location:x}"
    assert new_location == 0x11223344, f"DFLPT MPTE0 contents should move with DIGCTL_MPTE0_LOC: got 0x{new_location:x}"
