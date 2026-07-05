/*
 * STMP3770 LCD Interface (LCDIF) emulation
 *
 * Based on STMP3770 Reference Manual Chapter 18
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
 * for more details.
 */

#include "qemu/osdep.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "system/address-spaces.h"
#include "ui/console.h"
#include "ui/surface.h"
#include "ui/pixel_ops.h"
#include "hw/display/framebuffer.h"
#include "hw/display/stmp3770_lcdif.h"

#define LCDIF_VERSION   0x01000000

/* Register offsets */
#define REG_CTRL0       0x000
#define REG_CTRL0_SET   0x004
#define REG_CTRL0_CLR   0x008
#define REG_CTRL0_TOG   0x00C
#define REG_CTRL1       0x010
#define REG_CTRL1_SET   0x014
#define REG_CTRL1_CLR   0x018
#define REG_CTRL1_TOG   0x01C
#define REG_CUR_BUF     0x020
#define REG_NEXT_BUF    0x030
#define REG_TIMING0     0x040
#define REG_TIMING1     0x050
#define REG_TIMING2     0x060
#define REG_TIMING3     0x070
#define REG_VDCTRL0     0x080
#define REG_VDCTRL1     0x090
#define REG_VDCTRL2     0x0A0
#define REG_VDCTRL3     0x0B0
#define REG_STAT        0x0C0
#define REG_VERSION     0x0D0

/* CTRL0 bits */
#define CTRL0_SFTRST    (1U << 31)
#define CTRL0_CLKGATE   (1U << 30)
#define CTRL0_RUN       (1U << 0)
#define CTRL0_DOTCLK_MODE (1U << 1)

/* CTRL1 bits */
#define CTRL1_VSYNC_EDGE_IRQ        (1U << 0)
#define CTRL1_CUR_FRAME_DONE_IRQ    (1U << 1)
#define CTRL1_UNDERFLOW_IRQ         (1U << 2)

/* IRQ bits */
#define IRQ_VSYNC           (1U << 0)
#define IRQ_CUR_FRAME_DONE  (1U << 1)
#define IRQ_UNDERFLOW       (1U << 2)

/* STAT bits */
#define STAT_PRESENT        (1U << 31)
#define STAT_DMA_REQ        (1U << 30)
#define STAT_RXFIFO_FULL    (1U << 29)
#define STAT_RXFIFO_EMPTY   (1U << 28)
#define STAT_TXFIFO_FULL    (1U << 27)
#define STAT_TXFIFO_EMPTY   (1U << 26)
#define STAT_BUSY           (1U << 25)
#define STAT_DVI_CURRENT_FIELD (1U << 24)

#define REFRESH_RATE_HZ     60
#define NS_PER_SEC          1000000000ULL

static inline bool lcdif_enabled(STMP3770LCDIFState *s)
{
    return (s->ctrl0 & (CTRL0_SFTRST | CTRL0_CLKGATE)) == 0 &&
           (s->ctrl0 & CTRL0_RUN) != 0;
}

static void lcdif_update_irq(STMP3770LCDIFState *s)
{
    bool pending = (s->irq & s->irq_en) != 0;
    qemu_set_irq(s->irq_out, pending);
}

static void lcdif_draw_line(void *opaque, uint8_t *dest,
                            const uint8_t *src, int width, int deststep)
{
    STMP3770LCDIFState *s = opaque;
    int i;

    for (i = 0; i < width; i++) {
        uint16_t pixel = ((const uint16_t *)src)[i];
        unsigned int r = ((pixel >> 11) & 0x1F) << 3;
        unsigned int g = ((pixel >> 5) & 0x3F) << 2;
        unsigned int b = (pixel & 0x1F) << 3;
        uint32_t val;

        switch (s->surface_format) {
        case PIXMAN_r5g6b5:
            val = rgb_to_pixel16(r, g, b);
            break;
        case PIXMAN_b5g6r5:
            val = rgb_to_pixel16bgr(r, g, b);
            break;
        case PIXMAN_x8b8g8r8:
        case PIXMAN_a8b8g8r8:
            val = rgb_to_pixel32bgr(r, g, b);
            break;
        case PIXMAN_x8r8g8b8:
        case PIXMAN_a8r8g8b8:
        default:
            val = rgb_to_pixel32(r, g, b);
            break;
        }

        switch (deststep) {
        case 2:
            ((uint16_t *)dest)[i] = (uint16_t)val;
            break;
        case 4:
            ((uint32_t *)dest)[i] = val;
            break;
        default:
            memcpy(dest + i * deststep, &val, deststep);
            break;
        }
    }
}

static void lcdif_update_display(void *opaque)
{
    STMP3770LCDIFState *s = opaque;
    DisplaySurface *surface;
    int src_width;
    int first = -1, last = -1;

    if (!lcdif_enabled(s)) {
        return;
    }

    if (s->width <= 0 || s->height <= 0 || s->cur_buf == 0) {
        return;
    }

    surface = qemu_console_surface(s->con);
    if (!surface || surface_is_placeholder(surface)) {
        return;
    }

    if (surface_width(surface) != s->width ||
        surface_height(surface) != s->height) {
        qemu_console_resize(s->con, s->width, s->height);
        surface = qemu_console_surface(s->con);
        if (!surface) {
            return;
        }
    }

    s->surface_format = surface_format(surface);
    src_width = s->width * 2; /* 16-bit RGB565 framebuffer */

    framebuffer_update_memory_section(&s->fbsection, s->system_memory,
                                      s->cur_buf, s->height, src_width);

    framebuffer_update_display(surface, &s->fbsection,
                               s->width, s->height,
                               src_width,
                               surface_stride(surface),
                               surface_bytes_per_pixel(surface),
                               0, lcdif_draw_line, s,
                               &first, &last);

    if (first >= 0) {
        dpy_gfx_update(s->con, 0, first, s->width, last - first + 1);
    }
}

static void lcdif_refresh(void *opaque)
{
    STMP3770LCDIFState *s = opaque;

    if (lcdif_enabled(s)) {
        lcdif_update_display(s);

        s->irq |= IRQ_VSYNC;
        if (s->irq_en & IRQ_VSYNC) {
            lcdif_update_irq(s);
        }
    }

    timer_mod(s->refresh_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              NS_PER_SEC / REFRESH_RATE_HZ);
}

static void lcdif_apply_sct(uint32_t *reg, uint32_t value, int sct)
{
    switch (sct) {
    case 0:
        *reg = value;
        break;
    case 1:
        *reg |= value;
        break;
    case 2:
        *reg &= ~value;
        break;
    case 3:
        *reg ^= value;
        break;
    }
}

static uint64_t lcdif_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770LCDIFState *s = opaque;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-lcdif: unsupported read size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return 0;
    }

    switch (offset) {
    case REG_CTRL0:
        return s->ctrl0;
    case REG_CTRL1:
        return s->ctrl1;
    case REG_CUR_BUF:
        return s->cur_buf;
    case REG_NEXT_BUF:
        return s->next_buf;
    case REG_TIMING0:
        return s->timing[0];
    case REG_TIMING1:
        return s->timing[1];
    case REG_TIMING2:
        return s->timing[2];
    case REG_TIMING3:
        return s->timing[3];
    case REG_VDCTRL0:
        return s->vdctrl0;
    case REG_VDCTRL1:
        return s->vdctrl1;
    case REG_VDCTRL2:
        return s->vdctrl2;
    case REG_VDCTRL3:
        return s->vdctrl3;
    case REG_STAT:
        /* Report FIFOs as empty and controller as not busy */
        return STAT_PRESENT | STAT_RXFIFO_EMPTY | STAT_TXFIFO_EMPTY;
    case REG_VERSION:
        return LCDIF_VERSION;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-lcdif: read from unimplemented offset "
                      HWADDR_FMT_plx "\n", offset);
        return 0;
    }
}

static void lcdif_write(void *opaque, hwaddr offset,
                        uint64_t value, unsigned size)
{
    STMP3770LCDIFState *s = opaque;
    int sct = (offset >> 2) & 3;
    hwaddr base = offset & ~0xC;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-lcdif: unsupported write size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return;
    }

    switch (base) {
    case REG_CTRL0:
        lcdif_apply_sct(&s->ctrl0, (uint32_t)value, sct);
        /*
         * Hardware ties CLKGATE to SFTRST: asserting reset automatically
         * gates the clock, so firmware polls CLKGATE after setting SFTRST.
         */
        if (s->ctrl0 & CTRL0_SFTRST) {
            s->ctrl0 |= CTRL0_CLKGATE;
        } else {
            s->ctrl0 &= ~CTRL0_CLKGATE;
        }
        break;
    case REG_CTRL1:
        lcdif_apply_sct(&s->ctrl1, (uint32_t)value, sct);
        break;
    case REG_CUR_BUF:
        s->cur_buf = (uint32_t)value;
        break;
    case REG_NEXT_BUF:
        s->next_buf = (uint32_t)value;
        s->cur_buf = s->next_buf;
        break;
    case REG_TIMING0:
        s->timing[0] = (uint32_t)value;
        s->width = (int)(value & 0xFFFF);
        break;
    case REG_TIMING1:
        s->timing[1] = (uint32_t)value;
        s->height = (int)(value & 0xFFFF);
        break;
    case REG_TIMING2:
        s->timing[2] = (uint32_t)value;
        break;
    case REG_TIMING3:
        s->timing[3] = (uint32_t)value;
        break;
    case REG_VDCTRL0:
        s->vdctrl0 = (uint32_t)value;
        break;
    case REG_VDCTRL1:
        s->vdctrl1 = (uint32_t)value;
        break;
    case REG_VDCTRL2:
        s->vdctrl2 = (uint32_t)value;
        break;
    case REG_VDCTRL3:
        s->vdctrl3 = (uint32_t)value;
        break;
    case REG_STAT:
    case REG_VERSION:
        /* Read-only; SET/CLR/TOG aliases are harmless */
        break;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-lcdif: write to unimplemented offset "
                      HWADDR_FMT_plx "\n", offset);
        break;
    }
}

static const MemoryRegionOps lcdif_ops = {
    .read = lcdif_read,
    .write = lcdif_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
};

static void lcdif_reset(DeviceState *dev)
{
    STMP3770LCDIFState *s = STMP3770_LCDIF(dev);

    s->ctrl0 = CTRL0_SFTRST | CTRL0_CLKGATE;
    s->ctrl1 = 0;
    s->cur_buf = 0;
    s->next_buf = 0;
    memset(s->timing, 0, sizeof(s->timing));
    s->vdctrl0 = 0;
    s->vdctrl1 = 0;
    s->vdctrl2 = 0;
    s->vdctrl3 = 0;
    s->irq = 0;
    s->irq_en = 0;
    s->width = 0;
    s->height = 0;
}

static const GraphicHwOps lcdif_gfx_ops = {
    .invalidate = lcdif_update_display,
    .gfx_update = lcdif_update_display,
};

static void lcdif_realize(DeviceState *dev, Error **errp)
{
    STMP3770LCDIFState *s = STMP3770_LCDIF(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    memory_region_init_io(&s->iomem, OBJECT(dev), &lcdif_ops, s,
                          TYPE_STMP3770_LCDIF, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq_out);

    s->system_memory = get_system_memory();
    s->con = graphic_console_init(dev, 0, &lcdif_gfx_ops, s);
    if (!s->con) {
        error_setg(errp, "stmp3770-lcdif: failed to initialize graphic console");
        return;
    }

    s->refresh_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, lcdif_refresh, s);
    timer_mod(s->refresh_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              NS_PER_SEC / REFRESH_RATE_HZ);
}

static const VMStateDescription vmstate_lcdif = {
    .name = "stmp3770-lcdif",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl0, STMP3770LCDIFState),
        VMSTATE_UINT32(ctrl1, STMP3770LCDIFState),
        VMSTATE_UINT32(cur_buf, STMP3770LCDIFState),
        VMSTATE_UINT32(next_buf, STMP3770LCDIFState),
        VMSTATE_UINT32_ARRAY(timing, STMP3770LCDIFState, 4),
        VMSTATE_UINT32(vdctrl0, STMP3770LCDIFState),
        VMSTATE_UINT32(vdctrl1, STMP3770LCDIFState),
        VMSTATE_UINT32(vdctrl2, STMP3770LCDIFState),
        VMSTATE_UINT32(vdctrl3, STMP3770LCDIFState),
        VMSTATE_UINT32(irq, STMP3770LCDIFState),
        VMSTATE_UINT32(irq_en, STMP3770LCDIFState),
        VMSTATE_INT32(width, STMP3770LCDIFState),
        VMSTATE_INT32(height, STMP3770LCDIFState),
        VMSTATE_END_OF_LIST()
    }
};

static void lcdif_init(Object *obj)
{
    STMP3770LCDIFState *s = STMP3770_LCDIF(obj);

    s->width = 0;
    s->height = 0;
    s->surface_format = PIXMAN_x8r8g8b8;
}

static void lcdif_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = lcdif_realize;
    device_class_set_legacy_reset(dc, lcdif_reset);
    dc->vmsd = &vmstate_lcdif;
}

static const TypeInfo lcdif_type_info = {
    .name          = TYPE_STMP3770_LCDIF,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770LCDIFState),
    .instance_init = lcdif_init,
    .class_init    = lcdif_class_init,
};

static void lcdif_register_types(void)
{
    type_register_static(&lcdif_type_info);
}

type_init(lcdif_register_types)
