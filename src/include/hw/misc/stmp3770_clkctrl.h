/*
 * STMP3770 Clock Control (CLKCTRL) header
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef HW_MISC_STMP3770_CLKCTRL_H
#define HW_MISC_STMP3770_CLKCTRL_H

#include "hw/sysbus.h"
#include "qom/object.h"

#define TYPE_STMP3770_CLKCTRL "stmp3770-clkctrl"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770CLKCTRLState, STMP3770_CLKCTRL)

#endif /* HW_MISC_STMP3770_CLKCTRL_H */
