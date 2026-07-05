/*
 * STMP3770 SSP (Synchronous Serial Port) controller
 *
 * Based on STMP3770 Reference Manual Chapter 16
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef STMP3770_SSP_H
#define STMP3770_SSP_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_SSP "stmp3770-ssp"

OBJECT_DECLARE_SIMPLE_TYPE(STMP3770SSPState, STMP3770_SSP)

/* Register offsets */
#define SSP_CTRL0      0x000
#define SSP_CTRL1      0x010
#define SSP_CMD0       0x020
#define SSP_CMD1       0x030
#define SSP_COMPREF    0x040
#define SSP_COMPMASK   0x050
#define SSP_TIMING     0x060
#define SSP_DATA       0x070
#define SSP_SDRESP0    0x080
#define SSP_SDRESP1    0x090
#define SSP_SDRESP2    0x0A0
#define SSP_SDRESP3    0x0B0
#define SSP_STATUS     0x0C0
#define SSP_DEBUG      0x0D0
#define SSP_VERSION    0x0E0
#define SSP_DLL_CTRL   0x100
#define SSP_DLL_STS    0x110

/* CTRL0 bits */
#define SSP_CTRL0_SFTRST   (1U << 31)
#define SSP_CTRL0_CLKGATE  (1U << 30)
#define SSP_CTRL0_RUN      (1U << 29)

/* STATUS bits */
#define SSP_STATUS_FIFO_EMPTY  (1U << 0)
#define SSP_STATUS_FIFO_FULL   (1U << 1)
#define SSP_STATUS_BUSY        (1U << 2)
#define SSP_STATUS_DATA_CRC_ERR (1U << 3)
#define SSP_STATUS_RESP_ERR    (1U << 4)
#define SSP_STATUS_RESP_TIMEOUT (1U << 5)

/* VERSION value */
#define SSP_VERSION_VALUE 0x01000000

struct STMP3770SSPState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq_dma;
    qemu_irq irq_error;

    uint32_t ctrl0;
    uint32_t ctrl1;
    uint32_t cmd0;
    uint32_t cmd1;
    uint32_t compref;
    uint32_t compmask;
    uint32_t timing;
    uint32_t data;
    uint32_t sdresp[4];
    uint32_t status;
    uint32_t debug;
    uint32_t dll_ctrl;
    uint32_t dll_sts;
};

#endif /* STMP3770_SSP_H */
