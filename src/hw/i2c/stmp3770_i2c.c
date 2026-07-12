/*
 * STMP3770 I2C controller
 *
 * Based on STMP3770 Reference Manual Chapter 24
 *
 * Features:
 * - Minimal register stub sufficient for firmware probing
 * - Reports bus free and acknowledges all writes
 * - Supports SET/CLR/TOG aliases
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include "qemu/osdep.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "hw/i2c/stmp3770_i2c.h"
#include "hw/dma/stmp3770_dma.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"

/* SET/CLR/TOG sub-offsets */
#define SCT_SET 0x4
#define SCT_CLR 0x8
#define SCT_TOG 0xC

static inline bool stmp3770_i2c_enabled(STMP3770I2CState *s)
{
    return (s->ctrl0 & (I2C_CTRL0_SFTRST | I2C_CTRL0_CLKGATE)) == 0;
}

static void stmp3770_i2c_apply_sct(uint32_t *reg, uint32_t value, int sct,
                                    uint32_t writable_mask)
{
    value &= writable_mask;

    switch (sct) {
    case SCT_SET:
        *reg |= value;
        break;
    case SCT_CLR:
        *reg &= ~value;
        break;
    case SCT_TOG:
        *reg ^= value;
        break;
    default:
        *reg = (*reg & ~writable_mask) | value;
        break;
    }
}

static void stmp3770_i2c_update_irq(STMP3770I2CState *s)
{
    uint32_t pending = (s->ctrl1 & I2C_CTRL1_STATUS_MASK) &
                       ((s->ctrl1 & I2C_CTRL1_ENABLE_MASK) >> 8);

    qemu_set_irq(s->irq_error, pending != 0);
}

static bool stmp3770_i2c_fifo_push(STMP3770I2CState *s, uint8_t byte)
{
    if (s->fifo_count >= I2C_FIFO_DEPTH) {
        return false;
    }

    s->fifo[s->fifo_wptr] = byte;
    s->fifo_wptr = (s->fifo_wptr + 1) % I2C_FIFO_DEPTH;
    s->fifo_count++;
    return true;
}

static bool stmp3770_i2c_fifo_pop(STMP3770I2CState *s, uint8_t *byte)
{
    if (s->fifo_count == 0) {
        return false;
    }

    *byte = s->fifo[s->fifo_rptr];
    s->fifo_rptr = (s->fifo_rptr + 1) % I2C_FIFO_DEPTH;
    s->fifo_count--;
    return true;
}

static void stmp3770_i2c_update_debug0_state(STMP3770I2CState *s)
{
    s->debug0 = (s->debug0 & 0x1C000800) |
                (s->data_engine_busy ? (0x2U << 16) : 0);
}

static void stmp3770_i2c_complete(STMP3770I2CState *s)
{
    s->ctrl0 &= ~I2C_CTRL0_RUN;
    s->data_engine_busy = false;
    stmp3770_i2c_update_debug0_state(s);
    s->ctrl1 |= I2C_CTRL1_DATA_ENGINE_CMPLT_IRQ;
    stmp3770_i2c_update_irq(s);

    if (s->dma && s->dma_wait4endcmd) {
        s->dma_wait4endcmd = false;
        stmp3770_dma_complete_channel_command(s->dma, s->dma_channel);
    }
}

static uint32_t stmp3770_i2c_get_xfer_count(STMP3770I2CState *s)
{
    uint32_t count = s->ctrl0 & I2C_CTRL0_XFER_COUNT_MASK;

    return count ? count : (1U << 16);
}

static void stmp3770_i2c_process(STMP3770I2CState *s)
{
    uint8_t byte;

    if (!s->data_engine_busy || s->xfer_count == 0) {
        return;
    }

    if (s->ctrl0 & I2C_CTRL0_DIRECTION) {
        /* TRANSMIT: consume bytes from the FIFO */
        while (s->xfer_count > 0 && s->fifo_count > 0) {
            stmp3770_i2c_fifo_pop(s, &byte);
            s->xfer_count--;
        }
    } else {
        /* RECEIVE: produce bytes into the FIFO */
        while (s->xfer_count > 0 && s->fifo_count < I2C_FIFO_DEPTH) {
            stmp3770_i2c_fifo_push(s, 0xFF);
            s->xfer_count--;
        }
    }

    if (s->xfer_count == 0) {
        stmp3770_i2c_complete(s);
    }
}

static void stmp3770_i2c_reset(DeviceState *dev)
{
    STMP3770I2CState *s = STMP3770_I2C(dev);

    s->ctrl0 = I2C_CTRL0_SFTRST | I2C_CTRL0_CLKGATE;
    s->ctrl1 = 0x00860000;
    s->timing0 = 0x00780030;
    s->timing1 = 0x00800030;
    s->timing2 = 0x00300030;
    s->data = 0;
    s->debug0 = 0;
    s->debug1 = 0;

    s->fifo_count = 0;
    s->fifo_rptr = 0;
    s->fifo_wptr = 0;
    s->xfer_count = 0;
    s->data_engine_busy = false;
    s->dma_wait4endcmd = false;

    stmp3770_i2c_update_irq(s);
}

static uint64_t stmp3770_i2c_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770I2CState *s = STMP3770_I2C(opaque);

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-i2c: unsupported read size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return 0;
    }

    switch (offset) {
    case I2C_CTRL0:
    case I2C_CTRL0 + SCT_SET:
    case I2C_CTRL0 + SCT_CLR:
    case I2C_CTRL0 + SCT_TOG:
        return s->ctrl0;
    case I2C_TIMING0:
    case I2C_TIMING0 + SCT_SET:
    case I2C_TIMING0 + SCT_CLR:
    case I2C_TIMING0 + SCT_TOG:
        return s->timing0;
    case I2C_TIMING1:
    case I2C_TIMING1 + SCT_SET:
    case I2C_TIMING1 + SCT_CLR:
    case I2C_TIMING1 + SCT_TOG:
        return s->timing1;
    case I2C_TIMING2:
    case I2C_TIMING2 + SCT_SET:
    case I2C_TIMING2 + SCT_CLR:
    case I2C_TIMING2 + SCT_TOG:
        return s->timing2;
    case I2C_CTRL1:
    case I2C_CTRL1 + SCT_SET:
    case I2C_CTRL1 + SCT_CLR:
    case I2C_CTRL1 + SCT_TOG:
        return s->ctrl1;
    case I2C_STAT: {
        uint32_t pending = (s->ctrl1 & I2C_CTRL1_STATUS_MASK) &
                           ((s->ctrl1 & I2C_CTRL1_ENABLE_MASK) >> 8);
        uint32_t stat = 0xC0000000 | (pending ? (1U << 29) : 0) | pending;

        if (s->data_engine_busy) {
            stat |= (1U << 9)  /* DATA_ENGINE_BUSY */ |
                    (1U << 10) /* CLK_GEN_BUSY */ |
                    (1U << 11) /* BUS_BUSY */;
        }
        if (s->data_engine_busy) {
            bool transmit = (s->ctrl0 & I2C_CTRL0_DIRECTION) != 0;
            if ((transmit && s->fifo_count == 0) ||
                (!transmit && s->fifo_count == I2C_FIFO_DEPTH)) {
                stat |= (1U << 12); /* DATA_ENGINE_DMA_WAIT */
            }
        }
        return stat;
    }
    case I2C_DATA: {
        uint32_t val = 0;
        unsigned int i;

        if (!stmp3770_i2c_enabled(s)) {
            return s->data;
        }

        for (i = 0; i < size; i++) {
            uint8_t byte;
            if (!stmp3770_i2c_fifo_pop(s, &byte)) {
                break;
            }
            val |= (uint32_t)byte << (i * 8);
        }
        return val;
    }
    case I2C_DEBUG0:
    case I2C_DEBUG0 + SCT_SET:
    case I2C_DEBUG0 + SCT_CLR:
    case I2C_DEBUG0 + SCT_TOG:
        return 0x00100000 | s->debug0;
    case I2C_DEBUG1:
    case I2C_DEBUG1 + SCT_SET:
    case I2C_DEBUG1 + SCT_CLR:
    case I2C_DEBUG1 + SCT_TOG:
        return 0xC0000000 | s->debug1;
    case I2C_VERSION:
        return I2C_VERSION_VALUE;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-i2c: read from unimplemented offset "
                      HWADDR_FMT_plx "\n", offset);
        return 0;
    }
}

static void stmp3770_i2c_write(void *opaque, hwaddr offset,
                               uint64_t value, unsigned size)
{
    STMP3770I2CState *s = STMP3770_I2C(opaque);
    int sct = offset & 0xF;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-i2c: unsupported write size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return;
    }

    switch (offset & ~0xFULL) {
    case I2C_CTRL0:
        stmp3770_i2c_apply_sct(&s->ctrl0, (uint32_t)value, sct,
                                I2C_CTRL0_RW_MASK);
        if (s->ctrl0 & I2C_CTRL0_SFTRST) {
            stmp3770_i2c_reset(DEVICE(s));
        }
        if ((s->ctrl0 & I2C_CTRL0_RUN) && stmp3770_i2c_enabled(s) &&
            !s->data_engine_busy) {
            s->data_engine_busy = true;
            stmp3770_i2c_update_debug0_state(s);
            s->xfer_count = stmp3770_i2c_get_xfer_count(s);
            stmp3770_i2c_process(s);
        }
        break;
    case I2C_TIMING0:
        stmp3770_i2c_apply_sct(&s->timing0, (uint32_t)value, sct,
                                0x03FF03FF);
        break;
    case I2C_TIMING1:
        stmp3770_i2c_apply_sct(&s->timing1, (uint32_t)value, sct,
                                0x03FF03FF);
        break;
    case I2C_TIMING2:
        stmp3770_i2c_apply_sct(&s->timing2, (uint32_t)value, sct,
                                0x03FF03FF);
        break;
    case I2C_CTRL1:
        stmp3770_i2c_apply_sct(&s->ctrl1, (uint32_t)value, sct,
                                I2C_CTRL1_RW_MASK);
        stmp3770_i2c_update_irq(s);
        break;
    case I2C_DATA:
        if (sct == 0) {
            if (!stmp3770_i2c_enabled(s)) {
                s->data = (uint32_t)value;
            } else {
                unsigned int i;

                for (i = 0; i < size; i++) {
                    stmp3770_i2c_fifo_push(s, (value >> (i * 8)) & 0xFF);
                }
                s->data = (uint32_t)value;
                stmp3770_i2c_process(s);
            }
        }
        break;
    case I2C_DEBUG0:
        stmp3770_i2c_apply_sct(&s->debug0, (uint32_t)value, sct,
                                0x1C000800);
        break;
    case I2C_DEBUG1:
        stmp3770_i2c_apply_sct(&s->debug1, (uint32_t)value, sct,
                                0x0000073F);
        break;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-i2c: write to unimplemented offset "
                      HWADDR_FMT_plx "\n", offset);
        break;
    }
}

static const MemoryRegionOps stmp3770_i2c_ops = {
    .read = stmp3770_i2c_read,
    .write = stmp3770_i2c_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
};

static void stmp3770_i2c_init(Object *obj)
{
    STMP3770I2CState *s = STMP3770_I2C(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &stmp3770_i2c_ops, s,
                          TYPE_STMP3770_I2C, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq_error);
}

static const VMStateDescription vmstate_stmp3770_i2c = {
    .name = "stmp3770-i2c",
    .version_id = 2,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl0, STMP3770I2CState),
        VMSTATE_UINT32(ctrl1, STMP3770I2CState),
        VMSTATE_UINT32(timing0, STMP3770I2CState),
        VMSTATE_UINT32(timing1, STMP3770I2CState),
        VMSTATE_UINT32(timing2, STMP3770I2CState),
        VMSTATE_UINT32(data, STMP3770I2CState),
        VMSTATE_UINT32(debug0, STMP3770I2CState),
        VMSTATE_UINT32(debug1, STMP3770I2CState),
        VMSTATE_UINT8_ARRAY(fifo, STMP3770I2CState, I2C_FIFO_DEPTH),
        VMSTATE_UINT32(fifo_count, STMP3770I2CState),
        VMSTATE_UINT32(fifo_rptr, STMP3770I2CState),
        VMSTATE_UINT32(fifo_wptr, STMP3770I2CState),
        VMSTATE_UINT32(xfer_count, STMP3770I2CState),
        VMSTATE_BOOL(data_engine_busy, STMP3770I2CState),
        VMSTATE_BOOL(dma_wait4endcmd, STMP3770I2CState),
        VMSTATE_END_OF_LIST()
    }
};

static void stmp3770_i2c_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    device_class_set_legacy_reset(dc, stmp3770_i2c_reset);
    dc->vmsd = &vmstate_stmp3770_i2c;
}

static const TypeInfo stmp3770_i2c_type_info = {
    .name          = TYPE_STMP3770_I2C,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770I2CState),
    .instance_init = stmp3770_i2c_init,
    .class_init    = stmp3770_i2c_class_init,
};

static void stmp3770_i2c_dma_completion(STMP3770DMAState *dma, int channel,
                                        void *opaque)
{
    STMP3770I2CState *s = STMP3770_I2C(opaque);

    s->dma_wait4endcmd = true;
    if (!(s->ctrl0 & I2C_CTRL0_RUN)) {
        s->dma_wait4endcmd = false;
        stmp3770_dma_complete_channel_command(dma, channel);
    }
}

static int stmp3770_i2c_dma_handler(STMP3770DMAState *dma, int channel,
                                    STMP3770DMAEvent event, void *buf,
                                    size_t len, void *opaque)
{
    STMP3770I2CState *s = STMP3770_I2C(opaque);
    size_t i;

    if (event == STMP3770_DMA_EVENT_PIO) {
        uint32_t *pio = (uint32_t *)buf;

        if (len >= sizeof(uint32_t)) {
            stmp3770_i2c_write(s, I2C_CTRL0, pio[0], 4);
        }
        return (int)len;
    }

    if (event == STMP3770_DMA_EVENT_DATA_WRITE) {
        const uint8_t *src = (const uint8_t *)buf;

        for (i = 0; i < len; i++) {
            if (!stmp3770_i2c_fifo_push(s, src[i])) {
                break;
            }
            stmp3770_i2c_process(s);
        }
        return (int)i;
    }

    if (event == STMP3770_DMA_EVENT_DATA_READ) {
        uint8_t *dst = (uint8_t *)buf;

        for (i = 0; i < len; i++) {
            uint8_t byte;

            if (s->fifo_count == 0) {
                stmp3770_i2c_process(s);
            }
            if (!stmp3770_i2c_fifo_pop(s, &byte)) {
                break;
            }
            dst[i] = byte;
        }
        return (int)i;
    }

    return 0;
}

void stmp3770_i2c_set_dma(STMP3770I2CState *s, STMP3770DMAState *dma,
                          int channel)
{
    s->dma = dma;
    s->dma_channel = channel;

    if (!dma) {
        return;
    }

    stmp3770_dma_set_channel_handler(dma, channel, stmp3770_i2c_dma_handler, s);
    stmp3770_dma_set_channel_completion_callback(dma, channel,
                                                 stmp3770_i2c_dma_completion,
                                                 s);
}

static void stmp3770_i2c_register_types(void)
{
    type_register_static(&stmp3770_i2c_type_info);
}

type_init(stmp3770_i2c_register_types)
