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
#define REG_SET         0x004
#define REG_CLR         0x008
#define REG_TOG         0x00C
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
#define REG_LOCK        0x120
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
#define LOCK_CUST0              (1U << 0)
#define LOCK_CUST1              (1U << 1)
#define LOCK_CUST2              (1U << 2)
#define LOCK_CUST3              (1U << 3)
#define LOCK_CRYPTOKEY          (1U << 4)
#define LOCK_CUSTCAP_SHADOW     (1U << 7)
#define LOCK_CUSTCAP            (1U << 9)

#define BAD_DATA                0xBADABADAU
#define CTRL_RW_MASK            (CTRL_WR_UNLOCK_MASK | CTRL_RELOAD_SHADOWS | \
                                 CTRL_RD_BANK_OPEN | CTRL_ADDR_MASK)

static void stmp3770_ocotp_set_error(STMP3770OCOTPState *s)
{
    s->ctrl |= CTRL_ERROR;
}

static void stmp3770_ocotp_reload_shadows(STMP3770OCOTPState *s)
{
    s->custcap = s->otp_custcap;
    s->lock = s->otp_lock;
}

static void stmp3770_ocotp_maybe_finish_reload(STMP3770OCOTPState *s)
{
    if ((s->ctrl & CTRL_RELOAD_SHADOWS) && !(s->ctrl & CTRL_RD_BANK_OPEN)) {
        stmp3770_ocotp_reload_shadows(s);
        s->ctrl &= ~CTRL_RELOAD_SHADOWS;
    }
}

static bool stmp3770_ocotp_program_locked(STMP3770OCOTPState *s, uint32_t lock_bit)
{
    if (s->lock & lock_bit) {
        stmp3770_ocotp_set_error(s);
        return true;
    }

    return false;
}

static bool stmp3770_ocotp_read_banks_open(STMP3770OCOTPState *s)
{
    return (s->ctrl & CTRL_RD_BANK_OPEN) != 0;
}

static uint64_t stmp3770_ocotp_fail_closed_bank(STMP3770OCOTPState *s)
{
    stmp3770_ocotp_set_error(s);
    return BAD_DATA;
}

static void stmp3770_ocotp_program_word(STMP3770OCOTPState *s, uint32_t addr,
                                        uint32_t value)
{
    switch (addr) {
    case 0x00:
        if (!stmp3770_ocotp_program_locked(s, LOCK_CUST0)) {
            s->cust[0] |= value;
        }
        return;
    case 0x01:
        if (!stmp3770_ocotp_program_locked(s, LOCK_CUST1)) {
            s->cust[1] |= value;
        }
        return;
    case 0x02:
        if (!stmp3770_ocotp_program_locked(s, LOCK_CUST2)) {
            s->cust[2] |= value;
        }
        return;
    case 0x03:
        if (!stmp3770_ocotp_program_locked(s, LOCK_CUST3)) {
            s->cust[3] |= value;
        }
        return;
    case 0x04:
    case 0x05:
    case 0x06:
    case 0x07:
        if (!stmp3770_ocotp_program_locked(s, LOCK_CRYPTOKEY)) {
            s->crypto[addr - 0x04] |= value;
        }
        return;
    case 0x0f:
        if (!stmp3770_ocotp_program_locked(s, LOCK_CUSTCAP)) {
            s->otp_custcap |= value;
        }
        return;
    case 0x10:
        s->otp_lock |= value;
        return;
    case 0x18:
    case 0x19:
    case 0x1a:
        s->rom[addr - 0x18] |= value;
        return;
    default:
        stmp3770_ocotp_set_error(s);
        return;
    }
}

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

    case REG_LOCK:
        return s->lock;

    case REG_VERSION:
        return s->version;

    default:
        break;
    }

    idx = cust_idx_from_offset(offset);
    if (idx >= 0) {
        if (!stmp3770_ocotp_read_banks_open(s)) {
            return stmp3770_ocotp_fail_closed_bank(s);
        }
        return s->cust[idx];
    }

    idx = crypto_idx_from_offset(offset);
    if (idx >= 0) {
        if (!stmp3770_ocotp_read_banks_open(s)) {
            return stmp3770_ocotp_fail_closed_bank(s);
        }
        if (s->lock & LOCK_CRYPTOKEY) {
            stmp3770_ocotp_set_error(s);
            return BAD_DATA;
        }
        return s->crypto[idx];
    }

    idx = rom_idx_from_offset(offset);
    if (idx >= 0) {
        if (!stmp3770_ocotp_read_banks_open(s)) {
            return stmp3770_ocotp_fail_closed_bank(s);
        }
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
    hwaddr reg = offset & ~0x0f;
    hwaddr sct = offset & 0x0f;
    uint32_t writable;
    bool reload_requested = false;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-ocotp: unsupported write size %u at "
                      HWADDR_FMT_plx "\n", size, offset);
        return;
    }

    switch (reg) {
    case REG_CTRL:
        writable = s->ctrl & ~(CTRL_RW_MASK);

        switch (sct) {
        case 0x0:
            writable &= ~CTRL_RW_MASK;
            writable |= (uint32_t)value & (CTRL_RELOAD_SHADOWS |
                                           CTRL_RD_BANK_OPEN |
                                           CTRL_ADDR_MASK);
            if (((uint32_t)value & CTRL_WR_UNLOCK_MASK) == CTRL_WR_UNLOCK_VALUE) {
                writable |= CTRL_WR_UNLOCK_VALUE;
            }
            break;
        case REG_SET:
            writable |= (uint32_t)value & (CTRL_RELOAD_SHADOWS |
                                           CTRL_RD_BANK_OPEN |
                                           CTRL_ADDR_MASK);
            if (((uint32_t)value & CTRL_WR_UNLOCK_MASK) == CTRL_WR_UNLOCK_VALUE) {
                writable |= CTRL_WR_UNLOCK_VALUE;
            }
            break;
        case REG_CLR:
            writable &= ~((uint32_t)value & (CTRL_RELOAD_SHADOWS |
                                             CTRL_RD_BANK_OPEN |
                                             CTRL_ADDR_MASK |
                                             CTRL_WR_UNLOCK_MASK));
            if ((uint32_t)value & CTRL_ERROR) {
                s->ctrl &= ~CTRL_ERROR;
            }
            break;
        case REG_TOG:
            writable ^= (uint32_t)value & (CTRL_RELOAD_SHADOWS |
                                           CTRL_RD_BANK_OPEN |
                                           CTRL_ADDR_MASK);
            break;
        default:
            qemu_log_mask(LOG_GUEST_ERROR,
                          "stmp3770-ocotp: write to invalid CTRL alias "
                          HWADDR_FMT_plx "\n", offset);
            return;
        }

        s->ctrl = (s->ctrl & ~(CTRL_RW_MASK | CTRL_ERROR)) |
                  (writable & CTRL_RW_MASK) |
                  (s->ctrl & CTRL_ERROR);
        reload_requested = (s->ctrl & CTRL_RELOAD_SHADOWS) != 0;
        if (reload_requested) {
            stmp3770_ocotp_maybe_finish_reload(s);
        }
        return;

    case REG_DATA:
        if (sct != 0x0) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "stmp3770-ocotp: DATA has no SCT alias "
                          HWADDR_FMT_plx "\n", offset);
            return;
        }
        s->data = (uint32_t)value;
        if ((s->ctrl & CTRL_ERROR) ||
            ((s->ctrl & CTRL_WR_UNLOCK_MASK) != CTRL_WR_UNLOCK_VALUE)) {
            return;
        }
        stmp3770_ocotp_program_word(s, s->ctrl & CTRL_ADDR_MASK, s->data);
        if (!(s->ctrl & CTRL_ERROR)) {
            s->ctrl &= ~CTRL_WR_UNLOCK_MASK;
        }
        return;

    case REG_CUSTCAP:
        if (sct != 0x0) {
            qemu_log_mask(LOG_GUEST_ERROR,
                          "stmp3770-ocotp: CUSTCAP has no SCT alias "
                          HWADDR_FMT_plx "\n", offset);
            return;
        }
        if (s->lock & LOCK_CUSTCAP_SHADOW) {
            stmp3770_ocotp_set_error(s);
            return;
        }
        s->custcap = (uint32_t)value;
        return;

    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-ocotp: write to read-only/unimplemented offset "
                      HWADDR_FMT_plx "\n", offset);
        return;
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
    s->otp_custcap = 0;
    s->custcap = 0;
    s->otp_lock = 0;
    memset(s->rom, 0, sizeof(s->rom));
    s->lock = 0;
    s->version = 0x01010000; /* HW_OCOTP_VERSION fields: MAJOR=1, MINOR=1, STEP=0 */
    stmp3770_ocotp_reload_shadows(s);
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
    .version_id = 2,
    .minimum_version_id = 2,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl, STMP3770OCOTPState),
        VMSTATE_UINT32(data, STMP3770OCOTPState),
        VMSTATE_UINT32_ARRAY(cust, STMP3770OCOTPState, STMP3770_OCOTP_NUM_CUST),
        VMSTATE_UINT32_ARRAY(crypto, STMP3770OCOTPState, STMP3770_OCOTP_NUM_CRYPTO),
        VMSTATE_UINT32(otp_custcap, STMP3770OCOTPState),
        VMSTATE_UINT32(custcap, STMP3770OCOTPState),
        VMSTATE_UINT32(otp_lock, STMP3770OCOTPState),
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
