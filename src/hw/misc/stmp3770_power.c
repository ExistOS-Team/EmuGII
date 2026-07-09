/*
 * STMP3770 Power Supply (POWER)
 *
 * Based on STMP3770 Reference Manual Chapter 29
 *
 * Features:
 * - Power control / 5V control / minimum power registers
 * - Charge control / regulator controls (VDDD/VDDA/VDDIO)
 * - DC-DC function, limits, loop control
 * - Status register (VBUSVALID, LINREG_OK, DC_OK, etc.)
 * - Speed, battery monitor, reset, debug, special, version
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

#include "qemu/osdep.h"
#include "hw/sysbus.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "hw/misc/stmp3770_power.h"

/* Register offsets (from Chapter 29.3 Register Map) */
#define REG_CTRL                0x000
#define REG_5VCTRL              0x010
#define REG_MINPWR              0x020
#define REG_CHARGE              0x030
#define REG_VDDDCTRL            0x040
#define REG_VDDACTRL            0x050
#define REG_VDDIOCTRL           0x060
#define REG_DCFUNCV             0x070
#define REG_MISC                0x080
#define REG_DCLIMITS            0x090
#define REG_LOOPCTRL            0x0A0
#define REG_STS                 0x0B0
#define REG_SPEED               0x0C0
#define REG_BATTMONITOR         0x0D0
#define REG_RESET               0x0E0
#define REG_DEBUG               0x0F0
#define REG_SPECIAL             0x100
#define REG_VERSION             0x110

#define REG_SPACING             0x10
#define REG_SET                 0x4
#define REG_CLR                 0x8
#define REG_TOG                 0xC

/* Number of 16-byte register slots we emulate (0x000..0x110 inclusive) */
#define NUM_SLOTS               18

/* CTRL bits */
#define CTRL_CLKGATE                (1U << 30)
#define CTRL_POLARITY_LINREG_OK     (1U << 18)
#define CTRL_POLARITY_VBUSVALID     (1U << 5)
#define CTRL_POLARITY_VDD5V_GT_VDDIO (1U << 2)

/* REG_RESET write-unlock protocol */
#define RESET_UNLOCK_MASK       0xFFFF0000U
#define RESET_UNLOCK_VALUE      0x3E770000U
#define RESET_WRITABLE_MASK     0x00000003U

/* Register reset values per Reference Chapter 29 */
#define CTRL_RESET              (CTRL_CLKGATE | CTRL_POLARITY_LINREG_OK | \
                                 CTRL_POLARITY_VBUSVALID | \
                                 CTRL_POLARITY_VDD5V_GT_VDDIO)
#define V5CTRL_RESET            (1U << 8)
#define CHARGE_RESET            (1U << 16)
#define VDDDCTRL_RESET          0x00310710U
#define VDDACTRL_RESET          0x0000170AU
#define VDDIOCTRL_RESET         0x0000170CU
#define DCLIMITS_RESET          0x00040C5FU
#define LOOPCTRL_RESET          0x00000021U
#define BATTMONITOR_RESET       (1U << 5)
#define STS_RESET               (1U << 31)
#define SPEED_RESET             0x00000000U
#define VERSION_VALUE           0x02000000U

#define TYPE_STMP3770_POWER "stmp3770-power"

struct STMP3770PowerState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;

    uint32_t regs[NUM_SLOTS];
};

static inline int slot_from_offset(hwaddr offset)
{
    return (int)(offset / REG_SPACING);
}

static uint64_t stmp3770_power_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770PowerState *s = STMP3770_POWER(opaque);
    int slot;

    if (offset >= NUM_SLOTS * REG_SPACING) {
        qemu_log_mask(LOG_GUEST_ERROR,
                     "%s: bad offset 0x%" HWADDR_PRIx "\n", __func__, offset);
        return 0;
    }

    /* SET/CLR/TOG variants read as the base register */
    slot = slot_from_offset(offset & ~0xFULL);

    switch (offset & ~0xFULL) {
    case REG_STS:
        return s->regs[slot];

    case REG_VERSION:
        return VERSION_VALUE;

    default:
        return s->regs[slot];
    }
}

static void stmp3770_power_write(void *opaque, hwaddr offset,
                                  uint64_t value, unsigned size)
{
    STMP3770PowerState *s = STMP3770_POWER(opaque);
    int slot;
    uint32_t val = value;
    uint32_t *target;
    bool is_set = (offset & 0xF) == REG_SET;
    bool is_clr = (offset & 0xF) == REG_CLR;
    bool is_tog = (offset & 0xF) == REG_TOG;

    if (offset >= NUM_SLOTS * REG_SPACING) {
        qemu_log_mask(LOG_GUEST_ERROR,
                     "%s: bad offset 0x%" HWADDR_PRIx "\n", __func__, offset);
        return;
    }

    slot = slot_from_offset(offset & ~0xFULL);
    target = &s->regs[slot];

    switch (offset & ~0xFULL) {
    case REG_VERSION:
        /* Read-only */
        return;

    case REG_STS:
        /* Allow guest to clear sticky status bits */
        if (is_clr) {
            *target &= ~val;
        } else if (is_set) {
            *target |= val;
        } else if (is_tog) {
            *target ^= val;
        } else {
            *target = val;
        }
        return;

    case REG_RESET:
        if (!is_set && !is_clr && !is_tog) {
            if ((val & RESET_UNLOCK_MASK) == RESET_UNLOCK_VALUE) {
                *target = val & RESET_WRITABLE_MASK;
            }
        } else if ((val & RESET_UNLOCK_MASK) == RESET_UNLOCK_VALUE) {
            uint32_t bits = val & RESET_WRITABLE_MASK;
            if (is_set) {
                *target |= bits;
            } else if (is_clr) {
                *target &= ~bits;
            }
        }
        return;

    default:
        break;
    }

    if (is_set) {
        *target |= val;
    } else if (is_clr) {
        *target &= ~val;
    } else if (is_tog) {
        *target ^= val;
    } else {
        *target = val;
    }
}

static const MemoryRegionOps stmp3770_power_ops = {
    .read = stmp3770_power_read,
    .write = stmp3770_power_write,
    .endianness = DEVICE_NATIVE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

static void stmp3770_power_reset(DeviceState *dev)
{
    STMP3770PowerState *s = STMP3770_POWER(dev);

    memset(s->regs, 0, sizeof(s->regs));

    s->regs[slot_from_offset(REG_CTRL)] = CTRL_RESET;
    s->regs[slot_from_offset(REG_5VCTRL)] = V5CTRL_RESET;
    s->regs[slot_from_offset(REG_CHARGE)] = CHARGE_RESET;
    s->regs[slot_from_offset(REG_VDDDCTRL)] = VDDDCTRL_RESET;
    s->regs[slot_from_offset(REG_VDDACTRL)] = VDDACTRL_RESET;
    s->regs[slot_from_offset(REG_VDDIOCTRL)] = VDDIOCTRL_RESET;
    s->regs[slot_from_offset(REG_DCLIMITS)] = DCLIMITS_RESET;
    s->regs[slot_from_offset(REG_LOOPCTRL)] = LOOPCTRL_RESET;
    s->regs[slot_from_offset(REG_STS)] = STS_RESET;
    s->regs[slot_from_offset(REG_SPEED)] = SPEED_RESET;
    s->regs[slot_from_offset(REG_BATTMONITOR)] = BATTMONITOR_RESET;
}

static void stmp3770_power_init(Object *obj)
{
    STMP3770PowerState *s = STMP3770_POWER(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &stmp3770_power_ops, s,
                          TYPE_STMP3770_POWER, 0x200);
    sysbus_init_mmio(sbd, &s->iomem);
}

static const VMStateDescription vmstate_stmp3770_power = {
    .name = TYPE_STMP3770_POWER,
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32_ARRAY(regs, STMP3770PowerState, NUM_SLOTS),
        VMSTATE_END_OF_LIST()
    }
};

static void stmp3770_power_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, stmp3770_power_reset);
    dc->vmsd = &vmstate_stmp3770_power;
}

static const TypeInfo stmp3770_power_info = {
    .name          = TYPE_STMP3770_POWER,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770PowerState),
    .instance_init = stmp3770_power_init,
    .class_init    = stmp3770_power_class_init,
};

static void stmp3770_power_register_types(void)
{
    type_register_static(&stmp3770_power_info);
}

type_init(stmp3770_power_register_types)
