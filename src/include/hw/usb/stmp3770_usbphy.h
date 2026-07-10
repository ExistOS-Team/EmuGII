/*
 * STMP3770 USB PHY emulation
 *
 * Based on STMP3770 Reference Manual Chapter 17
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef STMP3770_USBPHY_H
#define STMP3770_USBPHY_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_USBPHY "stmp3770-usbphy"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770USBPHYState, STMP3770_USBPHY)

struct STMP3770USBPHYState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;

    uint32_t pwd;
    uint32_t tx;
    uint32_t rx;
    uint32_t ctrl;
    uint32_t status;
    uint32_t debug;
    uint32_t debug1;
};

#endif /* STMP3770_USBPHY_H */
