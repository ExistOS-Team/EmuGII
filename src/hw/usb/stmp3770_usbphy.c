/*
 * STMP3770 USB PHY emulation
 *
 * Based on STMP3770 Reference Manual Chapter 17
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
#include "hw/irq.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "hw/usb/stmp3770_usbphy.h"

#define USBPHY_VERSION      0x43000000

#define REG_CTRL0           0x000
#define REG_CTRL0_SET       0x004
#define REG_CTRL0_CLR       0x008
#define REG_CTRL0_TOG       0x00C
#define REG_STATUS          0x010
#define REG_DEBUG           0x020
#define REG_DEBUG_SET       0x024
#define REG_DEBUG_CLR       0x028
#define REG_DEBUG_TOG       0x02C
#define REG_VERSION         0x030
#define REG_VERSION_SET     0x034
#define REG_VERSION_CLR     0x038
#define REG_VERSION_TOG     0x03C

#define CTRL0_SFTRST        (1U << 31)
#define CTRL0_CLKGATE       (1U << 30)
#define CTRL0_UTMI_SUSPENDM (1U << 29)
#define CTRL0_HOSTDISCON    (1U << 21)
#define CTRL0_ENDEDGDETECT  (1U << 20)
#define CTRL0_ENHOSTDISCON  (1U << 21)

#define STATUS_HOSTDISCON   (1U << 3)
#define STATUS_DEVPLUGIN    (1U << 2)
#define STATUS_OTGID        (1U << 1)
#define STATUS_DCDETECTED   (1U << 0)

static void usbphy_apply_sct(uint32_t *reg, uint32_t value, int sct)
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

static uint64_t usbphy_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770USBPHYState *s = opaque;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-usbphy: unsupported read size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return 0;
    }

    switch (offset) {
    case REG_CTRL0:
        return s->ctrl0;
    case REG_STATUS:
        /* Report a connected B-device (peripheral) */
        return s->status;
    case REG_DEBUG:
        return s->debug;
    case REG_VERSION:
        return USBPHY_VERSION;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-usbphy: read from unimplemented offset "
                      HWADDR_FMT_plx "\n", offset);
        return 0;
    }
}

static void usbphy_write(void *opaque, hwaddr offset,
                         uint64_t value, unsigned size)
{
    STMP3770USBPHYState *s = opaque;
    int sct = (offset >> 2) & 3;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-usbphy: unsupported write size %u at offset "
                      HWADDR_FMT_plx "\n", size, offset);
        return;
    }

    if ((offset & ~0xC) == REG_CTRL0) {
        usbphy_apply_sct(&s->ctrl0, (uint32_t)value, sct);
        /* Hardware ties CLKGATE to SFTRST */
        if (s->ctrl0 & CTRL0_SFTRST) {
            s->ctrl0 |= CTRL0_CLKGATE;
        } else {
            s->ctrl0 &= ~CTRL0_CLKGATE;
        }
        return;
    }

    if ((offset & ~0xC) == REG_DEBUG) {
        usbphy_apply_sct(&s->debug, (uint32_t)value, sct);
        return;
    }

    if ((offset & ~0xC) == REG_VERSION) {
        /* VERSION is read-only; SET/CLR/TOG aliases are harmless no-ops */
        return;
    }

    qemu_log_mask(LOG_GUEST_ERROR,
                  "stmp3770-usbphy: write to unimplemented offset "
                  HWADDR_FMT_plx "\n", offset);
}

static const MemoryRegionOps usbphy_ops = {
    .read = usbphy_read,
    .write = usbphy_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
};

static void usbphy_reset(DeviceState *dev)
{
    STMP3770USBPHYState *s = STMP3770_USBPHY(dev);

    s->ctrl0 = CTRL0_SFTRST | CTRL0_CLKGATE;
    s->status = STATUS_DEVPLUGIN | STATUS_DCDETECTED;
    s->debug = 0;
}

static void usbphy_realize(DeviceState *dev, Error **errp)
{
    STMP3770USBPHYState *s = STMP3770_USBPHY(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    memory_region_init_io(&s->iomem, OBJECT(dev), &usbphy_ops, s,
                          TYPE_STMP3770_USBPHY, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);
}

static const VMStateDescription vmstate_usbphy = {
    .name = "stmp3770-usbphy",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl0, STMP3770USBPHYState),
        VMSTATE_UINT32(status, STMP3770USBPHYState),
        VMSTATE_UINT32(debug, STMP3770USBPHYState),
        VMSTATE_END_OF_LIST()
    }
};

static void usbphy_init(Object *obj)
{
    STMP3770USBPHYState *s = STMP3770_USBPHY(obj);

    s->ctrl0 = CTRL0_SFTRST | CTRL0_CLKGATE;
    s->status = STATUS_DEVPLUGIN | STATUS_DCDETECTED;
    s->debug = 0;
}

static void usbphy_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = usbphy_realize;
    device_class_set_legacy_reset(dc, usbphy_reset);
    dc->vmsd = &vmstate_usbphy;
}

static const TypeInfo usbphy_type_info = {
    .name          = TYPE_STMP3770_USBPHY,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770USBPHYState),
    .instance_init = usbphy_init,
    .class_init    = usbphy_class_init,
};

static void usbphy_register_types(void)
{
    type_register_static(&usbphy_type_info);
}

type_init(usbphy_register_types)
