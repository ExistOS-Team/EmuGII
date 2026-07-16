/*
 * STMP3770 Data Co-Processor (DCP)
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_MISC_STMP3770_DCP_H
#define HW_MISC_STMP3770_DCP_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_DCP "stmp3770-dcp"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770DCPState, STMP3770_DCP)

typedef struct STMP3770OCOTPState STMP3770OCOTPState;

void stmp3770_dcp_set_ocotp(STMP3770DCPState *s, STMP3770OCOTPState *ocotp);

#endif /* HW_MISC_STMP3770_DCP_H */
