# Common APBH/APBX DMA descriptor bits
DMA_CMD_NO_DMA_XFER = 0
DMA_CMD_DMA_WRITE = 1
DMA_CMD_DMA_READ = 2
DMA_CMD_DMA_SENSE = 3

DMA_CHAIN = 1 << 2
DMA_IRQONCMPLT = 1 << 3
DMA_NANDWAIT4READY = 1 << 5
DMA_SEMAPHORE = 1 << 6
DMA_WAIT4ENDCMD = 1 << 7
DMA_ONE_PIO_WORD = 1 << 12

GPMI_RUN_BIT = 1 << 29


async def write_descriptor(machine, address, nxt, command, bar=0, ctrl0=None):
    """Write an APBH/APBX DMA descriptor to memory.

    Layout (32-bit words):
      +0x00: nxtcmdar
      +0x04: command
      +0x08: bar
      +0x0c: pio_words[0] (optional)
    """
    await machine.writel(address + 0x00, nxt)
    await machine.writel(address + 0x04, command)
    await machine.writel(address + 0x08, bar)
    if ctrl0 is not None:
        await machine.writel(address + 0x0C, ctrl0)


async def write_descriptor_and_kick(machine, nxt, sema, desc):
    await write_descriptor(machine, desc)
    await machine.writel(nxt, desc)
    await machine.writel(sema, 1)
