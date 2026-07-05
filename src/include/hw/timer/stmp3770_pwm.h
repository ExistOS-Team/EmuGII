/*
 * STMP3770 PWM controller emulation
 *
 * Based on STMP3770 Reference Manual Chapter 19
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

#ifndef STMP3770_PWM_H
#define STMP3770_PWM_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_PWM "stmp3770-pwm"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770PWMState, STMP3770_PWM)

#define STMP3770_PWM_NUM_CHANNELS 5

struct STMP3770PWMState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;

    uint32_t ctrl0;
    uint32_t period[STMP3770_PWM_NUM_CHANNELS];
    uint32_t duty[STMP3770_PWM_NUM_CHANNELS];
    uint32_t active[STMP3770_PWM_NUM_CHANNELS];
};

#endif /* STMP3770_PWM_H */
