/*
 * STMP3770 On-Chip OTP (OCOTP) Controller
 *
 * Based on STMP3770 Reference Manual Chapter 8
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef STMP3770_OCOTP_H
#define STMP3770_OCOTP_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_OCOTP "stmp3770-ocotp"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770OCOTPState, STMP3770_OCOTP)

#define STMP3770_OCOTP_NUM_CUST    4
#define STMP3770_OCOTP_NUM_CRYPTO  4
#define STMP3770_OCOTP_NUM_ROM     3

struct STMP3770OCOTPState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;

    uint32_t ctrl;
    uint32_t data;
    uint32_t cust[STMP3770_OCOTP_NUM_CUST];
    uint32_t crypto[STMP3770_OCOTP_NUM_CRYPTO];
    uint32_t otp_custcap;
    uint32_t custcap;
    uint32_t otp_lock;
    uint32_t rom[STMP3770_OCOTP_NUM_ROM];
    uint32_t lock;
    uint32_t version;
};

#endif /* STMP3770_OCOTP_H */
