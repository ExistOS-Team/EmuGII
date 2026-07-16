/*
 * STMP3770 SPDIF Transmitter
 *
 * Register file, TX FIFO and DMA request model per PDF Chapter 26
 * (Tables 1026-1039).  No external SPDIF line consumer exists in this
 * emulation; the sample stream drains at the programmed SRR sample rate
 * so that FIFO occupancy, overflow/underflow and the DMAREQ toggle stay
 * observable.  The pcm_spdif_clk generation inside CLKCTRL
 * (HW_CLKCTRL_SPDIF) is not modeled; frame timing derives from
 * HW_SPDIF_SRR instead.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/audio/stmp3770_spdif.h"
#include "hw/irq.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "qemu/timer.h"

#define SPDIF_MMIO_SIZE         0x2000

#define REG_CTRL                0x000
#define REG_STAT                0x010
#define REG_FRAMECTRL           0x020
#define REG_SRR                 0x030
#define REG_DEBUG               0x040
#define REG_DATA                0x050
#define REG_VERSION             0x060

#define REG_SET                 0x4
#define REG_CLR                 0x8
#define REG_TOG                 0xc

#define CTRL_RUN                (1U << 0)
#define CTRL_FIFO_ERROR_IRQ_EN  (1U << 1)
#define CTRL_FIFO_OVERFLOW_IRQ  (1U << 2)
#define CTRL_FIFO_UNDERFLOW_IRQ (1U << 3)
#define CTRL_WORD_LENGTH        (1U << 4)
#define CTRL_WAIT_END_XFER      (1U << 5)
#define CTRL_DMAWAIT_COUNT      (0x1fU << 16)
#define CTRL_CLKGATE            (1U << 30)
#define CTRL_SFTRST             (1U << 31)

#define CTRL_WRITABLE_MASK      0xc01f003fU
#define CTRL_RESET              0xc0000020U
#define FRAMECTRL_WRITABLE_MASK 0x000377ffU
#define FRAMECTRL_RESET         0x00020000U
#define SRR_WRITABLE_MASK       0x700fffffU
#define SRR_RESET               0x10000000U

#define FRAMECTRL_AUTO_MUTE     (1U << 16)

#define STAT_PRESENT            (1U << 31)
#define STAT_END_XFER           (1U << 0)

/* Bits 3:2 of CTRL are W1C status bits (PDF Tables 1026/1027). */
#define CTRL_IRQ_STATUS_BITS    (CTRL_FIFO_UNDERFLOW_IRQ | CTRL_FIFO_OVERFLOW_IRQ)

struct STMP3770SPDIFState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq;
    STMP3770DMAState *dma;
    int dma_channel;
    QEMUTimer *frame_timer;

    uint32_t ctrl;
    uint32_t framectrl;
    uint32_t srr;
    uint32_t fifo[8];
    uint32_t fifo_count;
    bool converting;
    bool end_xfer;
    bool dma_preq;
};

static uint32_t spdif_fifo_capacity(const STMP3770SPDIFState *s)
{
    /* PDF Table 1027: 8 words in 16-bit mode, 4 words in 32-bit mode. */
    return (s->ctrl & CTRL_WORD_LENGTH) ? 8 : 4;
}

static uint32_t spdif_frame_words(const STMP3770SPDIFState *s)
{
    /* One SPDIF frame carries one left and one right sample. */
    return (s->ctrl & CTRL_WORD_LENGTH) ? 1 : 2;
}

static uint32_t spdif_sample_rate(const STMP3770SPDIFState *s)
{
    uint32_t rate = 48000;

    switch (s->srr & 0xfffffU) {
    case 0x07d00:
        rate = 32000;
        break;
    case 0x0ac44:
        rate = 44100;
        break;
    case 0x0bb80:
        rate = 48000;
        break;
    default:
        break;
    }
    if (((s->srr >> 28) & 7) == 2) {
        rate *= 2;
    }
    return rate;
}

static void spdif_update_timer(STMP3770SPDIFState *s)
{
    uint64_t period;

    if (!(s->ctrl & CTRL_RUN) || (s->ctrl & (CTRL_SFTRST | CTRL_CLKGATE)) ||
        !s->converting) {
        timer_del(s->frame_timer);
        return;
    }
    period = NANOSECONDS_PER_SECOND / spdif_sample_rate(s);
    timer_mod(s->frame_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + period);
}

static void spdif_update_irq(STMP3770SPDIFState *s)
{
    qemu_set_irq(s->irq,
                 (s->ctrl & CTRL_FIFO_ERROR_IRQ_EN) &&
                 (s->ctrl & CTRL_IRQ_STATUS_BITS));
}

static void spdif_frame_tick(void *opaque)
{
    STMP3770SPDIFState *s = opaque;
    uint32_t frame = spdif_frame_words(s);

    if (!(s->ctrl & CTRL_RUN) || !s->converting) {
        return;
    }
    if (s->fifo_count >= frame) {
        s->fifo_count -= frame;
        memmove(s->fifo, s->fifo + frame, s->fifo_count * sizeof(uint32_t));
        /* Each freed word space toggles the DMA request line. */
        s->dma_preq = !s->dma_preq;
    } else {
        /*
         * Empty frame while transmitting: PDF sends the last sample for
         * four frames before muting; the underflow status is raised on
         * the first empty frame here (the analog stream is not modeled).
         */
        s->ctrl |= CTRL_FIFO_UNDERFLOW_IRQ;
    }
    spdif_update_irq(s);
    spdif_update_timer(s);
}

static void spdif_reset_registers(STMP3770SPDIFState *s)
{
    s->ctrl = CTRL_RESET;
    s->framectrl = FRAMECTRL_RESET;
    s->srr = SRR_RESET;
    s->fifo_count = 0;
    s->converting = false;
    s->end_xfer = false;
    s->dma_preq = false;
    spdif_update_irq(s);
    spdif_update_timer(s);
}

static uint32_t spdif_apply_sct(uint32_t old, uint32_t value, uint32_t mask,
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

static void spdif_fifo_push(STMP3770SPDIFState *s, uint32_t value)
{
    if (s->ctrl & (CTRL_SFTRST | CTRL_CLKGATE)) {
        return;
    }
    if (s->fifo_count >= spdif_fifo_capacity(s)) {
        s->ctrl |= CTRL_FIFO_OVERFLOW_IRQ;
        spdif_update_irq(s);
        return;
    }
    s->fifo[s->fifo_count++] = value;
    if ((s->ctrl & CTRL_RUN) && s->fifo_count == spdif_fifo_capacity(s)) {
        /* PDF: conversion begins when the FIFO is filled. */
        s->converting = true;
        s->end_xfer = false;
        spdif_update_timer(s);
    }
}

static uint64_t spdif_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770SPDIFState *s = STMP3770_SPDIF(opaque);
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-spdif: unsupported read size %u\n",
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
    case REG_STAT:
        return STAT_PRESENT | (s->end_xfer ? STAT_END_XFER : 0);
    case REG_FRAMECTRL:
        return s->framectrl;
    case REG_SRR:
        return s->srr;
    case REG_DEBUG:
        return (s->dma_preq ? 2 : 0) |
               (s->fifo_count < spdif_fifo_capacity(s) ? 1 : 0);
    case REG_DATA:
        return 0;
    case REG_VERSION:
        return 0x01010000;
    default:
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-spdif: read from offset 0x%"
                      HWADDR_PRIx "\n", offset);
        return 0;
    }
}

static void spdif_write(void *opaque, hwaddr offset, uint64_t value,
                        unsigned size)
{
    STMP3770SPDIFState *s = STMP3770_SPDIF(opaque);
    uint32_t val = value;
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    uint32_t old_ctrl;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-spdif: unsupported write size %u\n",
                      size);
        return;
    }

    switch (base) {
    case REG_CTRL:
        old_ctrl = s->ctrl;
        s->ctrl = spdif_apply_sct(s->ctrl, val, CTRL_WRITABLE_MASK, modifier);
        /* FIFO error status bits are W1C via the SCT clear alias only. */
        if (modifier == REG_SET) {
            s->ctrl |= old_ctrl & CTRL_IRQ_STATUS_BITS;
            s->ctrl |= val & CTRL_IRQ_STATUS_BITS;
        } else if (modifier == 0 || modifier == REG_TOG) {
            s->ctrl = (s->ctrl & ~CTRL_IRQ_STATUS_BITS) |
                      (old_ctrl & CTRL_IRQ_STATUS_BITS);
        }
        if (s->ctrl & CTRL_SFTRST) {
            spdif_reset_registers(s);
            return;
        }
        if ((s->ctrl ^ old_ctrl) & CTRL_RUN) {
            if (s->ctrl & CTRL_RUN) {
                s->end_xfer = false;
                if (s->fifo_count == spdif_fifo_capacity(s)) {
                    s->converting = true;
                }
            } else if (s->fifo_count == 0 && s->converting) {
                s->end_xfer = true;
                s->converting = false;
            }
        }
        if ((s->ctrl ^ old_ctrl) & CTRL_CLKGATE) {
            /* CLKGATE gates sample consumption in both directions. */
        }
        spdif_update_irq(s);
        spdif_update_timer(s);
        return;
    case REG_STAT:
    case REG_DEBUG:
    case REG_VERSION:
        /* Read-only registers; writes (and SCT aliases) are ignored. */
        return;
    case REG_FRAMECTRL:
        s->framectrl = spdif_apply_sct(s->framectrl, val,
                                       FRAMECTRL_WRITABLE_MASK, modifier);
        return;
    case REG_SRR:
        s->srr = spdif_apply_sct(s->srr, val, SRR_WRITABLE_MASK, modifier);
        spdif_update_timer(s);
        return;
    case REG_DATA:
        /* Every address in the DATA window pushes one FIFO word. */
        spdif_fifo_push(s, val);
        return;
    default:
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-spdif: write to offset 0x%"
                      HWADDR_PRIx "\n", offset);
        return;
    }
}

static const MemoryRegionOps spdif_ops = {
    .read = spdif_read,
    .write = spdif_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static int stmp3770_spdif_dma_handler(STMP3770DMAState *dma, int channel,
                                      STMP3770DMAEvent event, void *buf,
                                      size_t len, void *opaque)
{
    STMP3770SPDIFState *s = STMP3770_SPDIF(opaque);
    uint32_t *pio = (uint32_t *)buf;
    size_t i;

    if (event == STMP3770_DMA_EVENT_PIO) {
        for (i = 0; i + 1 <= len / sizeof(uint32_t) && i < 2; i++) {
            spdif_write(s, i == 0 ? REG_CTRL : REG_FRAMECTRL, pio[i], 4);
        }
        return (int)len;
    }
    if (event == STMP3770_DMA_EVENT_DATA_WRITE) {
        for (i = 0; i + 4 <= len; i += 4) {
            spdif_fifo_push(s, pio[i / 4]);
        }
        return (int)i;
    }
    return 0;
}

void stmp3770_spdif_set_dma(STMP3770SPDIFState *s, STMP3770DMAState *dma,
                            int channel)
{
    s->dma = dma;
    s->dma_channel = channel;

    if (!dma) {
        return;
    }
    stmp3770_dma_set_channel_handler(dma, channel,
                                     stmp3770_spdif_dma_handler, s);
}

static void spdif_reset(DeviceState *dev)
{
    spdif_reset_registers(STMP3770_SPDIF(dev));
}

static void spdif_realize(DeviceState *dev, Error **errp)
{
    STMP3770SPDIFState *s = STMP3770_SPDIF(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    memory_region_init_io(&s->iomem, OBJECT(dev), &spdif_ops, s,
                          TYPE_STMP3770_SPDIF, SPDIF_MMIO_SIZE);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
    s->frame_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, spdif_frame_tick, s);
}

static int spdif_post_load(void *opaque, int version_id)
{
    spdif_update_timer(STMP3770_SPDIF(opaque));
    return 0;
}

static const VMStateDescription vmstate_spdif = {
    .name = "stmp3770-spdif",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = spdif_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl, STMP3770SPDIFState),
        VMSTATE_UINT32(framectrl, STMP3770SPDIFState),
        VMSTATE_UINT32(srr, STMP3770SPDIFState),
        VMSTATE_UINT32_ARRAY(fifo, STMP3770SPDIFState, 8),
        VMSTATE_UINT32(fifo_count, STMP3770SPDIFState),
        VMSTATE_BOOL(converting, STMP3770SPDIFState),
        VMSTATE_BOOL(end_xfer, STMP3770SPDIFState),
        VMSTATE_BOOL(dma_preq, STMP3770SPDIFState),
        VMSTATE_END_OF_LIST()
    }
};

static void spdif_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = spdif_realize;
    device_class_set_legacy_reset(dc, spdif_reset);
    dc->vmsd = &vmstate_spdif;
}

static const TypeInfo spdif_type_info = {
    .name = TYPE_STMP3770_SPDIF,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770SPDIFState),
    .class_init = spdif_class_init,
};

static void spdif_register_types(void)
{
    type_register_static(&spdif_type_info);
}

type_init(spdif_register_types)
