/*
 * STMP3770 Digital Radio Interface (DRI)
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_MISC_STMP3770_DRI_H
#define HW_MISC_STMP3770_DRI_H

#include "hw/sysbus.h"
#include "hw/dma/stmp3770_dma.h"

#define TYPE_STMP3770_DRI "stmp3770-dri"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770DRIState, STMP3770_DRI)

void stmp3770_dri_set_dma(STMP3770DRIState *s, STMP3770DMAState *dma,
                          int channel);

#endif /* HW_MISC_STMP3770_DRI_H */
