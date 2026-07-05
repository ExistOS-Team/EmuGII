/*
 * STMP3770 I2C controller
 *
 * Based on STMP3770 Reference Manual Chapter 24
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef STMP3770_I2C_H
#define STMP3770_I2C_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_I2C "stmp3770-i2c"

OBJECT_DECLARE_SIMPLE_TYPE(STMP3770I2CState, STMP3770_I2C)

/* Register offsets */
#define I2C_CTRL0     0x000
#define I2C_CTRL1     0x010
#define I2C_TIMING0   0x020
#define I2C_TIMING1   0x030
#define I2C_TIMING2   0x040
#define I2C_DATA      0x050
#define I2C_DEBUG0    0x060
#define I2C_DEBUG1    0x070
#define I2C_VERSION   0x080

/* CTRL0 bits */
#define I2C_CTRL0_SFTRST            (1U << 31)
#define I2C_CTRL0_CLKGATE           (1U << 30)
#define I2C_CTRL0_RUN               (1U << 29)
#define I2C_CTRL0_SEND_NAK_ON_LAST  (1U << 21)
#define I2C_CTRL0_RETAIN_CLOCK      (1U << 20)
#define I2C_CTRL0_POST_SEND_STOP    (1U << 19)
#define I2C_CTRL0_PRE_SEND_START    (1U << 18)
#define I2C_CTRL0_MASTER_MODE       (1U << 17)
#define I2C_CTRL0_DIRECTION         (1U << 16)
#define I2C_CTRL0_XFER_COUNT_MASK   0xFFFF

/* CTRL1 bits (status lower 16, enable upper 16) */
#define I2C_CTRL1_NO_SLAVE_ACK_IRQ          (1U << 0)
#define I2C_CTRL1_OVERSIZE_XFER_TERM_IRQ    (1U << 1)
#define I2C_CTRL1_ARBITRATE_LOST_IRQ        (1U << 2)
#define I2C_CTRL1_BUS_FREE_IRQ              (1U << 3)
#define I2C_CTRL1_DATA_ENGINE_CMPLT_IRQ     (1U << 4)
#define I2C_CTRL1_DMA_ERROR_IRQ             (1U << 16)

/* VERSION value */
#define I2C_VERSION_VALUE 0x01000000

struct STMP3770I2CState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq_dma;
    qemu_irq irq_error;

    uint32_t ctrl0;
    uint32_t ctrl1;
    uint32_t timing0;
    uint32_t timing1;
    uint32_t timing2;
    uint32_t data;
    uint32_t debug0;
    uint32_t debug1;
};

#endif /* STMP3770_I2C_H */
