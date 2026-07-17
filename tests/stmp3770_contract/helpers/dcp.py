from framework.constants import DCP_BASE


async def dcp_enable_channel0(machine):
    await machine.writel(DCP_BASE + 0x008, 0xC0000000)
    await machine.writel(DCP_BASE + 0x024, 0x00000001)
    await machine.writel(DCP_BASE + 0x004, 0x00000001)


async def dcp_write_descriptor(
    machine,
    addr,
    *,
    nxt=0,
    ctrl0,
    ctrl1=0,
    source=0,
    destination=0,
    size=0,
    payload=0,
):
    await machine.writel(addr + 0x00, nxt)
    await machine.writel(addr + 0x04, ctrl0)
    await machine.writel(addr + 0x08, ctrl1)
    await machine.writel(addr + 0x0C, source)
    await machine.writel(addr + 0x10, destination)
    await machine.writel(addr + 0x14, size)
    await machine.writel(addr + 0x18, payload)
    await machine.writel(addr + 0x1C, 0)


async def dcp_kick_channel0(machine, descriptor, semaphore):
    await machine.writel(DCP_BASE + 0x100, descriptor)
    await machine.writel(DCP_BASE + 0x110, semaphore)


async def dcp_kick(machine, channel, descriptor, semaphore):
    await machine.writel(DCP_BASE + 0x100 + channel * 0x40, descriptor)
    await machine.writel(DCP_BASE + 0x110 + channel * 0x40, semaphore)
