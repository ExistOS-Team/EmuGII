/*
 * STMP3770 On-Chip OTP (OCOTP) Controller
 *
 * Based on STMP3770 Reference Manual Chapter 8
 *
 * Features:
 * - Memory-mapped OTP shadow registers
 * - CTRL/DATA and LOCK/CUSTCAP handling
 * - Customer, crypto key and ROM-use words
 * - Version register
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#include "qemu/osdep.h"
#include "hw/sysbus.h"
#include "hw/misc/stmp3770_ocotp.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"

/* Register offsets */
#define REG_CTRL        0x000
#define REG_DATA        0x010
#define REG_CUST0       0x020
#define REG_CUST1       0x030
#define REG_CUST2       0x040
#define REG_CUST3       0x050
#define REG_CRYPTO0     0x060
#define REG_CRYPTO1     0x070
#define REG_CRYPTO2     0x080
#define REG_CRYPTO3     0x090
#define REG_CUSTCAP     0x110
#define REG_ROM0        0x1A0
#define REG_ROM1        0x1B0
#define REG_ROM2        0x1C0
#define REG_VERSION     0x220

/* CTRL bits */
#define CTRL_WR_UNLOCK_MASK     0xFFFF0000
#define CTRL_WR_UNLOCK_VALUE    0x3E770000
#define CTRL_RELOAD_SHADOWS     (1U << 13)
#define CTRL_RD_BANK_OPEN       (1U << 12)
#define CTRL_ERROR              (1U << 9)
#define CTRL_BUSY               (1U << 8)
#define CTRL_ADDR_MASK          0x1F

/* LOCK bits */
#define LOCK_CRYPTOKEY          (1U << 4)

#define BAD_DATA                0xBADABADAU

static int cust_idx_from_offset(hwaddr offset)
{
    if (offset >= REG_CUST0 && offset < REG_CUST0 + (STMP3770_OCOTP_NUM_CUST * 0x10)) {
        return (offset - REG_CUST0) >> 4;
    }
    return -1;
}

static int crypto_idx_from_offset(hwaddr offset)
{
    if (offset >= REG_CRYPTO0 &&
        offset < REG_CRYPTO0 + (STMP3770_OCOTP_NUM_CRYPTO * 0x10)) {
        return (offset - REG_CRYPTO0) >> 4;
    }
    return -1;
}

static int rom_idx_from_offset(hwaddr offset)
{
    if (offset >= REG_ROM0 && offset < REG_ROM0 + (STMP3770_OCOTP_NUM_ROM * 0x10)) {
        return (offset - REG_ROM0) >> 4;
    }
    return -1;
}

static uint64_t stmp3770_ocotp_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770OCOTPState *s = STMP3770_OCOTP(opaque);
    int idx;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-ocotp: unsupported read size %u at "
                      HWADDR_FMT_plx "\n", size, offset);
        return 0;
    }

    switch (offset) {
    case REG_CTRL:
        return s->ctrl & ~(CTRL_BUSY);

    case REG_DATA:
        return s->data;

    case REG_CUSTCAP:
        return s->custcap;

    case REG_VERSION:
        return s->version;

    default:
        break;
    }

    idx = cust_idx_from_offset(offset);
    if (idx >= 0) {
        return s->cust[idx];
    }

    idx = crypto_idx_from_offset(offset);
    if (idx >= 0) {
        if (s->lock & LOCK_CRYPTOKEY) {
            return BAD_DATA;
        }
        return s->crypto[idx];
    }

    idx = rom_idx_from_offset(offset);
    if (idx >= 0) {
        return s->rom[idx];
    }

    qemu_log_mask(LOG_GUEST_ERROR,
                  "stmp3770-ocotp: read from unimplemented offset "
                  HWADDR_FMT_plx "\n", offset);
    return 0;
}

static void stmp3770_ocotp_write(void *opaque, hwaddr offset,
                                 uint64_t value, unsigned size)
{
    STMP3770OCOTPState *s = STMP3770_OCOTP(opaque);

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-ocotp: unsupported write size %u at "
                      HWADDR_FMT_plx "\n", size, offset);
        return;
    }

    switch (offset) {
    case REG_CTRL:
        s->ctrl = (value & ~CTRL_WR_UNLOCK_MASK) |
                    ((value & CTRL_WR_UNLOCK_MASK) == CTRL_WR_UNLOCK_VALUE
                     ? CTRL_WR_UNLOCK_VALUE : 0);
        if (value & CTRL_RELOAD_SHADOWS) {
            /* Shadow reload is instantaneous in this model */
            s->ctrl &= ~CTRL_RELOAD_SHADOWS;
        }
        if (value & CTRL_RD_BANK_OPEN) {
            s->ctrl |= CTRL_RD_BANK_OPEN;
        } else {
            s->ctrl &= ~CTRL_RD_BANK_OPEN;
        }
        if (value & CTRL_ERROR) {
            /* Writing 1 clears the error flag */
            s->ctrl &= ~CTRL_ERROR;
        }
        break;

    case REG_DATA:
        s->data = value;
        break;

    case REG_CUSTCAP:
        s->custcap = value;
        break;

    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-ocotp: write to read-only/unimplemented offset "
                      HWADDR_FMT_plx "\n", offset);
        break;
    }
}

static const MemoryRegionOps stmp3770_ocotp_ops = {
    .read = stmp3770_ocotp_read,
    .write = stmp3770_ocotp_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
};

static void stmp3770_ocotp_reset(DeviceState *dev)
{
    STMP3770OCOTPState *s = STMP3770_OCOTP(dev);

    s->ctrl = 0;
    s->data = 0;
    memset(s->cust, 0, sizeof(s->cust));
    memset(s->crypto, 0, sizeof(s->crypto));
    s->custcap = 0;
    memset(s->rom, 0, sizeof(s->rom));
    s->lock = 0;
    s->version = 0x01010000; /* OCOTP Block v1.1 */
}

static void stmp3770_ocotp_init(Object *obj)
{
    STMP3770OCOTPState *s = STMP3770_OCOTP(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &stmp3770_ocotp_ops, s,
        TYPE_STMP3770_OCOTP, 0x300);
    sysbus_init_mmio(sbd, &s->iomem);
}

static const VMStateDescription vmstate_stmp3770_ocotp = {
    .name = TYPE_STMP3770_OCOTP,
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl, STMP3770OCOTPState),
        VMSTATE_UINT32(data, STMP3770OCOTPState),
        VMSTATE_UINT32_ARRAY(cust, STMP3770OCOTPState, STMP3770_OCOTP_NUM_CUST),
        VMSTATE_UINT32_ARRAY(crypto, STMP3770OCOTPState, STMP3770_OCOTP_NUM_CRYPTO),
        VMSTATE_UINT32(custcap, STMP3770OCOTPState),
        VMSTATE_UINT32_ARRAY(rom, STMP3770OCOTPState, STMP3770_OCOTP_NUM_ROM),
        VMSTATE_UINT32(lock, STMP3770OCOTPState),
        VMSTATE_UINT32(version, STMP3770OCOTPState),
        VMSTATE_END_OF_LIST()
    }
};

static void stmp3770_ocotp_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    device_class_set_legacy_reset(dc, stmp3770_ocotp_reset);
    dc->vmsd = &vmstate_stmp3770_ocotp;
}

static const TypeInfo stmp3770_ocotp_type_info = {
    .name          = TYPE_STMP3770_OCOTP,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770OCOTPState),
    .instance_init = stmp3770_ocotp_init,
    .class_init    = stmp3770_ocotp_class_init,
};

static void stmp3770_ocotp_register_types(void)
{
    type_register_static(&stmp3770_ocotp_type_info);
}

type_init(stmp3770_ocotp_register_types)
