/*
 * STMP3770 Digital Control and On-Chip RAM (DIGCTL)
 *
 * Based on STMP3770 Reference Manual Chapter 7
 *
 * Features:
 * - DIGCTL control / status registers
 * - Free-running HCLK counter
 * - On-chip RAM control / repair
 * - Software write-once register
 * - High-entropy pseudo-random seed
 * - Microseconds counter (1 MHz)
 * - DFLPT movable PTE locators (8)
 * - Debug trap address range
 * - ARM cache timing control
 * - Chip ID (CHIPID)
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
#include "qemu/timer.h"
#include "hw/misc/stmp3770_digctl.h"

/* Register offsets (from Chapter 7.2 Register Map) */
#define REG_CTRL                0x000
#define REG_STATUS              0x010
#define REG_HCLKCOUNT           0x020
#define REG_RAMCTRL             0x030
#define REG_RAMREPAIR           0x040
#define REG_ROMCTRL             0x050
#define REG_WRITEONCE           0x060
#define REG_ENTROPY             0x090
#define REG_ENTROPY_LATCHED     0x0A0
#define REG_SJTAGDBG            0x0B0
#define REG_MICROSECONDS        0x0C0
#define REG_DBGRD               0x0D0
#define REG_DBG                 0x0E0
#define REG_OCRAM_BIST_CSR      0x0F0
#define REG_OCRAM_STATUS0       0x110
#define REG_OCRAM_STATUS1       0x120
#define REG_OCRAM_STATUS2       0x130
#define REG_OCRAM_STATUS3       0x140
#define REG_OCRAM_STATUS4       0x150
#define REG_OCRAM_STATUS5       0x160
#define REG_OCRAM_STATUS6       0x170
#define REG_OCRAM_STATUS7       0x180
#define REG_OCRAM_STATUS8       0x190
#define REG_OCRAM_STATUS9       0x1A0
#define REG_OCRAM_STATUS10      0x1B0
#define REG_OCRAM_STATUS11      0x1C0
#define REG_OCRAM_STATUS12      0x1D0
#define REG_OCRAM_STATUS13      0x1E0
#define REG_ARMCACHE            0x2B0
#define REG_DEBUG_TRAP_ADDR_LOW 0x2C0
#define REG_DEBUG_TRAP_ADDR_HIGH 0x2D0
#define REG_CHIPID              0x310
#define REG_AHB_STATS_SELECT    0x330
#define REG_L0_AHB_ACTIVE       0x340
#define REG_L0_AHB_STALLED      0x350
#define REG_L0_AHB_DATA         0x360
#define REG_L1_AHB_ACTIVE       0x370
#define REG_L1_AHB_STALLED      0x380
#define REG_L1_AHB_DATA         0x390
#define REG_L2_AHB_ACTIVE       0x3A0
#define REG_L2_AHB_STALLED      0x3B0
#define REG_L2_AHB_DATA         0x3C0
#define REG_L3_AHB_ACTIVE       0x3D0
#define REG_L3_AHB_STALLED      0x3E0
#define REG_L3_AHB_DATA         0x3F0
#define REG_MPTE0_LOC           0x400
#define REG_MPTE1_LOC           0x410
#define REG_MPTE2_LOC           0x420
#define REG_MPTE3_LOC           0x430
#define REG_MPTE4_LOC           0x440
#define REG_MPTE5_LOC           0x450
#define REG_MPTE6_LOC           0x460
#define REG_MPTE7_LOC           0x470

/* SET/CLR/TOG offsets (within 16-byte aligned block) */
#define REG_SET                 0x4
#define REG_CLR                 0x8
#define REG_TOG                 0xC

/* CTRL register bits (7.4.1) */
#define CTRL_LATCH_ENTROPY      (1 << 0)
#define CTRL_USB_CLKGATE        (1 << 2)

/* STATUS register reset (7.4.2) - USB features present */
#define STATUS_USB_FEATURES     ((1U << 31) | (1U << 30) | (1U << 29) | (1U << 28))

/* WRITEONCE reset (7.4.7) */
#define WRITEONCE_RESET         0xA5A5A5A5

/* DBGRD / DBG fixed debug values (7.4.12, 7.4.13) */
#define DBG_VALUE               0x87654321
#define DBGRD_VALUE             0x789ABCDE  /* ~DBG_VALUE */

/* CHIPID (7.4.34) - STMP37xx product code 0x37B0, TA1 revision 0x00 */
#define CHIPID_PRODUCT_CODE     0x37B0
#define CHIPID_REVISION         0x00

/* ROMCTRL reset (7.4.6) - RD_MARGIN = 0x2 */
#define ROMCTRL_RESET           0x2

/* SJTAGDBG reset (7.4.10) - SJTAG_STATE = 0x2 */
#define SJTAGDBG_RESET          (0x2 << 16)

#define TYPE_STMP3770_DIGCTL "stmp3770-digctl"

struct STMP3770DIGCTLState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;

    /* Control / status */
    uint32_t ctrl;
    uint32_t status;
    uint32_t ramctrl;
    uint32_t ramrepair;
    uint32_t romctrl;
    uint32_t writeonce;
    bool writeonce_written;

    /* Entropy */
    uint32_t entropy;
    uint32_t entropy_latched;

    /* SJTAG debug */
    uint32_t sjtagdbg;

    /* Counters */
    uint32_t microseconds;
    uint64_t hclkcount_base_ns;  /* QEMU clock snapshot at last sync */

    /* OCRAM BIST */
    uint32_t ocram_bist_csr;
    uint32_t ocram_status[14];   /* STATUS0..STATUS13 */

    /* ARM cache / debug trap */
    uint32_t armcache;
    uint32_t debug_trap_addr_low;
    uint32_t debug_trap_addr_high;

    /* AHB statistics */
    uint32_t ahb_stats_select;
    uint32_t ahb_l_active[4];    /* L0..L3 */
    uint32_t ahb_l_stalled[4];
    uint32_t ahb_l_data[4];

    /* DFLPT PTE locators */
    uint32_t mpte_loc[8];
};

uint32_t stmp3770_digctl_get_mpte_loc(STMP3770DIGCTLState *s, int idx)
{
    g_assert(idx >= 0 && idx < 8);
    return s->mpte_loc[idx] & 0xFFF;
}

static uint64_t digctl_hclkcount_get(STMP3770DIGCTLState *s)
{
    /*
     * Free-running HCLK counter. Return the elapsed virtual time since reset
     * as a 32-bit monotonic value. This approximates a real HCLK frequency;
     * it is sufficient for software that polls the counter for delays.
     */
    return (uint32_t)(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) - s->hclkcount_base_ns);
}

static uint64_t stmp3770_digctl_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770DIGCTLState *s = STMP3770_DIGCTL(opaque);
    uint32_t value = 0;

    /* SET/CLR/TOG variants read identically to the base register */
    offset &= ~0xFULL;

    switch (offset) {
    case REG_CTRL:
        value = s->ctrl;
        break;

    case REG_STATUS:
        value = s->status;
        break;

    case REG_HCLKCOUNT:
        value = (uint32_t)digctl_hclkcount_get(s);
        break;

    case REG_RAMCTRL:
        value = s->ramctrl;
        break;

    case REG_RAMREPAIR:
        value = s->ramrepair;
        break;

    case REG_ROMCTRL:
        value = s->romctrl;
        break;

    case REG_WRITEONCE:
        value = s->writeonce;
        break;

    case REG_ENTROPY:
        /* Return a pseudo-entropy value derived from the QEMU clock */
        value = (uint32_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        break;

    case REG_ENTROPY_LATCHED:
        value = s->entropy_latched;
        break;

    case REG_SJTAGDBG:
        value = s->sjtagdbg;
        break;

    case REG_MICROSECONDS:
        /*
         * 1 MHz counter. Approximate using the virtual clock: divide ns
         * by 1000 to get microseconds, add the stored offset so guest
         * writes remain observable.
         */
        value = s->microseconds +
                (uint32_t)(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / 1000);
        break;

    case REG_DBGRD:
        value = DBGRD_VALUE;
        break;

    case REG_DBG:
        value = DBG_VALUE;
        break;

    case REG_OCRAM_BIST_CSR:
        value = s->ocram_bist_csr;
        break;

    case REG_OCRAM_STATUS0 ... REG_OCRAM_STATUS13:
        value = s->ocram_status[(offset - REG_OCRAM_STATUS0) / 0x10];
        break;

    case REG_ARMCACHE:
        value = s->armcache;
        break;

    case REG_DEBUG_TRAP_ADDR_LOW:
        value = s->debug_trap_addr_low;
        break;

    case REG_DEBUG_TRAP_ADDR_HIGH:
        value = s->debug_trap_addr_high;
        break;

    case REG_CHIPID:
        value = (CHIPID_PRODUCT_CODE << 16) | CHIPID_REVISION;
        break;

    case REG_AHB_STATS_SELECT:
        value = s->ahb_stats_select;
        break;

    case REG_L0_AHB_ACTIVE:
    case REG_L1_AHB_ACTIVE:
    case REG_L2_AHB_ACTIVE:
    case REG_L3_AHB_ACTIVE:
        value = s->ahb_l_active[(offset - REG_L0_AHB_ACTIVE) / 0x30];
        break;

    case REG_L0_AHB_STALLED:
    case REG_L1_AHB_STALLED:
    case REG_L2_AHB_STALLED:
    case REG_L3_AHB_STALLED:
        value = s->ahb_l_stalled[(offset - REG_L0_AHB_STALLED) / 0x30];
        break;

    case REG_L0_AHB_DATA:
    case REG_L1_AHB_DATA:
    case REG_L2_AHB_DATA:
    case REG_L3_AHB_DATA:
        value = s->ahb_l_data[(offset - REG_L0_AHB_DATA) / 0x30];
        break;

    case REG_MPTE0_LOC ... REG_MPTE7_LOC:
        value = s->mpte_loc[(offset - REG_MPTE0_LOC) / 0x10];
        break;

    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                     "%s: bad offset 0x%" HWADDR_PRIx "\n", __func__, offset);
        break;
    }

    return value;
}

static void stmp3770_digctl_write(void *opaque, hwaddr offset,
                                   uint64_t value, unsigned size)
{
    STMP3770DIGCTLState *s = STMP3770_DIGCTL(opaque);
    uint32_t val = value;
    bool is_set = (offset & 0xF) == REG_SET;
    bool is_clr = (offset & 0xF) == REG_CLR;
    bool is_tog = (offset & 0xF) == REG_TOG;
    uint32_t *target = NULL;

    offset &= ~0xFULL;

    switch (offset) {
    case REG_CTRL:
        target = &s->ctrl;
        /* LATCH_ENTROPY: latch current entropy on rising edge */
        if (!is_clr && (val & CTRL_LATCH_ENTROPY)) {
            s->entropy_latched =
                (uint32_t)qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        }
        break;

    case REG_STATUS:
        /* Read-only, ignore writes */
        return;

    case REG_HCLKCOUNT:
        /* Read-only, ignore writes */
        return;

    case REG_RAMCTRL:
        target = &s->ramctrl;
        break;

    case REG_RAMREPAIR:
        target = &s->ramrepair;
        break;

    case REG_ROMCTRL:
        target = &s->romctrl;
        break;

    case REG_WRITEONCE:
        /* One-time-write register: first write sticks, later writes ignored */
        if (!s->writeonce_written) {
            s->writeonce = val;
            s->writeonce_written = true;
            s->status |= (1U << 0);  /* STATUS.WRITTEN */
        }
        return;

    case REG_ENTROPY:
        /* Read-only */
        return;

    case REG_ENTROPY_LATCHED:
        /* Read-only */
        return;

    case REG_SJTAGDBG:
        target = &s->sjtagdbg;
        /* Only bits 0-1 are RW (SJTAG_DEBUG_DATA / SJTAG_DEBUG_OE) */
        val &= 0x3;
        if (is_set || is_clr || is_tog) {
            uint32_t mask = val;
            if (is_set) {
                s->sjtagdbg = (s->sjtagdbg & ~0x3) | ((s->sjtagdbg | mask) & 0x3);
            } else if (is_clr) {
                s->sjtagdbg = (s->sjtagdbg & ~0x3) | ((s->sjtagdbg & ~mask) & 0x3);
            } else {
                s->sjtagdbg = (s->sjtagdbg & ~0x3) | ((s->sjtagdbg ^ mask) & 0x3);
            }
        } else {
            s->sjtagdbg = (s->sjtagdbg & ~0x3) | (val & 0x3);
        }
        return;

    case REG_MICROSECONDS:
        /*
         * RW 1 MHz counter. We capture the offset between the requested
         * value and the current virtual-clock microseconds so subsequent
         * reads return a monotonic count from the written base.
         */
        s->microseconds = val -
            (uint32_t)(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / 1000);
        return;

    case REG_DBGRD:
    case REG_DBG:
        /* Read-only debug values */
        return;

    case REG_OCRAM_BIST_CSR:
        target = &s->ocram_bist_csr;
        /* START is self-clearing in real HW; BIST runs instantly here */
        if (val & 0x1) {
            val &= ~0x1U;             /* clear START */
            val |= (1U << 1);         /* set DONE */
            val |= (1U << 2);         /* set PASS */
        }
        break;

    case REG_OCRAM_STATUS0 ... REG_OCRAM_STATUS13:
        /* Read-only BIST status registers */
        return;

    case REG_ARMCACHE:
        target = &s->armcache;
        break;

    case REG_DEBUG_TRAP_ADDR_LOW:
        target = &s->debug_trap_addr_low;
        break;

    case REG_DEBUG_TRAP_ADDR_HIGH:
        target = &s->debug_trap_addr_high;
        break;

    case REG_CHIPID:
        /* Read-only */
        return;

    case REG_AHB_STATS_SELECT:
        target = &s->ahb_stats_select;
        break;

    case REG_L0_AHB_ACTIVE:
    case REG_L1_AHB_ACTIVE:
    case REG_L2_AHB_ACTIVE:
    case REG_L3_AHB_ACTIVE:
        target = &s->ahb_l_active[(offset - REG_L0_AHB_ACTIVE) / 0x30];
        break;

    case REG_L0_AHB_STALLED:
    case REG_L1_AHB_STALLED:
    case REG_L2_AHB_STALLED:
    case REG_L3_AHB_STALLED:
        target = &s->ahb_l_stalled[(offset - REG_L0_AHB_STALLED) / 0x30];
        break;

    case REG_L0_AHB_DATA:
    case REG_L1_AHB_DATA:
    case REG_L2_AHB_DATA:
    case REG_L3_AHB_DATA:
        target = &s->ahb_l_data[(offset - REG_L0_AHB_DATA) / 0x30];
        break;

    case REG_MPTE0_LOC ... REG_MPTE7_LOC: {
        int idx = (offset - REG_MPTE0_LOC) / 0x10;
        /* Mask to 12-bit LOC field; forbid 0x800 (fixed PTE_2048) */
        uint32_t masked = val & 0xFFF;
        if (masked == 0x800) {
            qemu_log_mask(LOG_GUEST_ERROR,
                         "%s: MPTE%d_LOC forbidden value 0x800\n",
                         __func__, idx);
            return;
        }
        s->mpte_loc[idx] = masked;
        return;
    }

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
}

static const MemoryRegionOps stmp3770_digctl_ops = {
    .read = stmp3770_digctl_read,
    .write = stmp3770_digctl_write,
    .endianness = DEVICE_NATIVE_ENDIAN,
    /* Registers are 32-bit, 16-byte aligned with SET/CLR/TOG variants */
    .valid.min_access_size = 1,
    .valid.max_access_size = 4,
};

static void stmp3770_digctl_reset(DeviceState *dev)
{
    STMP3770DIGCTLState *s = STMP3770_DIGCTL(dev);

    s->ctrl = CTRL_USB_CLKGATE;          /* USB_CLKGATE reset = 1 */
    s->status = STATUS_USB_FEATURES;     /* USB features present */
    s->ramctrl = 0;
    s->ramrepair = 0;
    s->romctrl = ROMCTRL_RESET;          /* RD_MARGIN = 0x2 */
    s->writeonce = WRITEONCE_RESET;      /* 0xA5A5A5A5 */
    s->writeonce_written = false;
    s->entropy = 0;
    s->entropy_latched = 0;
    s->sjtagdbg = SJTAGDBG_RESET;        /* SJTAG_STATE = 0x2 */
    s->microseconds = 0;
    s->hclkcount_base_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);

    s->ocram_bist_csr = 0;
    memset(s->ocram_status, 0, sizeof(s->ocram_status));

    s->armcache = 0;
    s->debug_trap_addr_low = 0;
    s->debug_trap_addr_high = 0;

    s->ahb_stats_select = 0;
    memset(s->ahb_l_active, 0, sizeof(s->ahb_l_active));
    memset(s->ahb_l_stalled, 0, sizeof(s->ahb_l_stalled));
    memset(s->ahb_l_data, 0, sizeof(s->ahb_l_data));

    /* MPTE n reset value = n */
    for (int i = 0; i < 8; i++) {
        s->mpte_loc[i] = i;
    }
}

static void stmp3770_digctl_init(Object *obj)
{
    STMP3770DIGCTLState *s = STMP3770_DIGCTL(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);

    memory_region_init_io(&s->iomem, obj, &stmp3770_digctl_ops, s,
                          TYPE_STMP3770_DIGCTL, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);
}

static const VMStateDescription vmstate_stmp3770_digctl = {
    .name = TYPE_STMP3770_DIGCTL,
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl, STMP3770DIGCTLState),
        VMSTATE_UINT32(status, STMP3770DIGCTLState),
        VMSTATE_UINT32(ramctrl, STMP3770DIGCTLState),
        VMSTATE_UINT32(ramrepair, STMP3770DIGCTLState),
        VMSTATE_UINT32(romctrl, STMP3770DIGCTLState),
        VMSTATE_UINT32(writeonce, STMP3770DIGCTLState),
        VMSTATE_BOOL(writeonce_written, STMP3770DIGCTLState),
        VMSTATE_UINT32(entropy, STMP3770DIGCTLState),
        VMSTATE_UINT32(entropy_latched, STMP3770DIGCTLState),
        VMSTATE_UINT32(sjtagdbg, STMP3770DIGCTLState),
        VMSTATE_UINT32(microseconds, STMP3770DIGCTLState),
        VMSTATE_UINT64(hclkcount_base_ns, STMP3770DIGCTLState),
        VMSTATE_UINT32(ocram_bist_csr, STMP3770DIGCTLState),
        VMSTATE_UINT32_ARRAY(ocram_status, STMP3770DIGCTLState, 14),
        VMSTATE_UINT32(armcache, STMP3770DIGCTLState),
        VMSTATE_UINT32(debug_trap_addr_low, STMP3770DIGCTLState),
        VMSTATE_UINT32(debug_trap_addr_high, STMP3770DIGCTLState),
        VMSTATE_UINT32(ahb_stats_select, STMP3770DIGCTLState),
        VMSTATE_UINT32_ARRAY(ahb_l_active, STMP3770DIGCTLState, 4),
        VMSTATE_UINT32_ARRAY(ahb_l_stalled, STMP3770DIGCTLState, 4),
        VMSTATE_UINT32_ARRAY(ahb_l_data, STMP3770DIGCTLState, 4),
        VMSTATE_UINT32_ARRAY(mpte_loc, STMP3770DIGCTLState, 8),
        VMSTATE_END_OF_LIST()
    }
};

static void stmp3770_digctl_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, stmp3770_digctl_reset);
    dc->vmsd = &vmstate_stmp3770_digctl;
}

static const TypeInfo stmp3770_digctl_info = {
    .name          = TYPE_STMP3770_DIGCTL,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770DIGCTLState),
    .instance_init = stmp3770_digctl_init,
    .class_init    = stmp3770_digctl_class_init,
};

static void stmp3770_digctl_register_types(void)
{
    type_register_static(&stmp3770_digctl_info);
}

type_init(stmp3770_digctl_register_types)
