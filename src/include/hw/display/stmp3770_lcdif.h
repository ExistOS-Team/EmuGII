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

#ifndef STMP3770_LCDIF_H
#define STMP3770_LCDIF_H

#include "hw/sysbus.h"
#include "ui/console.h"
#include "ui/surface.h"
#include "hw/display/framebuffer.h"

#define TYPE_STMP3770_LCDIF "stmp3770-lcdif"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770LCDIFState, STMP3770_LCDIF)

struct STMP3770LCDIFState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    QemuConsole *con;
    QEMUTimer *refresh_timer;
    MemoryRegionSection fbsection;
    MemoryRegion *system_memory;

    uint32_t ctrl0;
    uint32_t ctrl1;
    uint32_t cur_buf;
    uint32_t next_buf;
    uint32_t timing[4];
    uint32_t vdctrl0;
    uint32_t vdctrl1;
    uint32_t vdctrl2;
    uint32_t vdctrl3;
    uint32_t irq;
    uint32_t irq_en;

    qemu_irq irq_out;

    int width;
    int height;
    pixman_format_code_t surface_format;
};

#endif /* STMP3770_LCDIF_H */
