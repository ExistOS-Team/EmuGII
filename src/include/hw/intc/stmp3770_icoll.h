/*
 * STMP3770 Interrupt Collector (ICOLL) header
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef HW_INTC_STMP3770_ICOLL_H
#define HW_INTC_STMP3770_ICOLL_H

#include "hw/sysbus.h"
#include "qom/object.h"

#define TYPE_STMP3770_ICOLL "stmp3770-icoll"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770ICOLLState, STMP3770_ICOLL)

void stmp3770_icoll_set_hclk_rate(void *opaque, uint32_t hclk_hz);

#endif /* HW_INTC_STMP3770_ICOLL_H */
