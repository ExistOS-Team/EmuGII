/*
 * STMP3770 Power Supply (POWER)
 *
 * Based on STMP3770 Reference Manual Chapter 9
 *
 * Features:
 * - Power control / 5V control / minimum power registers
 * - Charge control / regulator controls (VDDD/VDDA/VDDIO)
 * - DC-DC function, limits, loop control
 * - Status register (VBUSVALID, LINREG_OK, DC_OK, etc.)
 * - Speed, battery monitor, reset, debug, version
 * - SET/CLR/TOG register variants on applicable registers
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

#ifndef HW_MISC_STMP3770_POWER_H
#define HW_MISC_STMP3770_POWER_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_POWER "stmp3770-power"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770PowerState, STMP3770_POWER)

#endif /* HW_MISC_STMP3770_POWER_H */
