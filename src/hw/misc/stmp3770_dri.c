/*
 * STMP3770 Digital Radio Interface (DRI)
 *
 * Register file and DMA FIFO model per PDF Chapter 27 (Tables 1042-1053).
 * The DRI receiver front-end (DRI_CLK/DRI_DATA from the STFM1000 radio)
 * has no external driver in this emulation: the digital inputs read as
 * idle, no frames are received and the RX FIFO stays empty.  No line
 * state is fabricated; only register, FIFO and interrupt-gating
 * semantics are modeled.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/misc/stmp3770_dri.h"
#include "hw/irq.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"

#define DRI_MMIO_SIZE           0x2000

#define REG_CTRL                0x000
#define REG_TIMING              0x010
#define REG_STAT                0x020
#define REG_DATA                0x030
#define REG_DEBUG0              0x040
#define REG_DEBUG1              0x050

#define REG_SET                 0x4
#define REG_CLR                 0x8
#define REG_TOG                 0xc

#define CTRL_RUN                (1U << 0)
#define CTRL_ATTENTION_IRQ      (1U << 1)
#define CTRL_PILOT_SYNC_IRQ     (1U << 2)
#define CTRL_OVERFLOW_IRQ       (1U << 3)
#define CTRL_ATTENTION_IRQ_EN   (1U << 9)
#define CTRL_PILOT_SYNC_IRQ_EN  (1U << 10)
#define CTRL_OVERFLOW_IRQ_EN    (1U << 11)
#define CTRL_REACQUIRE_PHASE    (1U << 15)
#define CTRL_STOP_ON_PILOT      (1U << 25)
#define CTRL_STOP_ON_OFLOW      (1U << 26)
#define CTRL_ENABLE_INPUTS      (1U << 29)
#define CTRL_CLKGATE            (1U << 30)
#define CTRL_SFTRST             (1U << 31)

#define CTRL_WRITABLE_MASK      0xe61f8e0fU
#define CTRL_RESET              0xc0010000U
#define CTRL_IRQ_STATUS_BITS    (CTRL_OVERFLOW_IRQ | CTRL_PILOT_SYNC_IRQ | \
                                 CTRL_ATTENTION_IRQ)
#define CTRL_IRQ_ENABLE_BITS    (CTRL_OVERFLOW_IRQ_EN | \
                                 CTRL_PILOT_SYNC_IRQ_EN | \
                                 CTRL_ATTENTION_IRQ_EN)

#define TIMING_WRITABLE_MASK    0x000f00ffU
#define TIMING_RESET            0x00080010U

#define STAT_PRESENT            (1U << 31)
#define STAT_ATTENTION_SUMMARY  (1U << 1)
#define STAT_PILOT_SUMMARY      (1U << 2)
#define STAT_OVERFLOW_SUMMARY   (1U << 3)

#define DEBUG0_WRITABLE_MASK    0x0ffc0000U
#define DEBUG1_WRITABLE_MASK    0xf8000000U

struct STMP3770DRIState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq;
    STMP3770DMAState *dma;
    int dma_channel;

    uint32_t ctrl;
    uint32_t timing;
    uint32_t debug0;
    uint32_t debug1;
};

static void dri_update_irq(STMP3770DRIState *s)
{
    uint32_t status = s->ctrl & CTRL_IRQ_STATUS_BITS;
    uint32_t enable = (s->ctrl & CTRL_IRQ_ENABLE_BITS) >> 8;
    uint32_t pending = status & enable;

    qemu_set_irq(s->irq, pending != 0);
}

static void dri_reset_registers(STMP3770DRIState *s)
{
    s->ctrl = CTRL_RESET;
    s->timing = TIMING_RESET;
    s->debug0 = 0;
    s->debug1 = 0;
    dri_update_irq(s);
}

static uint32_t dri_apply_sct(uint32_t old, uint32_t value, uint32_t mask,
                              unsigned int modifier)
{
    uint32_t writable = old & mask;

    switch (modifier) {
    case REG_SET:
        writable |= value & mask;
        break;
    case REG_CLR:
        writable &= ~(value & mask);
        break;
    case REG_TOG:
        writable ^= value & mask;
        break;
    default:
        writable = value & mask;
        break;
    }

    return (old & ~mask) | writable;
}

static uint64_t dri_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770DRIState *s = STMP3770_DRI(opaque);
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    uint32_t status;
    uint32_t enable;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dri: unsupported read size %u\n",
                      size);
        return 0;
    }
    if (modifier) {
        /* SCT aliases read as zero. */
        return 0;
    }

    switch (base) {
    case REG_CTRL:
        return s->ctrl;
    case REG_TIMING:
        return s->timing;
    case REG_STAT:
        status = s->ctrl & CTRL_IRQ_STATUS_BITS;
        enable = (s->ctrl & CTRL_IRQ_ENABLE_BITS) >> 8;
        return STAT_PRESENT | (status & enable);
    case REG_DATA:
        /* RX FIFO is empty without an external radio front-end. */
        return 0;
    case REG_DEBUG0:
        return s->debug0 & DEBUG0_WRITABLE_MASK;
    case REG_DEBUG1:
        return s->debug1 & DEBUG1_WRITABLE_MASK;
    default:
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dri: read from offset 0x%"
                      HWADDR_PRIx "\n", offset);
        return 0;
    }
}

static void dri_write(void *opaque, hwaddr offset, uint64_t value,
                      unsigned size)
{
    STMP3770DRIState *s = STMP3770_DRI(opaque);
    uint32_t val = value;
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    uint32_t old_ctrl;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dri: unsupported write size %u\n",
                      size);
        return;
    }

    switch (base) {
    case REG_CTRL:
        old_ctrl = s->ctrl;
        s->ctrl = dri_apply_sct(s->ctrl, val, CTRL_WRITABLE_MASK, modifier);
        /* Interrupt status bits are W1C via the SCT clear alias only. */
        if (modifier == 0 || modifier == REG_TOG) {
            s->ctrl = (s->ctrl & ~CTRL_IRQ_STATUS_BITS) |
                      (old_ctrl & CTRL_IRQ_STATUS_BITS);
        }
        if (s->ctrl & CTRL_SFTRST) {
            dri_reset_registers(s);
            return;
        }
        dri_update_irq(s);
        return;
    case REG_TIMING:
        if (modifier == 0) {
            s->timing = val & TIMING_WRITABLE_MASK;
        }
        return;
    case REG_STAT:
    case REG_DATA:
        /* Read-only status and the RX FIFO output. */
        return;
    case REG_DEBUG0:
        s->debug0 = dri_apply_sct(s->debug0, val, DEBUG0_WRITABLE_MASK,
                                  modifier);
        return;
    case REG_DEBUG1:
        s->debug1 = dri_apply_sct(s->debug1, val, DEBUG1_WRITABLE_MASK,
                                  modifier);
        return;
    default:
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dri: write to offset 0x%"
                      HWADDR_PRIx "\n", offset);
        return;
    }
}

static const MemoryRegionOps dri_ops = {
    .read = dri_read,
    .write = dri_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static int stmp3770_dri_dma_handler(STMP3770DMAState *dma, int channel,
                                    STMP3770DMAEvent event, void *buf,
                                    size_t len, void *opaque)
{
    STMP3770DRIState *s = STMP3770_DRI(opaque);
    uint32_t *pio = (uint32_t *)buf;

    if (event == STMP3770_DMA_EVENT_PIO) {
        if (len >= sizeof(uint32_t)) {
            dri_write(s, REG_CTRL, pio[0], 4);
        }
        return (int)len;
    }
    if (event == STMP3770_DMA_EVENT_DATA_READ) {
        /* No frames are received without an external radio front-end. */
        return 0;
    }
    if (event == STMP3770_DMA_EVENT_DATA_WRITE) {
        /* DRI is a receive-only interface; DMA writes are discarded. */
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-dri: DMA write to receive-only DATA\n");
        return (int)len;
    }
    return 0;
}

void stmp3770_dri_set_dma(STMP3770DRIState *s, STMP3770DMAState *dma,
                          int channel)
{
    s->dma = dma;
    s->dma_channel = channel;

    if (!dma) {
        return;
    }
    stmp3770_dma_set_channel_handler(dma, channel,
                                     stmp3770_dri_dma_handler, s);
}

static void dri_reset(DeviceState *dev)
{
    dri_reset_registers(STMP3770_DRI(dev));
}

static void dri_realize(DeviceState *dev, Error **errp)
{
    STMP3770DRIState *s = STMP3770_DRI(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    memory_region_init_io(&s->iomem, OBJECT(dev), &dri_ops, s,
                          TYPE_STMP3770_DRI, DRI_MMIO_SIZE);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
}

static const VMStateDescription vmstate_dri = {
    .name = "stmp3770-dri",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl, STMP3770DRIState),
        VMSTATE_UINT32(timing, STMP3770DRIState),
        VMSTATE_UINT32(debug0, STMP3770DRIState),
        VMSTATE_UINT32(debug1, STMP3770DRIState),
        VMSTATE_END_OF_LIST()
    }
};

static void dri_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = dri_realize;
    device_class_set_legacy_reset(dc, dri_reset);
    dc->vmsd = &vmstate_dri;
}

static const TypeInfo dri_type_info = {
    .name = TYPE_STMP3770_DRI,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770DRIState),
    .class_init = dri_class_init,
};

static void dri_register_types(void)
{
    type_register_static(&dri_type_info);
}

type_init(dri_register_types)
