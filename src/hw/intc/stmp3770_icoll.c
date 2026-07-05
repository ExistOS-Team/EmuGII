/*
 * STMP3770 Interrupt Collector (ICOLL)
 *
 * Based on STMP3770 Reference Manual Chapter 5
 *
 * Features:
 * - 64 interrupt sources with 4-level priority (0-3)
 * - Vectorized interrupt handling
 * - 8 sources (28-35) can be routed to FIQ
 * - Per-source enable and software trigger
 * - Nested interrupt support
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
#include "hw/intc/stmp3770_icoll.h"

/* Register offsets */
#define REG_VECTOR          0x000
#define REG_LEVELACK        0x010
#define REG_CTRL            0x020
#define REG_STAT            0x030
#define REG_RAW0            0x040
#define REG_RAW1            0x050
#define REG_PRIORITY0       0x060
#define REG_PRIORITY1       0x070
#define REG_PRIORITY2       0x080
#define REG_PRIORITY3       0x090
#define REG_PRIORITY4       0x0A0
#define REG_PRIORITY5       0x0B0
#define REG_PRIORITY6       0x0C0
#define REG_PRIORITY7       0x0D0
#define REG_PRIORITY8       0x0E0
#define REG_PRIORITY9       0x0F0
#define REG_PRIORITY10      0x100
#define REG_PRIORITY11      0x110
#define REG_PRIORITY12      0x120
#define REG_PRIORITY13      0x130
#define REG_PRIORITY14      0x140
#define REG_PRIORITY15      0x150
#define REG_VBASE           0x160

/* Register SET/CLR/TOG offsets */
#define REG_SET             0x4
#define REG_CLR             0x8
#define REG_TOG             0xC

/* CTRL register bits (STMP3770 ref: SFTRST/CLKGATE upper, pitch/final enables mid) */
#define CTRL_SFTRST             (1U << 31)
#define CTRL_CLKGATE            (1U << 30)
#define CTRL_VECTOR_PITCH_MASK  0x00E00000
#define CTRL_VECTOR_PITCH_SHIFT 21
#define CTRL_BYPASS_FSM         (1U << 20)
#define CTRL_NO_NESTING         (1U << 19)
#define CTRL_ARM_RSE_MODE       (1U << 18)
#define CTRL_FIQ_FINAL_ENABLE   (1U << 17)
#define CTRL_IRQ_FINAL_ENABLE   (1U << 16)

/* STAT register bits */
#define STAT_VECTOR_NUMBER_MASK 0x3F

#define TYPE_STMP3770_ICOLL "stmp3770-icoll"

struct STMP3770ICOLLState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq;               /* IRQ output to CPU */
    qemu_irq fiq;               /* FIQ output to CPU */

    /* Registers */
    uint32_t ctrl;
    uint32_t vbase;
    uint32_t vector_pitch;

    /* Priority registers - one per 4 interrupt sources */
    /* Each priority reg contains: ENABLE[3:0], PRIORITY[3:0] for 4 sources */
    uint32_t priority[16];      /* PRIORITY0-15, covers all 64 sources */

    /* Raw interrupt status */
    uint64_t raw_status;        /* Bits 0-63: raw interrupt inputs */

    /* In-service tracking for nested interrupts */
    uint32_t level_active[4];   /* Active interrupts per level */
    uint32_t current_level;     /* Current service level */

    /* FIQ enable for sources 28-35 */
    uint8_t fiq_enable;         /* 8 bits for sources 28-35 */

    /* Highest priority pending IRQ vector number */
    uint32_t vector;
};

static void stmp3770_icoll_update(STMP3770ICOLLState *s)
{
    int i, level;
    uint32_t pending_irq = 0;
    uint32_t pending_fiq = 0;
    uint32_t vector = 0;
    bool irq_enabled = s->ctrl & CTRL_IRQ_FINAL_ENABLE;
    bool fiq_enabled = s->ctrl & CTRL_FIQ_FINAL_ENABLE;

    /* Check each interrupt source */
    for (i = 0; i < 64; i++) {
        bool active = (s->raw_status >> i) & 1;
        int pri_reg = i / 4;
        int pri_bit = (i % 4) * 8;
        uint32_t pri_val = s->priority[pri_reg];
        bool enabled = (pri_val >> (pri_bit + 2)) & 1;

        if (!active || !enabled) {
            continue;
        }

        /* Check if this source is routed to FIQ (only sources 28-35) */
        if (i >= 28 && i <= 35 && ((s->fiq_enable >> (i - 28)) & 1)) {
            pending_fiq = 1;
            continue;
        }

        /* This is an IRQ source */
        if (!pending_irq) {
            vector = i;
        }
        pending_irq = 1;
    }

    s->vector = vector;

    /* Update IRQ/FIQ outputs */
    qemu_set_irq(s->irq, irq_enabled && pending_irq);
    qemu_set_irq(s->fiq, fiq_enabled && pending_fiq);
}

static void stmp3770_icoll_set_irq(void *opaque, int irq, int level)
{
    STMP3770ICOLLState *s = STMP3770_ICOLL(opaque);

    if (level) {
        s->raw_status |= (1ULL << irq);
    } else {
        s->raw_status &= ~(1ULL << irq);
    }

    stmp3770_icoll_update(s);
}

static uint64_t icoll_read_subword(uint32_t value, hwaddr offset, unsigned size)
{
    unsigned shift = (offset & 3) * 8;
    uint32_t mask = (size >= 4) ? 0xFFFFFFFFu : ((1u << (size * 8)) - 1u);

    return (value >> shift) & mask;
}

static uint64_t stmp3770_icoll_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770ICOLLState *s = STMP3770_ICOLL(opaque);
    hwaddr base = offset & ~0xFULL;
    uint32_t value = 0;

    switch (base) {
    case REG_VECTOR:
        {
            /*
             * Return the vector address for the highest priority pending
             * interrupt.  The lower bits encode the vector number scaled by
             * the configured pitch; the firmware extracts IRQVECTOR from bits
             * 2+ (pitch is normally 4 bytes/entry, so vector = raw / 4).
             */
            uint32_t pitch_field = (s->ctrl & CTRL_VECTOR_PITCH_MASK) >>
                                   CTRL_VECTOR_PITCH_SHIFT;
            uint32_t pitch = (pitch_field + 1) * 4;
            value = s->vbase + s->vector * pitch;
        }
        break;

    case REG_CTRL:
        value = s->ctrl;
        break;

    case REG_VBASE:
        value = s->vbase;
        break;

    case REG_RAW0:
        value = (uint32_t)(s->raw_status & 0xFFFFFFFF);
        break;

    case REG_RAW1:
        value = (uint32_t)(s->raw_status >> 32);
        break;

    case REG_PRIORITY0 ... REG_PRIORITY15:
        value = s->priority[(base - REG_PRIORITY0) / 0x10];
        break;

    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                     "%s: bad offset 0x%" HWADDR_PRIx "\n", __func__, offset);
        break;
    }

    return icoll_read_subword(value, offset, size);
}

static void stmp3770_icoll_write(void *opaque, hwaddr offset,
                                  uint64_t value, unsigned size)
{
    STMP3770ICOLLState *s = STMP3770_ICOLL(opaque);
    hwaddr base_offset = offset & ~0xF;
    bool is_set = (offset & 0xF) == REG_SET;
    bool is_clr = (offset & 0xF) == REG_CLR;
    bool is_tog = (offset & 0xF) == REG_TOG;
    uint32_t *target = NULL;
    uint32_t val;

    /* Handle sub-word writes (byte/halfword) for bitfield access */
    if (size < 4) {
        unsigned shift = (offset & 3) * 8;
        uint32_t mask = ((1ULL << (size * 8)) - 1) << shift;

        /* Read-modify-write for sub-word access */
        switch (base_offset) {
        case REG_CTRL:
            target = &s->ctrl;
            break;
        case REG_VBASE:
            target = &s->vbase;
            break;
        case REG_PRIORITY0 ... REG_PRIORITY15:
            target = &s->priority[(base_offset - REG_PRIORITY0) / 0x10];
            break;
        default:
            qemu_log_mask(LOG_GUEST_ERROR,
                         "%s: sub-word write to unsupported offset 0x%" HWADDR_PRIx "\n",
                         __func__, offset);
            return;
        }

        if (target) {
            *target = (*target & ~mask) | ((value << shift) & mask);
        }

        stmp3770_icoll_update(s);
        return;
    }

    /* Standard 32-bit write handling */
    val = value;
    offset = base_offset;

    switch (offset) {
    case REG_CTRL:
        target = &s->ctrl;
        break;

    case REG_VBASE:
        target = &s->vbase;
        break;

    case REG_LEVELACK:
        /* Acknowledge interrupt level */
        /* Writing (1 << level) acknowledges that level */
        break;

    case REG_PRIORITY0 ... REG_PRIORITY15:
        target = &s->priority[(offset - REG_PRIORITY0) / 0x10];
        break;

    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                     "%s: bad offset 0x%" HWADDR_PRIx "\n", __func__, offset);
        return;
    }

    if (target) {
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

    /* Hardware ties CLKGATE to SFTRST on the control register */
    if (offset == REG_CTRL) {
        if (s->ctrl & CTRL_SFTRST) {
            s->ctrl |= CTRL_CLKGATE;
        } else {
            s->ctrl &= ~CTRL_CLKGATE;
        }
    }

    stmp3770_icoll_update(s);
}

static const MemoryRegionOps stmp3770_icoll_ops = {
    .read = stmp3770_icoll_read,
    .write = stmp3770_icoll_write,
    .endianness = DEVICE_NATIVE_ENDIAN,
};

static void stmp3770_icoll_reset(DeviceState *dev)
{
    STMP3770ICOLLState *s = STMP3770_ICOLL(dev);
    int i;

    s->ctrl = CTRL_CLKGATE | CTRL_SFTRST;
    s->vbase = 0;
    s->vector = 0;
    s->raw_status = 0;
    s->current_level = 0;
    s->fiq_enable = 0;

    for (i = 0; i < 16; i++) {
        s->priority[i] = 0;
    }

    for (i = 0; i < 4; i++) {
        s->level_active[i] = 0;
    }
}

static void stmp3770_icoll_init(Object *obj)
{
    STMP3770ICOLLState *s = STMP3770_ICOLL(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &stmp3770_icoll_ops, s,
                         TYPE_STMP3770_ICOLL, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);

    /* IRQ and FIQ outputs to CPU */
    sysbus_init_irq(sbd, &s->irq);
    sysbus_init_irq(sbd, &s->fiq);

    /* 64 IRQ inputs from peripherals */
    qdev_init_gpio_in(DEVICE(obj), stmp3770_icoll_set_irq, 64);
}

static const VMStateDescription vmstate_stmp3770_icoll = {
    .name = TYPE_STMP3770_ICOLL,
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl, STMP3770ICOLLState),
        VMSTATE_UINT32(vbase, STMP3770ICOLLState),
        VMSTATE_UINT32(vector, STMP3770ICOLLState),
        VMSTATE_UINT32_ARRAY(priority, STMP3770ICOLLState, 16),
        VMSTATE_UINT64(raw_status, STMP3770ICOLLState),
        VMSTATE_UINT32_ARRAY(level_active, STMP3770ICOLLState, 4),
        VMSTATE_UINT32(current_level, STMP3770ICOLLState),
        VMSTATE_UINT8(fiq_enable, STMP3770ICOLLState),
        VMSTATE_END_OF_LIST()
    }
};

static void stmp3770_icoll_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, stmp3770_icoll_reset);
    dc->vmsd = &vmstate_stmp3770_icoll;
}

static const TypeInfo stmp3770_icoll_info = {
    .name          = TYPE_STMP3770_ICOLL,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770ICOLLState),
    .instance_init = stmp3770_icoll_init,
    .class_init    = stmp3770_icoll_class_init,
};

static void stmp3770_icoll_register_types(void)
{
    type_register_static(&stmp3770_icoll_info);
}

type_init(stmp3770_icoll_register_types)
