/*
 * STMP3770 PWM controller emulation
 *
 * Based on STMP3770 Reference Manual Chapter 19
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
#include "hw/irq.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "hw/timer/stmp3770_pwm.h"

#define PWM_VERSION     0x01000000

#define REG_CTRL0       0x000
#define REG_CTRL0_SET   0x004
#define REG_CTRL0_CLR   0x008
#define REG_CTRL0_TOG   0x00C
#define REG_PERIOD(ch)  (0x100 + ((ch) * 0x10))
#define REG_DUTY(ch)    (0x180 + ((ch) * 0x10))
#define REG_ACTIVE(ch)  (0x200 + ((ch) * 0x10))
#define REG_VERSION     0x1F0

#define CTRL0_SFTRST    (1U << 31)
#define CTRL0_CLKGATE   (1U << 30)
#define CTRL0_PWM_ENABLE(chan) (1U << (chan))

static void pwm_apply_sct(uint32_t *reg, uint32_t value, int sct)
{
    switch (sct) {
    case 0:
        *reg = value;
        break;
    case 1:
        *reg |= value;
        break;
    case 2:
        *reg &= ~value;
        break;
    case 3:
        *reg ^= value;
        break;
    }
}

static uint64_t pwm_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770PWMState *s = opaque;
    int ch;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-pwm: unsupported read size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return 0;
    }

    if (offset == REG_CTRL0) {
        return s->ctrl0;
    }
    if (offset == REG_VERSION) {
        return PWM_VERSION;
    }

    for (ch = 0; ch < STMP3770_PWM_NUM_CHANNELS; ch++) {
        if (offset == REG_PERIOD(ch)) {
            return s->period[ch];
        }
        if (offset == REG_DUTY(ch)) {
            return s->duty[ch];
        }
        if (offset == REG_ACTIVE(ch)) {
            return s->active[ch];
        }
    }

    qemu_log_mask(LOG_GUEST_ERROR,
                  "stmp3770-pwm: read from unimplemented offset "
                  HWADDR_FMT_plx "\n", offset);
    return 0;
}

static void pwm_write(void *opaque, hwaddr offset,
                      uint64_t value, unsigned size)
{
    STMP3770PWMState *s = opaque;
    int sct = (offset >> 2) & 3;
    int ch;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-pwm: unsupported write size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return;
    }

    if ((offset & ~0xC) == REG_CTRL0) {
        pwm_apply_sct(&s->ctrl0, (uint32_t)value, sct);
        return;
    }

    for (ch = 0; ch < STMP3770_PWM_NUM_CHANNELS; ch++) {
        if (offset == REG_PERIOD(ch)) {
            s->period[ch] = (uint32_t)value;
            return;
        }
        if (offset == REG_DUTY(ch)) {
            s->duty[ch] = (uint32_t)value;
            return;
        }
        if (offset == REG_ACTIVE(ch)) {
            s->active[ch] = (uint32_t)value;
            return;
        }
    }

    qemu_log_mask(LOG_GUEST_ERROR,
                  "stmp3770-pwm: write to unimplemented offset "
                  HWADDR_FMT_plx "\n", offset);
}

static const MemoryRegionOps pwm_ops = {
    .read = pwm_read,
    .write = pwm_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
};

static void pwm_reset(DeviceState *dev)
{
    STMP3770PWMState *s = STMP3770_PWM(dev);

    s->ctrl0 = CTRL0_SFTRST | CTRL0_CLKGATE;
    memset(s->period, 0, sizeof(s->period));
    memset(s->duty, 0, sizeof(s->duty));
    memset(s->active, 0, sizeof(s->active));
}

static void pwm_realize(DeviceState *dev, Error **errp)
{
    STMP3770PWMState *s = STMP3770_PWM(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    memory_region_init_io(&s->iomem, OBJECT(dev), &pwm_ops, s,
                          TYPE_STMP3770_PWM, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);
}

static const VMStateDescription vmstate_pwm = {
    .name = "stmp3770-pwm",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl0, STMP3770PWMState),
        VMSTATE_UINT32_ARRAY(period, STMP3770PWMState, STMP3770_PWM_NUM_CHANNELS),
        VMSTATE_UINT32_ARRAY(duty, STMP3770PWMState, STMP3770_PWM_NUM_CHANNELS),
        VMSTATE_UINT32_ARRAY(active, STMP3770PWMState, STMP3770_PWM_NUM_CHANNELS),
        VMSTATE_END_OF_LIST()
    }
};

static void pwm_init(Object *obj)
{
    STMP3770PWMState *s = STMP3770_PWM(obj);

    s->ctrl0 = CTRL0_SFTRST | CTRL0_CLKGATE;
}

static void pwm_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = pwm_realize;
    device_class_set_legacy_reset(dc, pwm_reset);
    dc->vmsd = &vmstate_pwm;
}

static const TypeInfo pwm_type_info = {
    .name          = TYPE_STMP3770_PWM,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770PWMState),
    .instance_init = pwm_init,
    .class_init    = pwm_class_init,
};

static void pwm_register_types(void)
{
    type_register_static(&pwm_type_info);
}

type_init(pwm_register_types)
