/*
 * STMP3770 Data Co-Processor (DCP)
 *
 * Implements the documented control register file and the channel 0
 * memory-copy work-packet path. Crypto, hash, and CSC execution are added
 * separately as their packet semantics are completed.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/irq.h"
#include "hw/misc/stmp3770_dcp.h"
#include "migration/vmstate.h"
#include "qemu/bswap.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "system/address-spaces.h"

#define DCP_CHANNELS               4
#define DCP_MMIO_SIZE               0x2000

#define REG_CTRL                    0x000
#define REG_STAT                    0x010
#define REG_CHANNELCTRL             0x020
#define REG_CAPABILITY0             0x030
#define REG_CAPABILITY1             0x040
#define REG_CONTEXT                 0x050
#define REG_KEY                     0x060
#define REG_KEYDATA                 0x070
#define REG_PACKET0                 0x080
#define REG_CH_BASE                 0x100
#define REG_CH_STRIDE               0x040
#define REG_CH_CMDPTR               0x000
#define REG_CH_SEMA                 0x010
#define REG_CH_STAT                 0x020
#define REG_CH_OPTS                 0x030
#define REG_CSCCTRL0                0x300
#define REG_CSCSTAT                 0x310
#define REG_CSCOUTBUFPARAM          0x320
#define REG_CSCINBUFPARAM           0x330
#define REG_CSCRGB                  0x340
#define REG_CSCLUMA                 0x350
#define REG_CSCCHROMAU              0x360
#define REG_CSCCHROMAV              0x370
#define REG_CSCCOEFF0               0x380
#define REG_CSCCOEFF1               0x390
#define REG_CSCCOEFF2               0x3a0
#define REG_CSCXSCALE                0x3e0
#define REG_CSCYSCALE                0x3f0
#define REG_DBGSELECT                0x400
#define REG_DBGDATA                  0x410
#define REG_VERSION                 0x420

#define REG_SET                     0x4
#define REG_CLR                     0x8
#define REG_TOG                     0xc

#define CTRL_SFTRST                 (1U << 31)
#define CTRL_CLKGATE                (1U << 30)
#define CTRL_PRESENT_MASK           (3U << 28)
#define CTRL_WRITABLE_MASK          0xc0e001ffU
#define CTRL_RESET                  0xf0800000U
#define STAT_OTP_KEY_READY          (1U << 28)
#define STAT_WRITABLE_MASK          0x0000010fU
#define CHANNELCTRL_WRITABLE_MASK   0x0007ffffU
#define CH_STAT_WRITABLE_MASK       0x00ff003eU
#define CH_OPTS_WRITABLE_MASK       0x0000ffffU
#define CSCCTRL0_WRITABLE_MASK       0x00007ff1U
#define CSCSTAT_WRITABLE_MASK        0x00ff0035U
#define CSCOUTBUFPARAM_WRITABLE_MASK 0x00ffffffU
#define CSCINBUFPARAM_WRITABLE_MASK  0x00000fffU
#define CSCCOEFF0_WRITABLE_MASK      0x03ffffffU
#define CSCCOEFF1_WRITABLE_MASK      0x03ff03ffU
#define CSCXSCALE_WRITABLE_MASK      0x03ffffffU
#define DBGSELECT_WRITABLE_MASK      0x000000ffU

#define PACKET_CTRL_INTERRUPT       (1U << 0)
#define PACKET_CTRL_DECR_SEMA       (1U << 1)
#define PACKET_CTRL_CHAIN           (1U << 2)
#define PACKET_CTRL_MEMCOPY         (1U << 4)

#define CH_ERROR_HASH_MISMATCH      (1U << 1)
#define CH_ERROR_SETUP              (1U << 2)
#define CH_ERROR_PACKET             (1U << 3)
#define CH_ERROR_SRC                (1U << 4)
#define CH_ERROR_DST                (1U << 5)
#define CH_ERROR_NEXT_CHAIN_ZERO    0x01U
#define CH_ERROR_INVALID_MODE       0x05U

typedef struct DCPWorkPacket {
    uint32_t next;
    uint32_t ctrl0;
    uint32_t ctrl1;
    uint32_t source;
    uint32_t destination;
    uint32_t size;
    uint32_t payload;
    uint32_t status;
} DCPWorkPacket;

struct STMP3770DCPState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq_vmi;
    qemu_irq irq;

    uint32_t ctrl;
    uint32_t stat;
    uint32_t channelctrl;
    uint32_t context;
    uint32_t key;
    uint32_t key_data[4][4];
    uint32_t packet[7];
    uint32_t ch_cmdptr[DCP_CHANNELS];
    uint8_t ch_sema[DCP_CHANNELS];
    uint32_t ch_stat[DCP_CHANNELS];
    uint32_t ch_opts[DCP_CHANNELS];
    uint32_t cscctrl0;
    uint32_t cscstat;
    uint32_t cscoutbufparam;
    uint32_t cscinbufparam;
    uint32_t cscbuf[4];
    uint32_t csccoeff[3];
    uint32_t cscxscale;
    uint32_t cscyscale;
    uint32_t dbgselect;
};

static void dcp_update_irq(STMP3770DCPState *s)
{
    uint32_t pending = s->stat & 0x0f;
    bool ch0_merged = s->channelctrl & (1U << 16);
    bool vmi = (pending & 0x01) && (s->ctrl & 0x01) && !ch0_merged;
    bool shared = (pending & 0x0e & (s->ctrl & 0x0e)) != 0;

    if (ch0_merged && (pending & 0x01) && (s->ctrl & 0x01)) {
        shared = true;
    }
    if ((s->stat & (1U << 8)) && (s->ctrl & (1U << 8))) {
        shared = true;
    }

    qemu_set_irq(s->irq_vmi, vmi);
    qemu_set_irq(s->irq, shared);
}

static void dcp_reset_registers(STMP3770DCPState *s)
{
    s->ctrl = CTRL_RESET;
    s->stat = STAT_OTP_KEY_READY;
    s->channelctrl = 0;
    s->context = 0;
    s->key = 0;
    memset(s->key_data, 0, sizeof(s->key_data));
    memset(s->packet, 0, sizeof(s->packet));
    memset(s->ch_cmdptr, 0, sizeof(s->ch_cmdptr));
    memset(s->ch_sema, 0, sizeof(s->ch_sema));
    memset(s->ch_stat, 0, sizeof(s->ch_stat));
    memset(s->ch_opts, 0, sizeof(s->ch_opts));
    s->cscctrl0 = 0;
    s->cscstat = 0;
    s->cscoutbufparam = 0;
    s->cscinbufparam = 0;
    memset(s->cscbuf, 0, sizeof(s->cscbuf));
    s->csccoeff[0] = 0x012a8010;
    s->csccoeff[1] = 0x01980204;
    s->csccoeff[2] = 0x00d00064;
    s->cscxscale = 0;
    s->cscyscale = 0;
    s->dbgselect = 0;
    dcp_update_irq(s);
}

static uint32_t dcp_apply_sct(uint32_t old, uint32_t value, uint32_t mask,
                              unsigned int modifier)
{
    uint32_t writable = old & mask;

    switch (modifier) {
    case REG_SET:
        writable |= value & mask;
        break;
    case REG_CLR:
        writable &= ~(value & mask);
        break;
    case REG_TOG:
        writable ^= value & mask;
        break;
    default:
        writable = value & mask;
        break;
    }

    return (old & ~mask) | writable;
}

static bool dcp_channel_active(STMP3770DCPState *s, unsigned int ch)
{
    return !(s->ctrl & (CTRL_SFTRST | CTRL_CLKGATE)) &&
           (s->channelctrl & (1U << ch)) && s->ch_sema[ch] != 0;
}

static void dcp_channel_error(STMP3770DCPState *s, unsigned int ch,
                              uint32_t error_bit, uint32_t error_code)
{
    s->ch_stat[ch] = (s->ch_stat[ch] & 0xff000000U) |
                     ((error_code & 0xff) << 16) | error_bit;
    s->ch_sema[ch] = 0;
    s->stat |= 1U << ch;
    dcp_update_irq(s);
}

static void dcp_process_ch0(STMP3770DCPState *s)
{
    DCPWorkPacket raw;
    DCPWorkPacket packet;
    uint32_t tag;
    uint32_t remaining;
    hwaddr source;
    hwaddr destination;
    hwaddr packet_addr;
    uint8_t buffer[4096];

    if (!dcp_channel_active(s, 0)) {
        return;
    }

    packet_addr = s->ch_cmdptr[0];
    if (address_space_read(&address_space_memory, packet_addr,
                           MEMTXATTRS_UNSPECIFIED, &raw, sizeof(raw)) !=
        MEMTX_OK) {
        dcp_channel_error(s, 0, CH_ERROR_PACKET, 0);
        return;
    }

    packet.next = le32_to_cpu(raw.next);
    packet.ctrl0 = le32_to_cpu(raw.ctrl0);
    packet.ctrl1 = le32_to_cpu(raw.ctrl1);
    packet.source = le32_to_cpu(raw.source);
    packet.destination = le32_to_cpu(raw.destination);
    packet.size = le32_to_cpu(raw.size);
    packet.payload = le32_to_cpu(raw.payload);
    packet.status = le32_to_cpu(raw.status);
    s->packet[0] = packet.next;
    s->packet[1] = packet.ctrl0;
    s->packet[2] = packet.ctrl1;
    s->packet[3] = packet.source;
    s->packet[4] = packet.destination;
    s->packet[5] = packet.size;
    s->packet[6] = packet.payload;
    tag = packet.ctrl0 >> 24;

    if (!(packet.ctrl0 & PACKET_CTRL_MEMCOPY) ||
        (packet.ctrl0 & 0x000000e0U)) {
        dcp_channel_error(s, 0, CH_ERROR_SETUP, CH_ERROR_INVALID_MODE);
        return;
    }

    source = packet.source;
    destination = packet.destination;
    remaining = packet.size;
    while (remaining) {
        size_t length = MIN((uint32_t)sizeof(buffer), remaining);

        if (address_space_read(&address_space_memory, source,
                               MEMTXATTRS_UNSPECIFIED, buffer, length) !=
            MEMTX_OK) {
            dcp_channel_error(s, 0, CH_ERROR_SRC, 0);
            return;
        }
        if (address_space_write(&address_space_memory, destination,
                                MEMTXATTRS_UNSPECIFIED, buffer, length) !=
            MEMTX_OK) {
            dcp_channel_error(s, 0, CH_ERROR_DST, 0);
            return;
        }
        source += length;
        destination += length;
        remaining -= length;
    }

    raw.status = cpu_to_le32((tag << 24) | 1U);
    if (address_space_write(&address_space_memory, packet_addr + 0x1c,
                            MEMTXATTRS_UNSPECIFIED, &raw.status,
                            sizeof(raw.status)) != MEMTX_OK) {
        dcp_channel_error(s, 0, CH_ERROR_PACKET, 0);
        return;
    }

    s->ch_stat[0] = tag << 24;
    if (packet.ctrl0 & PACKET_CTRL_DECR_SEMA) {
        s->ch_sema[0]--;
    }
    if (packet.ctrl0 & PACKET_CTRL_CHAIN) {
        if (packet.next == 0) {
            dcp_channel_error(s, 0, CH_ERROR_PACKET, CH_ERROR_NEXT_CHAIN_ZERO);
            return;
        }
        s->ch_cmdptr[0] = packet.next;
    }
    if (packet.ctrl0 & PACKET_CTRL_INTERRUPT) {
        s->stat |= 1U;
    }
    dcp_update_irq(s);
}

static int dcp_channel_from_offset(hwaddr base)
{
    if (base < REG_CH_BASE || base >= REG_CH_BASE + DCP_CHANNELS * REG_CH_STRIDE) {
        return -1;
    }
    return (base - REG_CH_BASE) / REG_CH_STRIDE;
}

static uint64_t dcp_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770DCPState *s = STMP3770_DCP(opaque);
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    int ch;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dcp: unsupported read size %u\n",
                      size);
        return 0;
    }

    switch (base) {
    case REG_CTRL:
        return s->ctrl;
    case REG_STAT:
        return s->stat;
    case REG_CHANNELCTRL:
        return s->channelctrl;
    case REG_CAPABILITY0:
        return 0x00000404;
    case REG_CAPABILITY1:
        return 0x00010001;
    case REG_CONTEXT:
        return s->context;
    case REG_KEY:
        return s->key;
    case REG_KEYDATA:
        return s->key_data[(s->key >> 4) & 3][s->key & 3];
    case REG_CSCCTRL0:
        return s->cscctrl0;
    case REG_CSCSTAT:
        return s->cscstat;
    case REG_CSCOUTBUFPARAM:
        return s->cscoutbufparam;
    case REG_CSCINBUFPARAM:
        return s->cscinbufparam;
    case REG_CSCRGB:
    case REG_CSCLUMA:
    case REG_CSCCHROMAU:
    case REG_CSCCHROMAV:
        return s->cscbuf[(base - REG_CSCRGB) / 0x10];
    case REG_CSCCOEFF0:
    case REG_CSCCOEFF1:
    case REG_CSCCOEFF2:
        return s->csccoeff[(base - REG_CSCCOEFF0) / 0x10];
    case REG_CSCXSCALE:
        return s->cscxscale;
    case REG_CSCYSCALE:
        return s->cscyscale;
    case REG_DBGSELECT:
        return s->dbgselect;
    case REG_DBGDATA:
        return 0;
    case REG_VERSION:
        return 0x01000000;
    default:
        break;
    }

    if (base >= REG_PACKET0 && base <= REG_PACKET0 + 0x60) {
        return s->packet[(base - REG_PACKET0) / 0x10];
    }

    ch = dcp_channel_from_offset(base);
    if (ch < 0) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dcp: read from offset 0x%"
                      HWADDR_PRIx "\n", offset);
        return 0;
    }

    switch (base - (REG_CH_BASE + ch * REG_CH_STRIDE)) {
    case REG_CH_CMDPTR:
        return s->ch_cmdptr[ch];
    case REG_CH_SEMA:
        return (uint32_t)s->ch_sema[ch] << 16;
    case REG_CH_STAT:
        return s->ch_stat[ch];
    case REG_CH_OPTS:
        return s->ch_opts[ch];
    default:
        if (modifier) {
            return 0;
        }
        return 0;
    }
}

static void dcp_write(void *opaque, hwaddr offset, uint64_t value,
                      unsigned size)
{
    STMP3770DCPState *s = STMP3770_DCP(opaque);
    uint32_t val = value;
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    int ch;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dcp: unsupported write size %u\n",
                      size);
        return;
    }

    switch (base) {
    case REG_CTRL:
        s->ctrl = dcp_apply_sct(s->ctrl, val, CTRL_WRITABLE_MASK, modifier);
        s->ctrl = (s->ctrl & ~CTRL_PRESENT_MASK) | CTRL_PRESENT_MASK;
        if (s->ctrl & CTRL_SFTRST) {
            dcp_reset_registers(s);
        } else {
            dcp_update_irq(s);
            dcp_process_ch0(s);
        }
        return;
    case REG_STAT:
        s->stat = dcp_apply_sct(s->stat, val, STAT_WRITABLE_MASK, modifier);
        s->stat |= STAT_OTP_KEY_READY;
        dcp_update_irq(s);
        return;
    case REG_CHANNELCTRL:
        s->channelctrl = dcp_apply_sct(s->channelctrl, val,
                                       CHANNELCTRL_WRITABLE_MASK, modifier);
        dcp_update_irq(s);
        dcp_process_ch0(s);
        return;
    case REG_CONTEXT:
        if (modifier == 0) {
            s->context = val;
        }
        return;
    case REG_KEY:
        if (modifier == 0) {
            s->key = val & 0x33;
        }
        return;
    case REG_KEYDATA:
        if (modifier == 0) {
            unsigned int index = (s->key >> 4) & 3;
            unsigned int subword = s->key & 3;

            s->key_data[index][subword] = val;
            s->key = (s->key & ~3U) | ((subword + 1) & 3);
        }
        return;
    case REG_CSCCTRL0:
        s->cscctrl0 = dcp_apply_sct(s->cscctrl0, val,
                                    CSCCTRL0_WRITABLE_MASK, modifier);
        return;
    case REG_CSCSTAT:
        s->cscstat = dcp_apply_sct(s->cscstat, val,
                                   CSCSTAT_WRITABLE_MASK, modifier);
        return;
    case REG_CSCOUTBUFPARAM:
        if (modifier == 0) {
            s->cscoutbufparam = val & CSCOUTBUFPARAM_WRITABLE_MASK;
        }
        return;
    case REG_CSCINBUFPARAM:
        if (modifier == 0) {
            s->cscinbufparam = val & CSCINBUFPARAM_WRITABLE_MASK;
        }
        return;
    case REG_CSCRGB:
    case REG_CSCLUMA:
    case REG_CSCCHROMAU:
    case REG_CSCCHROMAV:
        if (modifier == 0) {
            s->cscbuf[(base - REG_CSCRGB) / 0x10] = val;
        }
        return;
    case REG_CSCCOEFF0:
        if (modifier == 0) {
            s->csccoeff[0] = val & CSCCOEFF0_WRITABLE_MASK;
        }
        return;
    case REG_CSCCOEFF1:
    case REG_CSCCOEFF2:
        if (modifier == 0) {
            s->csccoeff[(base - REG_CSCCOEFF0) / 0x10] =
                val & CSCCOEFF1_WRITABLE_MASK;
        }
        return;
    case REG_CSCXSCALE:
        if (modifier == 0) {
            s->cscxscale = val & CSCXSCALE_WRITABLE_MASK;
        }
        return;
    case REG_CSCYSCALE:
        if (modifier == 0) {
            s->cscyscale = val & CSCXSCALE_WRITABLE_MASK;
        }
        return;
    case REG_DBGSELECT:
        if (modifier == 0) {
            s->dbgselect = val & DBGSELECT_WRITABLE_MASK;
        }
        return;
    default:
        break;
    }

    ch = dcp_channel_from_offset(base);
    if (ch < 0) {
        qemu_log_mask(LOG_GUEST_ERROR, "stmp3770-dcp: write to offset 0x%"
                      HWADDR_PRIx "\n", offset);
        return;
    }

    switch (base - (REG_CH_BASE + ch * REG_CH_STRIDE)) {
    case REG_CH_CMDPTR:
        if (modifier == 0) {
            s->ch_cmdptr[ch] = val;
            if (ch == 0) {
                dcp_process_ch0(s);
            }
        }
        break;
    case REG_CH_SEMA:
        if (modifier == 0) {
            s->ch_sema[ch] = MIN(0xffU, s->ch_sema[ch] + (val & 0xff));
            if (ch == 0) {
                dcp_process_ch0(s);
            }
        } else if (modifier == REG_CLR && (val & 0xff)) {
            s->ch_sema[ch] = 0;
        }
        break;
    case REG_CH_STAT:
        s->ch_stat[ch] = dcp_apply_sct(s->ch_stat[ch], val,
                                       CH_STAT_WRITABLE_MASK, modifier);
        break;
    case REG_CH_OPTS:
        s->ch_opts[ch] = dcp_apply_sct(s->ch_opts[ch], val,
                                       CH_OPTS_WRITABLE_MASK, modifier);
        break;
    default:
        break;
    }
}

static const MemoryRegionOps dcp_ops = {
    .read = dcp_read,
    .write = dcp_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static void dcp_reset(DeviceState *dev)
{
    dcp_reset_registers(STMP3770_DCP(dev));
}

static void dcp_realize(DeviceState *dev, Error **errp)
{
    STMP3770DCPState *s = STMP3770_DCP(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);

    memory_region_init_io(&s->iomem, OBJECT(dev), &dcp_ops, s,
                          TYPE_STMP3770_DCP, DCP_MMIO_SIZE);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq_vmi);
    sysbus_init_irq(sbd, &s->irq);
}

static const VMStateDescription vmstate_dcp = {
    .name = "stmp3770-dcp",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl, STMP3770DCPState),
        VMSTATE_UINT32(stat, STMP3770DCPState),
        VMSTATE_UINT32(channelctrl, STMP3770DCPState),
        VMSTATE_UINT32(context, STMP3770DCPState),
        VMSTATE_UINT32(key, STMP3770DCPState),
        VMSTATE_UINT32_2DARRAY(key_data, STMP3770DCPState, 4, 4),
        VMSTATE_UINT32_ARRAY(packet, STMP3770DCPState, 7),
        VMSTATE_UINT32_ARRAY(ch_cmdptr, STMP3770DCPState, DCP_CHANNELS),
        VMSTATE_UINT8_ARRAY(ch_sema, STMP3770DCPState, DCP_CHANNELS),
        VMSTATE_UINT32_ARRAY(ch_stat, STMP3770DCPState, DCP_CHANNELS),
        VMSTATE_UINT32_ARRAY(ch_opts, STMP3770DCPState, DCP_CHANNELS),
        VMSTATE_UINT32(cscctrl0, STMP3770DCPState),
        VMSTATE_UINT32(cscstat, STMP3770DCPState),
        VMSTATE_UINT32(cscoutbufparam, STMP3770DCPState),
        VMSTATE_UINT32(cscinbufparam, STMP3770DCPState),
        VMSTATE_UINT32_ARRAY(cscbuf, STMP3770DCPState, 4),
        VMSTATE_UINT32_ARRAY(csccoeff, STMP3770DCPState, 3),
        VMSTATE_UINT32(cscxscale, STMP3770DCPState),
        VMSTATE_UINT32(cscyscale, STMP3770DCPState),
        VMSTATE_UINT32(dbgselect, STMP3770DCPState),
        VMSTATE_END_OF_LIST()
    }
};

static void dcp_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = dcp_realize;
    device_class_set_legacy_reset(dc, dcp_reset);
    dc->vmsd = &vmstate_dcp;
}

static const TypeInfo dcp_type_info = {
    .name = TYPE_STMP3770_DCP,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770DCPState),
    .class_init = dcp_class_init,
};

static void dcp_register_types(void)
{
    type_register_static(&dcp_type_info);
}

type_init(dcp_register_types)
