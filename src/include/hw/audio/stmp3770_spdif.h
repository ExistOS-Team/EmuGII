/*
 * STMP3770 SPDIF Transmitter
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_AUDIO_STMP3770_SPDIF_H
#define HW_AUDIO_STMP3770_SPDIF_H

#include "hw/sysbus.h"
#include "hw/dma/stmp3770_dma.h"

#define TYPE_STMP3770_SPDIF "stmp3770-spdif"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770SPDIFState, STMP3770_SPDIF)

void stmp3770_spdif_set_dma(STMP3770SPDIFState *s, STMP3770DMAState *dma,
                            int channel);

#endif /* HW_AUDIO_STMP3770_SPDIF_H */
