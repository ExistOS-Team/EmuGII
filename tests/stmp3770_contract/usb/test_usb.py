import pytest

from framework.constants import ICOLL_BASE, USB_BASE, USBPHY_BASE


@pytest.mark.asyncio
async def test_usb_phy_register_contract(machine):
    """USBPHY register contract"""
    reset_values = [
        [0x000, 0x001F7C00, "PWD"],
        [0x010, 0x10060607, "TX"],
        [0x020, 0x00000000, "RX"],
        [0x030, 0xC0000001, "CTRL"],
        [0x040, 0x00000000, "STATUS"],
        [0x050, 0x7F180000, "DEBUG"],
        [0x060, 0x0000900D, "DEBUG0_STATUS"],
        [0x070, 0x00001000, "DEBUG1"],
        [0x080, 0x03000000, "VERSION"],
    ]

    for offset, expected, name in reset_values:
        assert await machine.readl(USBPHY_BASE + offset) == expected, (
            f"USBPHY {name} must decode at its PDF address and reset to its documented value"
        )

    writable = [
        [0x000, 0x001F7C00, "PWD"],
        [0x010, 0x1FAF2F8F, "TX"],
        [0x020, 0x00400033, "RX"],
        [0x050, 0x7F1F1F3F, "DEBUG"],
        [0x070, 0x0000700F, "DEBUG1"],
    ]

    for offset, expected, name in writable:
        await machine.writel(USBPHY_BASE + offset, 0)
        await machine.writel(USBPHY_BASE + offset + 0x004, 0xFFFFFFFF)
        assert await machine.readl(USBPHY_BASE + offset) == expected, (
            f"USBPHY {name}_SET must preserve only documented writable fields"
        )
        await machine.writel(USBPHY_BASE + offset + 0x008, 0xFFFFFFFF)
        assert await machine.readl(USBPHY_BASE + offset) == 0, (
            f"USBPHY {name}_CLR must clear documented writable fields"
        )

    await machine.writel(USBPHY_BASE + 0x040, 0xFFFFFFFF)
    assert await machine.readl(USBPHY_BASE + 0x040) == 0x00000000, (
        "USBPHY STATUS must be read-only and reset to 0 (OTGID_STATUS is bit 8)"
    )

    no_tog = [
        [0x010, 0x1FAF2F8F, "TX"],
        [0x020, 0x00400033, "RX"],
    ]
    for offset, expected, name in no_tog:
        await machine.writel(USBPHY_BASE + offset, 0)
        await machine.writel(USBPHY_BASE + offset + 0x004, 0xFFFFFFFF)
        await machine.writel(USBPHY_BASE + offset + 0x00C, 0xFFFFFFFF)
        assert await machine.readl(USBPHY_BASE + offset) == expected, (
            f"USBPHY {name} must not support TOG alias"
        )

    await machine.writel(USBPHY_BASE + 0x050, 0)
    await machine.writel(USBPHY_BASE + 0x038, 0x80000000)
    assert ((await machine.readl(USBPHY_BASE + 0x030)) & 0xC0000000) == 0x40000000, (
        "USBPHY clearing SFTRST must preserve a separately gated clock"
    )
    await machine.writel(USBPHY_BASE + 0x034, 0x80000000)
    assert await machine.readl(USBPHY_BASE + 0x000) == 0x001F7C00
    assert await machine.readl(USBPHY_BASE + 0x010) == 0x10060607
    assert await machine.readl(USBPHY_BASE + 0x020) == 0
    assert ((await machine.readl(USBPHY_BASE + 0x030)) & 0xC0000001) == 0xC0000001, (
        "USBPHY SFTRST must restore CTRL together with PWD/TX/RX"
    )
    assert await machine.readl(USBPHY_BASE + 0x050) == 0, (
        "USBPHY SFTRST must not reset DEBUG outside its documented reset domain"
    )


@pytest.mark.asyncio
async def test_usb_capability_register_contract(machine):
    """USBCTRL capability register contract"""
    fixed_registers = [
        [0x000, 0x0042FA05, "ID"],
        [0x004, 0x00000015, "ARC_GENERAL"],
        [0x008, 0x10020001, "HWHOST"],
        [0x00C, 0x0000000B, "HWDEVICE"],
        [0x010, 0x00050810, "HWTXBUF"],
        [0x014, 0x00000610, "HWRXBUF"],
        [0x104, 0x00010011, "HCSPARAMS"],
        [0x108, 0x00000006, "HCCPARAMS"],
        [0x124, 0x00000185, "DCCPARAMS"],
    ]

    for offset, expected, name in fixed_registers:
        assert await machine.readl(USB_BASE + offset) == expected, (
            f"USBCTRL {name} must decode to its PDF reset value"
        )

    assert await machine.readb(USB_BASE + 0x100) == 0x40, (
        "USBCTRL CAPLENGTH must accept its documented 8-bit access"
    )
    assert await machine.readw(USB_BASE + 0x102) == 0x0100, (
        "USBCTRL HCIVERSION must accept its documented 16-bit access"
    )
    assert await machine.readw(USB_BASE + 0x120) == 0x0001, (
        "USBCTRL DCIVERSION must accept its documented 16-bit access"
    )


@pytest.mark.asyncio
async def test_usb_device_control_contract(machine):
    """USBCTRL device control contract"""
    assert await machine.readl(USB_BASE + 0x140) == 0x00080000
    assert await machine.readl(USB_BASE + 0x144) == 0x00000000
    assert await machine.readl(USB_BASE + 0x148) == 0x00000000
    assert await machine.readl(USB_BASE + 0x160) == 0x00001010
    assert await machine.readl(USB_BASE + 0x1A4) == 0x00000020
    assert await machine.readl(USB_BASE + 0x1A8) == 0x00000000
    assert ((await machine.readl(USB_BASE + 0x184)) & 0x00001005) == 0, (
        "USBCTRL PORTSC1 must not report a powered, enabled, or connected port at reset"
    )

    await machine.writel(USB_BASE + 0x148, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x148) == 0x030D01FF, (
        "USBCTRL USBINTR must retain only the Table 278 interrupt-enable fields"
    )

    await machine.writel(USB_BASE + 0x154, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x154) == 0x01000000, (
        "USBCTRL DEVICEADDR with USBADRA=1 must keep old USBADR and stage the new value"
    )
    await machine.writel(USB_BASE + 0x154, 0xFE000000)
    assert await machine.readl(USB_BASE + 0x154) == 0xFE000000, (
        "USBCTRL DEVICEADDR with USBADRA=0 must update USBADR immediately"
    )
    await machine.writel(USB_BASE + 0x158, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x158) == 0xFFFFF800, (
        "USBCTRL ENDPTLISTADDR must preserve its 2 KiB alignment"
    )
    await machine.writel(USB_BASE + 0x15C, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x15C) == 0x7F000000, (
        "USBCTRL TTCTRL must retain only TTHA[30:24]"
    )
    await machine.writel(USB_BASE + 0x160, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x160) == 0x0000FFFF, (
        "USBCTRL BURSTSIZE must retain only TXPBURST and RXPBURST"
    )

    await machine.writel(USB_BASE + 0x1A8, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x1A8) == 0x0000003F, (
        "USBCTRL USBMODE must retain its six documented control bits"
    )
    await machine.writel(USB_BASE + 0x1A8, 0x00000000)
    assert await machine.readl(USB_BASE + 0x1A8) == 0x0000003F, (
        "USBCTRL USBMODE must ignore subsequent writes until controller reset"
    )

    await machine.writel(USB_BASE + 0x140, 0x00000002)
    assert await machine.readl(USB_BASE + 0x140) == 0x00080000, (
        "USBCTRL USBCMD.RST must self-clear into the device-mode reset value"
    )
    assert await machine.readl(USB_BASE + 0x144) == 0x00000000
    assert await machine.readl(USB_BASE + 0x148) == 0x00000000
    assert await machine.readl(USB_BASE + 0x154) == 0x00000000
    assert await machine.readl(USB_BASE + 0x158) == 0x00000000
    assert await machine.readl(USB_BASE + 0x15C) == 0x00000000
    assert await machine.readl(USB_BASE + 0x160) == 0x00001010
    assert await machine.readl(USB_BASE + 0x1A4) == 0x00000020
    assert await machine.readl(USB_BASE + 0x1A8) == 0x00000000

    await machine.writel(USB_BASE + 0x1A8, 0x00000002)
    await machine.writel(USB_BASE + 0x1A8, 0x00000003)
    assert await machine.readl(USB_BASE + 0x1A8) == 0x00000002, (
        "USBCTRL controller reset must permit exactly one new USBMODE selection"
    )


@pytest.mark.asyncio
async def test_usb_portsc1_and_otgsc_contract(machine):
    """USBCTRL PORTSC1 and OTGSC contract"""
    PORTSC1_PE = 0x00000004
    PORTSC1_PEC = 0x00000008
    PORTSC1_CCS = 0x00000001
    PORTSC1_CSC = 0x00000002
    PORTSC1_OCC = 0x00000020

    await machine.writel(USB_BASE + 0x140, 0x00000002)
    assert await machine.readl(USB_BASE + 0x140) == 0x00080000
    await machine.writel(USB_BASE + 0x1A8, 0x00000003)
    assert await machine.readl(USB_BASE + 0x1A8) == 0x00000003

    await machine.writel(USB_BASE + 0x184, 0x00000000)
    await machine.writel(
        USB_BASE + 0x184,
        (0xF << 16) | (0x3 << 14) | (0x7 << 20) | (1 << 23)
        | (1 << 12) | (1 << 8) | (1 << 7) | (1 << 6) | (1 << 2),
    )
    assert await machine.readl(USB_BASE + 0x184) == 0x00FFD1CC, (
        "USBCTRL PORTSC1 must expose host-mode PP/PR/SUSP/PE, "
        "always-writable bits, and PEC on PE 0->1 transition"
    )

    portsc1 = await machine.readl(USB_BASE + 0x184)

    await machine.writel(USB_BASE + 0x184, portsc1 | PORTSC1_PEC)
    assert ((await machine.readl(USB_BASE + 0x184)) & PORTSC1_PEC) == 0, (
        "USBCTRL PORTSC1 PEC must be W1C"
    )

    portsc1 = await machine.readl(USB_BASE + 0x184)
    await machine.writel(USB_BASE + 0x184, portsc1 & ~PORTSC1_PE & ~PORTSC1_PEC)
    assert await machine.readl(USB_BASE + 0x184) == 0x00FFD1C8, (
        "USBCTRL PORTSC1 PEC must be set when PE transitions 1->0"
    )

    portsc1 = await machine.readl(USB_BASE + 0x184)
    await machine.writel(USB_BASE + 0x184, (portsc1 & ~PORTSC1_PEC) | PORTSC1_PE)
    assert await machine.readl(USB_BASE + 0x184) == 0x00FFD1CC, (
        "USBCTRL PORTSC1 PEC must be set when PE transitions 0->1"
    )

    portsc1 = await machine.readl(USB_BASE + 0x184)
    await machine.writel(USB_BASE + 0x184, portsc1 & ~PORTSC1_PE & ~PORTSC1_PEC)
    assert await machine.readl(USB_BASE + 0x184) == 0x00FFD1C8, (
        "USBCTRL PORTSC1 PEC must be set when PE transitions 1->0"
    )
    portsc1 = await machine.readl(USB_BASE + 0x184)
    await machine.writel(USB_BASE + 0x184, portsc1 | PORTSC1_PEC)
    assert await machine.readl(USB_BASE + 0x184) == 0x00FFD1C0, (
        "USBCTRL PORTSC1 PEC must be W1C when PE is 0"
    )

    portsc1 = await machine.readl(USB_BASE + 0x184)
    await machine.writel(
        USB_BASE + 0x184,
        portsc1 | PORTSC1_CCS | PORTSC1_CSC | PORTSC1_OCC,
    )
    assert await machine.readl(USB_BASE + 0x184) == 0x00FFD1C0, (
        "USBCTRL PORTSC1 must ignore CCS writes and W1C-clear CSC/OCC when not pending"
    )

    assert await machine.readl(USB_BASE + 0x1A4) == 0x00000020, (
        "USBCTRL OTGSC must reset with IDPU set"
    )

    await machine.writel(USB_BASE + 0x1A4, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x7F0000FF, (
        "USBCTRL OTGSC must expose all enable and control bits, with status W1C"
    )

    await machine.writel(USB_BASE + 0x1A4, 0x7F7F00FF)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x7F0000FF, (
        "USBCTRL OTGSC status bits must be write-1-to-clear and not writable"
    )

    await machine.writel(USB_BASE + 0x1A4, 0x00000000)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x00000000, (
        "USBCTRL OTGSC must clear enable and control bits"
    )

    await machine.writel(USB_BASE + 0x1A4, 0x00FF00FF)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x000000FF, (
        "USBCTRL OTGSC must ignore status-input and reserved bits on writes"
    )

    await machine.writel(USB_BASE + 0x148, 0x00000004)
    await machine.clock_step(10_000_000)
    assert await machine.readl(USB_BASE + 0x184) == 0x04FFD2CC, (
        "USBCTRL PORTSC1 PR must clear and PE/PEC/PSPD/HSP set after 10 ms reset"
    )
    assert await machine.readl(USB_BASE + 0x144) == 0x00001004, (
        "USBCTRL USBSTS.PCI must be set after port reset"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) != 0, (
        "USBCTRL PCI must assert ICOLL source 11"
    )
    await machine.writel(USB_BASE + 0x144, 0x00000004)
    assert await machine.readl(USB_BASE + 0x144) == 0x00001000, (
        "USBCTRL USBSTS.PCI must be W1C"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) == 0, (
        "USBCTRL PCI clear must deassert ICOLL source 11"
    )

    await machine.writel(USB_BASE + 0x1A4, 0x200000FF)
    await machine.clock_step(1_000_000)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x202020FF, (
        "USBCTRL OTGSC ONEMST must toggle and ONEMSS set after 1 ms"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) != 0, (
        "USBCTRL OTGSC ONEMSS must assert ICOLL source 11 when ONEMSE enabled"
    )

    await machine.clock_step(1_000_000)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x202000FF, (
        "USBCTRL OTGSC ONEMST must toggle again"
    )

    await machine.writel(USB_BASE + 0x1A4, 0x202000FF)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x200000FF, (
        "USBCTRL OTGSC ONEMSS must be W1C"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) == 0, (
        "USBCTRL OTGSC ONEMSS clear must deassert ICOLL source 11"
    )

    await machine.clock_step(1_000_000)
    assert await machine.readl(USB_BASE + 0x1A4) == 0x202020FF, (
        "USBCTRL OTGSC ONEMSS must be set again on next 1 ms tick"
    )


@pytest.mark.asyncio
async def test_usb_endpoint_register_contract(machine):
    """USBCTRL endpoint register contract"""
    assert await machine.readl(USB_BASE + 0x1C0) == 0x00800080, (
        "USBCTRL ENDPTCTRL0 must reset as the fixed enabled control endpoint"
    )
    await machine.writel(USB_BASE + 0x1C0, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x1C0) == 0x008D008D, (
        "USBCTRL ENDPTCTRL0 must retain fixed enables and only Table 318 writable fields"
    )

    await machine.writel(USB_BASE + 0x1B0, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x1B8) == 0x001F001F, (
        "USBCTRL ENDPTPRIME must expose ready bits only for endpoints 0 through 4"
    )
    await machine.writel(USB_BASE + 0x1B4, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x1B8) == 0, (
        "USBCTRL ENDPTFLUSH must clear only documented endpoint ready bits"
    )

    await machine.writel(USB_BASE + 0x1C4, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x1C4) == 0x00AD00AD, (
        "USBCTRL ENDPTCTRL1 must self-clear TXR/RXR and reset TXD/RXD"
    )

    await machine.writel(USB_BASE + 0x1C4, 0x00A300A3)
    assert await machine.readl(USB_BASE + 0x1C4) == 0x00A300A3, (
        "USBCTRL ENDPTCTRL1 must hold TXD/RXD when TXR/RXR are clear"
    )
    await machine.writel(USB_BASE + 0x1C4, 0x00E700E7)
    assert await machine.readl(USB_BASE + 0x1C4) == 0x00A500A5, (
        "USBCTRL ENDPTCTRL1 must clear TXD when TXR is set and RXD when RXR is set"
    )

    await machine.writel(USB_BASE + 0x17C, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x17C) == 0x001F001F, (
        "USBCTRL ENDPTNAKEN must retain only RX/TX endpoint bits 0 through 4"
    )

    await machine.writel(USB_BASE + 0x164, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x164) == 0x003F007F, (
        "USBCTRL TXFILLTUNING must hide reserved bits and clear TXSCHHEALTH writes"
    )
    await machine.writel(USB_BASE + 0x1D4, 0xFFFFFFFF)
    assert await machine.readl(USB_BASE + 0x1D4) == 0, (
        "USBCTRL ENDPTCTRL5 must remain unimplemented because only endpoints 0 through 4 exist"
    )


@pytest.mark.asyncio
async def test_usb_gptimer_contract(machine):
    """USBCTRL GPTIMER contract"""
    await machine.writel(USB_BASE + 0x080, 0x00000001)
    assert await machine.readl(USB_BASE + 0x080) == 0x00000001, (
        "USBCTRL GPTIMER0LD must retain its documented 24-bit load value"
    )
    await machine.writel(USB_BASE + 0x148, 0x01000000)
    await machine.writel(USB_BASE + 0x084, 0x40000000)
    assert await machine.readl(USB_BASE + 0x084) == 0x00000001, (
        "USBCTRL GPTRST must load GPTCNT and self-clear while the timer remains stopped"
    )

    await machine.clock_step(1_000)
    assert await machine.readl(USB_BASE + 0x084) == 0x00000001, (
        "USBCTRL GPTRST without GTPRUN must retain GPTCNT while the timer is stopped"
    )
    await machine.writel(USB_BASE + 0x084, 0x80000000)
    assert await machine.readl(USB_BASE + 0x084) == 0x80000001, (
        "USBCTRL GTPRUN must start from the reset-loaded GPTCNT without changing it"
    )

    await machine.clock_step(1_000)
    assert await machine.readl(USB_BASE + 0x084) == 0x80000001, (
        "USBCTRL GPTIMER0 must retain GPTCNT for the first 1 microsecond interval"
    )
    assert ((await machine.readl(USB_BASE + 0x144)) & 0x01000000) == 0, (
        "USBCTRL TI0 must remain clear before GPTCNT transitions to zero"
    )

    await machine.clock_step(1_000)
    assert await machine.readl(USB_BASE + 0x084) == 0x00000000, (
        "USBCTRL GPTIMER0 must stop at zero when the countdown expires"
    )
    assert ((await machine.readl(USB_BASE + 0x144)) & 0x01000000) != 0, (
        "USBCTRL GPTIMER0 expiry must set USBSTS.TI0"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) != 0, (
        "USBCTRL TIE0 and TI0 must assert the USB interrupt on ICOLL source 11"
    )
    await machine.writel(USB_BASE + 0x144, 0x01000000)
    assert ((await machine.readl(USB_BASE + 0x144)) & 0x01000000) == 0, (
        "USBCTRL USBSTS.TI0 must clear by write-one-to-clear"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) == 0, (
        "USBCTRL USB interrupt must deassert after TI0 is acknowledged"
    )
    await machine.writel(USB_BASE + 0x084, 0x80000000)
    await machine.clock_step(2_000)
    assert await machine.readl(USB_BASE + 0x084) == 0, (
        "USBCTRL one-shot must remain stopped when GTPRUN is written without GPTRST"
    )
    assert ((await machine.readl(USB_BASE + 0x144)) & 0x01000000) == 0, (
        "USBCTRL one-shot must not reassert TI0 until software resets GPTCNT"
    )

    await machine.writel(USB_BASE + 0x080, 0x00000009)
    await machine.writel(USB_BASE + 0x084, 0xC0000000)
    await machine.clock_step(2_000)
    await machine.writel(USB_BASE + 0x080, 0x00000003)
    await machine.writel(USB_BASE + 0x084, 0x40000000)
    assert await machine.readl(USB_BASE + 0x084) == 0x00000003, (
        "USBCTRL GPTRST must reload GPTCNT even when it stops an active timer"
    )
    await machine.clock_step(10_000)
    assert await machine.readl(USB_BASE + 0x084) == 0x00000003, (
        "USBCTRL GPTRST without GTPRUN must leave a reloaded active timer stopped"
    )

    await machine.writel(USB_BASE + 0x088, 0x00000000)
    await machine.writel(USB_BASE + 0x148, 0x02000000)
    await machine.writel(USB_BASE + 0x08C, 0xC1000000)
    await machine.clock_step(1_000)
    assert ((await machine.readl(USB_BASE + 0x144)) & 0x02000000) != 0, (
        "USBCTRL GPTIMER1 repeat mode must set USBSTS.TI1 on expiry"
    )
    await machine.writel(USB_BASE + 0x144, 0x02000000)
    await machine.clock_step(1_000)
    assert ((await machine.readl(USB_BASE + 0x144)) & 0x02000000) != 0, (
        "USBCTRL GPTIMER1 repeat mode must automatically reload after expiry"
    )


@pytest.mark.asyncio
async def test_usb_frindex_and_status_contract(machine):
    """USBCTRL FRINDEX and host status contract"""
    USBCMD = USB_BASE + 0x140
    USBSTS = USB_BASE + 0x144
    USBINTR = USB_BASE + 0x148
    FRINDEX = USB_BASE + 0x14C
    USBMODE = USB_BASE + 0x1A8

    await machine.writel(USBCMD, 0x00000002)
    assert await machine.readl(USBCMD) == 0x00080000
    await machine.writel(USBMODE, 0x00000003)
    assert await machine.readl(USBMODE) == 0x00000003

    assert await machine.readl(USBSTS) == 0x00001000

    await machine.writel(FRINDEX, 0x00001234)
    assert await machine.readl(FRINDEX) == 0x00001234
    await machine.clock_step(125_000)
    assert await machine.readl(FRINDEX) == 0x00001234

    await machine.writel(USBINTR, 0x00000088)
    await machine.writel(USBCMD, 0x00080001)
    assert await machine.readl(USBSTS) == 0x00000000

    await machine.clock_step(125_000)
    assert await machine.readl(FRINDEX) == 0x00001235
    assert await machine.readl(USBSTS) == 0x00000080
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) != 0

    await machine.writel(USBSTS, 0x00000080)
    assert await machine.readl(USBSTS) == 0x00000000
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) == 0

    await machine.clock_step(125_000)
    assert await machine.readl(FRINDEX) == 0x00001236
    assert await machine.readl(USBSTS) == 0x00000080

    await machine.writel(FRINDEX, 0x00003FFF)
    await machine.writel(USBSTS, 0x00000088)
    await machine.clock_step(125_000)
    assert await machine.readl(FRINDEX) == 0x00000000
    assert await machine.readl(USBSTS) == 0x00000088

    await machine.writel(USBSTS, 0x00000088)
    await machine.writel(USBCMD, 0x00080031)
    assert await machine.readl(USBSTS) == 0x0000C000
    await machine.writel(USBCMD, 0x00000000)
    assert await machine.readl(USBSTS) == 0x00001000

    await machine.writel(USBCMD, 0x00000002)
    await machine.writel(USBMODE, 0x00000002)
    await machine.writel(FRINDEX, 0x00001234)
    assert await machine.readl(FRINDEX) == 0x00000000


@pytest.mark.asyncio
async def test_usb_addr_sched_and_iaa_contract(machine):
    """USBCTRL addr/sched and IAA contract"""
    USBCMD = USB_BASE + 0x140
    USBSTS = USB_BASE + 0x144
    USBMODE = USB_BASE + 0x1A8
    DEVICEADDR = USB_BASE + 0x154
    ENDPTLISTADDR = USB_BASE + 0x158

    await machine.writel(USBCMD, 0x00000002)
    assert await machine.readl(USBCMD) == 0x00080000

    await machine.writel(DEVICEADDR, 0x12000000)
    assert await machine.readl(DEVICEADDR) == 0x12000000, (
        "USBCTRL DEVICEADDR with USBADRA=0 must update USBADR immediately"
    )

    await machine.writel(DEVICEADDR, 0x23000000 | (1 << 24))
    assert ((await machine.readl(DEVICEADDR)) & (1 << 24)) == (1 << 24), (
        "USBCTRL DEVICEADDR.USBADRA must read back 1 while staged"
    )
    assert ((await machine.readl(DEVICEADDR)) & 0xFE000000) == 0x12000000, (
        "USBCTRL DEVICEADDR.USBADR must keep the old value while staged"
    )

    await machine.writel(USBCMD, 0x00000002)
    assert await machine.readl(USBCMD) == 0x00080000
    assert await machine.readl(DEVICEADDR) == 0, (
        "USBCTRL controller reset must clear DEVICEADDR and USBADRA"
    )

    await machine.writel(ENDPTLISTADDR, 0xFFFFFFFF)
    assert await machine.readl(ENDPTLISTADDR) == 0xFFFFF800, (
        "USBCTRL ENDPTLISTADDR in device mode must keep EPBASE[31:11]"
    )

    await machine.writel(USBMODE, 0x00000003)
    assert await machine.readl(USBMODE) == 0x00000003

    await machine.writel(DEVICEADDR, 0xFFFFFFFF)
    assert await machine.readl(DEVICEADDR) == 0xFFFFF000, (
        "USBCTRL PERIODICLISTBASE in host mode must keep PERBASE[31:12]"
    )

    await machine.writel(ENDPTLISTADDR, 0xFFFFFFFF)
    assert await machine.readl(ENDPTLISTADDR) == 0xFFFFFFE0, (
        "USBCTRL ASYNCLISTADDR in host mode must keep ASYBASE[31:5]"
    )

    await machine.writel(USBSTS, 0xFFFFFFFF & 0x030C01FF)
    assert ((await machine.readl(USBSTS)) & 0x20) == 0
    await machine.writel(USBCMD, 0x00080040)
    assert ((await machine.readl(USBCMD)) & 0x40) == 0, (
        "USBCTRL USBCMD.IAA must self-clear after doorbell write"
    )
    assert ((await machine.readl(USBSTS)) & 0x20) == 0x20, (
        "USBCTRL USBSTS.AAI must be set after IAA doorbell in host mode"
    )

    await machine.writel(USBSTS, 0x00000020)
    assert ((await machine.readl(USBSTS)) & 0x20) == 0

    await machine.writel(USBCMD, 0x00000002)
    await machine.writel(USBMODE, 0x00000002)
    await machine.writel(USBSTS, 0xFFFFFFFF & 0x030C01FF)
    await machine.writel(USBCMD, 0x00080040)
    assert ((await machine.readl(USBSTS)) & 0x20) == 0, (
        "USBCTRL USBSTS.AAI must remain clear in device mode"
    )


@pytest.mark.asyncio
async def test_usb_device_transfer_contract(machine):
    """USBCTRL device transfer contract"""
    USBCMD = USB_BASE + 0x140
    USBSTS = USB_BASE + 0x144
    USBINTR = USB_BASE + 0x148
    USBMODE = USB_BASE + 0x1A8
    ENDPTLISTADDR = USB_BASE + 0x158
    ENDPTSETUPSTAT = USB_BASE + 0x1AC
    ENDPTPRIME = USB_BASE + 0x1B0
    ENDPTSTAT = USB_BASE + 0x1B8
    ENDPTCOMPLETE = USB_BASE + 0x1BC
    ENDPTCTRL0 = USB_BASE + 0x1C0

    VH_ACTION = USB_BASE + 0x800
    VH_SETUP_LO = USB_BASE + 0x804
    VH_SETUP_HI = USB_BASE + 0x808
    VH_OUT_ADDR = USB_BASE + 0x80C
    VH_OUT_LEN = USB_BASE + 0x810
    VH_IN_STATUS = USB_BASE + 0x814

    DQH_SIZE = 64
    DTD_ACTIVE = 1
    DTD_IOC = 1 << 15
    DTD_TERMINATE = 1

    QH_BASE = 0x00010000
    EP0_RX_QH = QH_BASE + 0 * DQH_SIZE
    EP0_TX_QH = QH_BASE + 1 * DQH_SIZE
    IN_DATA_BUF = 0x00010400
    OUT_DATA_BUF = 0x00010800

    await machine.writel(USBCMD, 0x00000002)
    assert await machine.readl(USBCMD) == 0x00080000
    await machine.writel(USBMODE, 0x00000002)
    assert await machine.readl(USBMODE) == 0x00000002

    await machine.writel(ENDPTLISTADDR, QH_BASE)
    assert await machine.readl(ENDPTLISTADDR) == QH_BASE, (
        "USBCTRL ENDPTLISTADDR must accept the dQH base address"
    )

    await machine.writel(USBINTR, 0x00000001)

    tx_qh_overlay = EP0_TX_QH + 0x08
    await machine.writel(tx_qh_overlay + 0x00, DTD_TERMINATE)
    await machine.writel(tx_qh_overlay + 0x04, DTD_ACTIVE | DTD_IOC | (8 << 16))
    await machine.writel(tx_qh_overlay + 0x08, IN_DATA_BUF)

    await machine.writel(IN_DATA_BUF, 0x44332211)
    await machine.writel(IN_DATA_BUF + 4, 0x88776655)

    await machine.writel(ENDPTPRIME, 1 << 16)
    assert ((await machine.readl(ENDPTSTAT)) & (1 << 16)) == (1 << 16), (
        "USBCTRL ENDPTPRIME for EP0 TX must set ENDPTSTAT bit 16"
    )

    await machine.writel(VH_ACTION, ((1 << 5) | 0 | (1 << 31)) & 0xFFFFFFFF)

    assert ((await machine.readl(ENDPTCOMPLETE)) & (1 << 16)) == (1 << 16), (
        "USBCTRL IN transfer must set ENDPTCOMPLETE TX bit for EP0"
    )
    assert ((await machine.readl(ENDPTSTAT)) & (1 << 16)) == 0, (
        "USBCTRL ENDPTSTAT must clear after IN transfer completes"
    )
    assert ((await machine.readl(USBSTS)) & 0x01) == 0x01, (
        "USBCTRL IN transfer must set USBSTS.UI"
    )
    assert ((await machine.readl(ICOLL_BASE + 0x040)) & (1 << 11)) != 0, (
        "USBCTRL UI interrupt must assert ICOLL source 11"
    )

    tx_token = await machine.readl(tx_qh_overlay + 0x04)
    assert (tx_token & DTD_ACTIVE) == 0, (
        "USBCTRL IN transfer must clear dTD active bit"
    )
    assert ((tx_token >> 16) & 0x7FFF) == 8, (
        "USBCTRL IN transfer must record 8 bytes transferred in dTD"
    )

    assert await machine.readl(VH_IN_STATUS) == 8, (
        "USBCTRL virtual host IN status must report 8 bytes transferred"
    )

    await machine.writel(ENDPTCOMPLETE, 1 << 16)
    await machine.writel(USBSTS, 0x01)
    assert (await machine.readl(USBSTS) & 0x01) == 0

    OUT_RECV_BUF = IN_DATA_BUF + 0x200
    rx_qh_overlay = EP0_RX_QH + 0x08
    await machine.writel(rx_qh_overlay + 0x00, DTD_TERMINATE)
    await machine.writel(rx_qh_overlay + 0x04, DTD_ACTIVE | DTD_IOC | (16 << 16))
    await machine.writel(rx_qh_overlay + 0x08, OUT_RECV_BUF)

    for i in range(4):
        await machine.writel(
            OUT_DATA_BUF + i * 4,
            (0xAABBCCDD ^ (i << 24)) & 0xFFFFFFFF,
        )

    await machine.writel(ENDPTPRIME, 1 << 0)
    assert ((await machine.readl(ENDPTSTAT)) & (1 << 0)) == (1 << 0), (
        "USBCTRL ENDPTPRIME for EP0 RX must set ENDPTSTAT bit 0"
    )

    await machine.writel(VH_OUT_ADDR, OUT_DATA_BUF)
    await machine.writel(VH_OUT_LEN, 16)
    await machine.writel(VH_ACTION, ((2 << 5) | 0 | (1 << 31)) & 0xFFFFFFFF)

    assert ((await machine.readl(ENDPTCOMPLETE)) & (1 << 0)) == (1 << 0), (
        "USBCTRL OUT transfer must set ENDPTCOMPLETE RX bit for EP0"
    )
    assert ((await machine.readl(USBSTS)) & 0x01) == 0x01, (
        "USBCTRL OUT transfer must set USBSTS.UI"
    )

    rx_token = await machine.readl(rx_qh_overlay + 0x04)
    assert (rx_token & DTD_ACTIVE) == 0, (
        "USBCTRL OUT transfer must clear dTD active bit"
    )
    assert ((rx_token >> 16) & 0x7FFF) == 16, (
        "USBCTRL OUT transfer must record 16 bytes transferred in dTD"
    )

    for i in range(4):
        assert await machine.readl(OUT_RECV_BUF + i * 4) == (
            (0xAABBCCDD ^ (i << 24)) & 0xFFFFFFFF
        ), (
            f"USBCTRL OUT transfer must write correct data to dTD buffer word {i}"
        )

    await machine.writel(ENDPTCOMPLETE, 1 << 0)
    await machine.writel(USBSTS, 0x01)

    setup_lo = 0x01234567
    setup_hi = 0x89ABCDEF & 0xFFFFFFFF
    await machine.writel(VH_SETUP_LO, setup_lo)
    await machine.writel(VH_SETUP_HI, setup_hi)
    await machine.writel(VH_ACTION, ((0 << 5) | 0 | (1 << 31)) & 0xFFFFFFFF)

    assert ((await machine.readl(ENDPTSETUPSTAT)) & 0x01) == 0x01, (
        "USBCTRL SETUP injection must set ENDPTSETUPSTAT for EP0"
    )
    assert ((await machine.readl(USBSTS)) & 0x01) == 0x01, (
        "USBCTRL SETUP injection must set USBSTS.UI"
    )
    assert await machine.readl(EP0_RX_QH + 0x2C) == setup_lo, (
        "USBCTRL SETUP injection must write SETUP bytes 0-3 to dQH setup buffer"
    )
    assert await machine.readl(EP0_RX_QH + 0x30) == setup_hi, (
        "USBCTRL SETUP injection must write SETUP bytes 4-7 to dQH setup buffer"
    )

    await machine.writel(ENDPTSETUPSTAT, 0x01)
    await machine.writel(USBSTS, 0x01)
    assert await machine.readl(ENDPTSETUPSTAT) == 0
    assert (await machine.readl(USBSTS) & 0x01) == 0
