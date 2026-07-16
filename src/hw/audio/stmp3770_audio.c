/*
 * STMP3770 Audio DAC/ADC emulation
 *
 * Based on STMP3770 Reference Manual Chapter 25 (AUDIOOUT/DAC) and
 * Chapter 24 (AUDIOIN/ADC), Tables 970-1025.
 *
 * The digital register files, FIFOs, DMA request and error interrupt
 * semantics are modeled per the PDF.  Sample streams flow through the
 * 8-word hardware FIFOs at the SRR-programmed rate so that occupancy,
 * overflow/underflow and DMAREQ toggles stay observable.  The QEMU
 * audio voice is attached behind the FIFOs; without a backend the
 * samples are simply drained (DAC) or zero-filled (ADC).  Analog-only
 * registers (volume/gain/power/clock) are storage-only: they do not
 * fabricate line behavior.  Per the PDF, most analog configuration
 * registers reset only on POR, not on the digital SFTRST.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/sysbus.h"
#include "hw/irq.h"
#include "hw/qdev-properties.h"
#include "audio/audio.h"
#include "hw/audio/stmp3770_audio.h"
#include "migration/vmstate.h"
#include "qemu/log.h"
#include "qemu/module.h"

#define AUDIO_VERSION           0x01010000U

#define REG_CTRL                0x000
#define REG_STAT                0x010
#define REG_SRR                 0x020
#define REG_VOLUME              0x030
#define REG_DEBUG               0x040
#define REG_DAC_HPVOL           0x050
#define REG_DAC_RESERVED        0x060
#define REG_DAC_PWRDN           0x070
#define REG_DAC_REFCTRL         0x080
#define REG_DAC_ANACTRL         0x090
#define REG_DAC_TEST            0x0a0
#define REG_DAC_BISTCTRL        0x0b0
#define REG_DAC_BISTSTAT0       0x0c0
#define REG_DAC_BISTSTAT1       0x0d0
#define REG_DAC_ANACLKCTRL      0x0e0
#define REG_DAC_DATA            0x0f0
#define REG_DAC_LINEOUTCTRL     0x100

#define REG_ADC_ADVOL           0x050
#define REG_ADC_MICLINE         0x060
#define REG_ADC_ANACLKCTRL      0x070
#define REG_ADC_DATA            0x080

#define REG_VERSION             0x200

#define REG_SET                 0x4
#define REG_CLR                 0x8
#define REG_TOG                 0xc

#define CTRL_RUN                (1U << 0)
#define CTRL_FIFO_ERROR_IRQ_EN  (1U << 1)
#define CTRL_FIFO_OVERFLOW_IRQ  (1U << 2)
#define CTRL_FIFO_UNDERFLOW_IRQ (1U << 3)
#define CTRL_LOOPBACK           (1U << 4)
#define CTRL_WORD_LENGTH        (1U << (5))   /* ADC: 16-bit when set */
#define CTRL_DAC_WORD_LENGTH    (1U << 6)     /* DAC: 16-bit when set */
#define CTRL_CLKGATE            (1U << 30)
#define CTRL_SFTRST             (1U << 31)
#define CTRL_IRQ_STATUS_BITS    (CTRL_FIFO_UNDERFLOW_IRQ | CTRL_FIFO_OVERFLOW_IRQ)

#define DAC_CTRL_WRITABLE_MASK   0xc01f773fU
#define DAC_CTRL_RESET           0xc0000000U
#define ADC_CTRL_WRITABLE_MASK   0xc01f07ffU
#define ADC_CTRL_RESET           0xc00000c0U

#define SRR_WRITABLE_MASK        0xf71f1fffU
#define SRR_RESET                0x10110037U

#define DAC_VOLUME_WRITABLE_MASK 0x03ff01ffU
#define DAC_VOLUME_RESET         0x01fe01feU
#define DAC_DEBUG_WRITABLE_MASK  0x80000f00U
#define DAC_HPVOL_WRITABLE_MASK  0x03017f7fU
#define DAC_HPVOL_RESET          0x01000c0cU
#define DAC_PWRDN_WRITABLE_MASK  0x01111111U
#define DAC_PWRDN_RESET          0x01001111U
#define DAC_REFCTRL_WRITABLE_MASK 0x07ff7ff7U
#define DAC_ANACTRL_WRITABLE_MASK 0x11367730U
#define DAC_TEST_WRITABLE_MASK   0x77f03007U
#define DAC_BISTCTRL_WRITABLE_MASK 0x00000001U
#define DAC_BISTCTRL_DONE        (1U << 1)
#define DAC_BISTCTRL_PASS        (1U << 2)
#define DAC_ANACLK_WRITABLE_MASK 0x80000017U
#define DAC_ANACLK_RESET         0x80000000U
#define DAC_LINEOUT_WRITABLE_MASK 0x03ffff1fU
#define DAC_LINEOUT_RESET        0x01404808U

#define ADC_VOLUME_WRITABLE_MASK 0x02ff00ffU
#define ADC_VOLUME_RESET         0x00fe00feU
#define ADC_DEBUG_WRITABLE_MASK  0x80000000U
#define ADC_ADVOL_WRITABLE_MASK  0x03003f3fU
#define ADC_ADVOL_RESET          0x01000000U
#define ADC_MICLINE_WRITABLE_MASK 0x21370033U
#define ADC_ANACLK_WRITABLE_MASK 0x80000077U
#define ADC_ANACLK_RESET         0x80000040U

#define STAT_PRESENT            (1U << 31)

#define SAMPLE_RATE             44100
#define SAMPLE_FORMAT           AUDIO_FORMAT_S16
#define SAMPLE_CHANNELS         2

static uint32_t audio_apply_sct(uint32_t old, uint32_t value, uint32_t mask,
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

/*
 * Sample-rate conversion (PDF Tables 975/995):
 * rate = 6 MHz * BASEMULT / ((SRC_INT.SRC_FRAC) * 8 * (SRC_HOLD + 1)).
 */
static uint64_t audio_frame_period_ns(uint32_t srr)
{
    uint32_t basemult = (srr >> 28) & 7;
    uint32_t hold = (srr >> 24) & 7;
    uint32_t src_int = (srr >> 16) & 0x1f;
    uint32_t src_frac = srr & 0x1fff;
    uint64_t divisor_q13;
    uint64_t denom;

    if (!basemult) {
        basemult = 1;
    }
    divisor_q13 = (((uint64_t)src_int << 13) | src_frac) * 8 * (hold + 1);
    if (!divisor_q13) {
        divisor_q13 = ((17ULL << 13) | 0x37) * 8;
    }
    denom = 6000000ULL * basemult * 8192;
    return (divisor_q13 * NANOSECONDS_PER_SECOND + denom / 2) / denom;
}

/* ======================================================================== */
/* Audio DAC (AUDIOOUT)                                                     */
/* ======================================================================== */

static uint32_t audio_dac_frame_words(const STMP3770AudioDACState *s)
{
    /* One output frame holds one left and one right sample. */
    return (s->ctrl0 & CTRL_DAC_WORD_LENGTH) ? 1 : 2;
}

static bool audio_dac_gated(const STMP3770AudioDACState *s)
{
    return (s->ctrl0 & (CTRL_SFTRST | CTRL_CLKGATE)) != 0;
}

static void audio_dac_update_irq(STMP3770AudioDACState *s)
{
    qemu_set_irq(s->irq,
                 (s->ctrl0 & CTRL_FIFO_ERROR_IRQ_EN) &&
                 (s->ctrl0 & CTRL_IRQ_STATUS_BITS));
}

static void audio_dac_update_timer(STMP3770AudioDACState *s)
{
    if (!s->frame_timer || !(s->ctrl0 & CTRL_RUN) || audio_dac_gated(s)) {
        if (s->frame_timer) {
            timer_del(s->frame_timer);
        }
        return;
    }
    timer_mod(s->frame_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              audio_frame_period_ns(s->srr));
}

static void audio_dac_frame_tick(void *opaque)
{
    STMP3770AudioDACState *s = opaque;
    uint32_t frame = audio_dac_frame_words(s);

    if (!(s->ctrl0 & CTRL_RUN) || audio_dac_gated(s)) {
        return;
    }
    if (s->fifo_count >= frame) {
        uint8_t buf[8];
        uint32_t bytes = frame * 4;
        uint32_t i;

        for (i = 0; i < frame; i++) {
            buf[4 * i + 0] = s->fifo[i] & 0xff;
            buf[4 * i + 1] = (s->fifo[i] >> 8) & 0xff;
            buf[4 * i + 2] = (s->fifo[i] >> 16) & 0xff;
            buf[4 * i + 3] = (s->fifo[i] >> 24) & 0xff;
        }
        if (s->voice) {
            AUD_write(s->voice, buf, bytes);
        }
        s->fifo_count -= frame;
        memmove(s->fifo, s->fifo + frame,
                s->fifo_count * sizeof(uint32_t));
        s->dma_preq = !s->dma_preq;
    } else {
        s->ctrl0 |= CTRL_FIFO_UNDERFLOW_IRQ;
    }
    audio_dac_update_irq(s);
    audio_dac_update_timer(s);
}

static void audio_dac_fifo_push(STMP3770AudioDACState *s, uint32_t value)
{
    if (audio_dac_gated(s)) {
        return;
    }
    if (s->fifo_count >= STMP3770_AUDIO_FIFO_WORDS) {
        s->ctrl0 |= CTRL_FIFO_OVERFLOW_IRQ;
        audio_dac_update_irq(s);
        return;
    }
    s->fifo[s->fifo_count++] = value;
}

static void audio_dac_reset_digital(STMP3770AudioDACState *s)
{
    s->ctrl0 = DAC_CTRL_RESET;
    s->srr = SRR_RESET;
    s->volume = DAC_VOLUME_RESET;
    s->debug = 0;
    s->bistctrl = 0;
    s->fifo_count = 0;
    s->dma_preq = false;
    if (s->voice) {
        AUD_set_active_out(s->voice, false);
    }
    audio_dac_update_irq(s);
    audio_dac_update_timer(s);
}

static void audio_dac_reset_all(STMP3770AudioDACState *s)
{
    audio_dac_reset_digital(s);
    /* Analog configuration registers reset on POR only (PDF Table 991). */
    s->hpvol = DAC_HPVOL_RESET;
    s->pwrdn = DAC_PWRDN_RESET;
    s->refctrl = 0;
    s->anactrl = 0;
    s->test = 0;
    s->anaclk = DAC_ANACLK_RESET;
    s->lineout = DAC_LINEOUT_RESET;
}

static uint64_t audio_dac_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770AudioDACState *s = STMP3770_AUDIO_DAC(opaque);
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-audio-dac: unsupported read size %u\n", size);
        return 0;
    }
    if (modifier && base != REG_VERSION) {
        /* SCT aliases read as zero. */
        return 0;
    }

    switch (base) {
    case REG_CTRL:
        return s->ctrl0;
    case REG_STAT:
        return STAT_PRESENT;
    case REG_SRR:
        return s->srr;
    case REG_VOLUME:
        return s->volume;
    case REG_DEBUG:
        return (s->debug & DAC_DEBUG_WRITABLE_MASK) |
               (s->dma_preq ? 2 : 0) |
               (s->fifo_count < STMP3770_AUDIO_FIFO_WORDS ? 1 : 0);
    case REG_DAC_HPVOL:
        return s->hpvol;
    case REG_DAC_RESERVED:
        return 0;
    case REG_DAC_PWRDN:
        return s->pwrdn;
    case REG_DAC_REFCTRL:
        return s->refctrl;
    case REG_DAC_ANACTRL:
        return s->anactrl;
    case REG_DAC_TEST:
        return s->test;
    case REG_DAC_BISTCTRL:
        return s->bistctrl;
    case REG_DAC_BISTSTAT0:
    case REG_DAC_BISTSTAT1:
        return 0;
    case REG_DAC_ANACLKCTRL:
        return s->anaclk;
    case REG_DAC_DATA:
        return 0;
    case REG_DAC_LINEOUTCTRL:
        return s->lineout;
    case REG_VERSION:
        if (modifier) {
            break;
        }
        return AUDIO_VERSION;
    default:
        break;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "stmp3770-audio-dac: read from offset 0x%" HWADDR_PRIx "\n",
                  offset);
    return 0;
}

static void audio_dac_write(void *opaque, hwaddr offset, uint64_t value,
                            unsigned size)
{
    STMP3770AudioDACState *s = STMP3770_AUDIO_DAC(opaque);
    uint32_t val = value;
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    uint32_t old_ctrl;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-audio-dac: unsupported write size %u\n", size);
        return;
    }

    switch (base) {
    case REG_CTRL:
        old_ctrl = s->ctrl0;
        s->ctrl0 = audio_apply_sct(s->ctrl0, val, DAC_CTRL_WRITABLE_MASK,
                                   modifier);
        /* FIFO error status bits are W1C via the SCT clear alias only. */
        if (modifier == 0 || modifier == REG_TOG) {
            s->ctrl0 = (s->ctrl0 & ~CTRL_IRQ_STATUS_BITS) |
                       (old_ctrl & CTRL_IRQ_STATUS_BITS);
        }
        if (s->ctrl0 & CTRL_SFTRST) {
            audio_dac_reset_digital(s);
            return;
        }
        if ((old_ctrl & CTRL_RUN) && !(s->ctrl0 & CTRL_RUN)) {
            /* PDF Table 991: clearing RUN also sets CLKGATE. */
            s->ctrl0 |= CTRL_CLKGATE;
        }
        if (s->voice) {
            AUD_set_active_out(s->voice,
                               (s->ctrl0 & CTRL_RUN) && !audio_dac_gated(s));
        }
        audio_dac_update_irq(s);
        audio_dac_update_timer(s);
        return;
    case REG_STAT:
    case REG_DAC_RESERVED:
    case REG_DAC_BISTSTAT0:
    case REG_DAC_BISTSTAT1:
    case REG_VERSION:
        /* Read-only registers; writes are ignored. */
        return;
    case REG_SRR:
        s->srr = audio_apply_sct(s->srr, val, SRR_WRITABLE_MASK, modifier);
        audio_dac_update_timer(s);
        return;
    case REG_VOLUME:
        s->volume = audio_apply_sct(s->volume, val,
                                    DAC_VOLUME_WRITABLE_MASK, modifier);
        return;
    case REG_DEBUG:
        s->debug = audio_apply_sct(s->debug, val, DAC_DEBUG_WRITABLE_MASK,
                                   modifier);
        return;
    case REG_DAC_HPVOL:
        s->hpvol = audio_apply_sct(s->hpvol, val, DAC_HPVOL_WRITABLE_MASK,
                                   modifier);
        return;
    case REG_DAC_PWRDN:
        s->pwrdn = audio_apply_sct(s->pwrdn, val, DAC_PWRDN_WRITABLE_MASK,
                                   modifier);
        return;
    case REG_DAC_REFCTRL:
        s->refctrl = audio_apply_sct(s->refctrl, val,
                                     DAC_REFCTRL_WRITABLE_MASK, modifier);
        return;
    case REG_DAC_ANACTRL:
        s->anactrl = audio_apply_sct(s->anactrl, val,
                                     DAC_ANACTRL_WRITABLE_MASK, modifier);
        return;
    case REG_DAC_TEST:
        s->test = audio_apply_sct(s->test, val, DAC_TEST_WRITABLE_MASK,
                                  modifier);
        return;
    case REG_DAC_BISTCTRL:
        s->bistctrl = audio_apply_sct(s->bistctrl, val,
                                      DAC_BISTCTRL_WRITABLE_MASK, modifier);
        if (s->bistctrl & 1) {
            /* Modeled BIST run completes instantly with a pass. */
            s->bistctrl = DAC_BISTCTRL_DONE | DAC_BISTCTRL_PASS;
        }
        return;
    case REG_DAC_ANACLKCTRL:
        s->anaclk = audio_apply_sct(s->anaclk, val,
                                    DAC_ANACLK_WRITABLE_MASK, modifier);
        return;
    case REG_DAC_DATA:
        /* Every address in the DATA window pushes one FIFO word. */
        audio_dac_fifo_push(s, val);
        return;
    case REG_DAC_LINEOUTCTRL:
        s->lineout = audio_apply_sct(s->lineout, val,
                                     DAC_LINEOUT_WRITABLE_MASK, modifier);
        return;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-audio-dac: write to offset 0x%" HWADDR_PRIx
                      "\n", offset);
        return;
    }
}

static const MemoryRegionOps audio_dac_ops = {
    .read = audio_dac_read,
    .write = audio_dac_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static int stmp3770_audio_dac_dma_handler(STMP3770DMAState *dma,
                                          int channel, STMP3770DMAEvent event,
                                          void *buf, size_t len, void *opaque)
{
    STMP3770AudioDACState *s = STMP3770_AUDIO_DAC(opaque);
    uint32_t *pio = (uint32_t *)buf;
    size_t i;

    if (event == STMP3770_DMA_EVENT_PIO) {
        if (len >= sizeof(uint32_t)) {
            audio_dac_write(s, REG_CTRL, pio[0], 4);
        }
        return (int)len;
    }
    if (event == STMP3770_DMA_EVENT_DATA_WRITE) {
        for (i = 0; i + 4 <= len; i += 4) {
            audio_dac_fifo_push(s, pio[i / 4]);
        }
        return (int)i;
    }
    return 0;
}

void stmp3770_audio_dac_set_dma(STMP3770AudioDACState *s,
                                STMP3770DMAState *dma, int channel)
{
    if (!dma) {
        return;
    }
    stmp3770_dma_set_channel_handler(dma, channel,
                                     stmp3770_audio_dac_dma_handler, s);
}

static void audio_dac_reset(DeviceState *dev)
{
    audio_dac_reset_all(STMP3770_AUDIO_DAC(dev));
}

static void audio_dac_realize(DeviceState *dev, Error **errp)
{
    STMP3770AudioDACState *s = STMP3770_AUDIO_DAC(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);
    struct audsettings as = {
        .freq = SAMPLE_RATE,
        .nchannels = SAMPLE_CHANNELS,
        .fmt = SAMPLE_FORMAT,
        .endianness = 0,
    };

    memory_region_init_io(&s->iomem, OBJECT(dev), &audio_dac_ops, s,
                          TYPE_STMP3770_AUDIO_DAC, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
    s->frame_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, audio_dac_frame_tick, s);

    if (s->card.state && AUD_register_card(TYPE_STMP3770_AUDIO_DAC,
                                             &s->card, errp)) {
        s->voice = AUD_open_out(&s->card, NULL, "stmp3770-audio-dac", s,
                                 NULL, &as);
        if (!s->voice) {
            AUD_log(TYPE_STMP3770_AUDIO_DAC, "Could not open DAC voice\n");
        }
    }
}

static int audio_dac_post_load(void *opaque, int version_id)
{
    audio_dac_update_timer(STMP3770_AUDIO_DAC(opaque));
    return 0;
}

static const VMStateDescription vmstate_audio_dac = {
    .name = "stmp3770-audio-dac",
    .version_id = 2,
    .minimum_version_id = 1,
    .post_load = audio_dac_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl0, STMP3770AudioDACState),
        VMSTATE_UINT32_V(srr, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(volume, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(debug, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(hpvol, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(pwrdn, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(refctrl, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(anactrl, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(test, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(bistctrl, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(anaclk, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_V(lineout, STMP3770AudioDACState, 2),
        VMSTATE_UINT32_ARRAY_V(fifo, STMP3770AudioDACState,
                               STMP3770_AUDIO_FIFO_WORDS, 2),
        VMSTATE_UINT32_V(fifo_count, STMP3770AudioDACState, 2),
        VMSTATE_BOOL_V(dma_preq, STMP3770AudioDACState, 2),
        VMSTATE_END_OF_LIST()
    }
};

static void audio_dac_init(Object *obj)
{
    audio_dac_reset_all(STMP3770_AUDIO_DAC(obj));
}

static const Property audio_dac_properties[] = {
    DEFINE_AUDIO_PROPERTIES(STMP3770AudioDACState, card),
};

static void audio_dac_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = audio_dac_realize;
    device_class_set_legacy_reset(dc, audio_dac_reset);
    dc->vmsd = &vmstate_audio_dac;
    device_class_set_props(dc, audio_dac_properties);
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
}

static const TypeInfo audio_dac_type_info = {
    .name          = TYPE_STMP3770_AUDIO_DAC,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770AudioDACState),
    .instance_init = audio_dac_init,
    .class_init    = audio_dac_class_init,
};

/* ======================================================================== */
/* Audio ADC (AUDIOIN)                                                      */
/* ======================================================================== */

static uint32_t audio_adc_frame_words(const STMP3770AudioADCState *s)
{
    return (s->ctrl0 & CTRL_WORD_LENGTH) ? 1 : 2;
}

static bool audio_adc_gated(const STMP3770AudioADCState *s)
{
    return (s->ctrl0 & (CTRL_SFTRST | CTRL_CLKGATE)) != 0;
}

static void audio_adc_update_irq(STMP3770AudioADCState *s)
{
    qemu_set_irq(s->irq,
                 (s->ctrl0 & CTRL_FIFO_ERROR_IRQ_EN) &&
                 (s->ctrl0 & CTRL_IRQ_STATUS_BITS));
}

static void audio_adc_update_timer(STMP3770AudioADCState *s)
{
    if (!s->frame_timer || !(s->ctrl0 & CTRL_RUN) || audio_adc_gated(s)) {
        if (s->frame_timer) {
            timer_del(s->frame_timer);
        }
        return;
    }
    timer_mod(s->frame_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
              audio_frame_period_ns(s->srr));
}

static void audio_adc_frame_tick(void *opaque)
{
    STMP3770AudioADCState *s = opaque;
    uint32_t frame = audio_adc_frame_words(s);
    uint32_t i;

    if (!(s->ctrl0 & CTRL_RUN) || audio_adc_gated(s)) {
        return;
    }
    if (s->fifo_count + frame > STMP3770_AUDIO_FIFO_WORDS) {
        s->ctrl0 |= CTRL_FIFO_OVERFLOW_IRQ;
    } else {
        uint8_t buf[8] = { 0 };
        uint32_t bytes = frame * 4;

        if (s->voice) {
            AUD_read(s->voice, buf, bytes);
        }
        for (i = 0; i < frame; i++) {
            s->fifo[s->fifo_count++] = buf[4 * i] | (buf[4 * i + 1] << 8) |
                                       ((uint32_t)buf[4 * i + 2] << 16) |
                                       ((uint32_t)buf[4 * i + 3] << 24);
        }
        /* PDF: a DMA service request issues once 8 words are collected. */
        if (s->fifo_count == STMP3770_AUDIO_FIFO_WORDS) {
            s->dma_preq = !s->dma_preq;
        }
    }
    audio_adc_update_irq(s);
    audio_adc_update_timer(s);
}

static bool audio_adc_fifo_pop(STMP3770AudioADCState *s, uint32_t *value)
{
    if (audio_adc_gated(s) || s->fifo_count == 0) {
        s->ctrl0 |= CTRL_FIFO_UNDERFLOW_IRQ;
        audio_adc_update_irq(s);
        return false;
    }
    *value = s->fifo[0];
    s->fifo_count--;
    memmove(s->fifo, s->fifo + 1, s->fifo_count * sizeof(uint32_t));
    return true;
}

static void audio_adc_reset_digital(STMP3770AudioADCState *s)
{
    s->ctrl0 = ADC_CTRL_RESET;
    s->srr = SRR_RESET;
    s->volume = ADC_VOLUME_RESET;
    s->debug = 0;
    s->fifo_count = 0;
    s->dma_preq = false;
    if (s->voice) {
        AUD_set_active_in(s->voice, false);
    }
    audio_adc_update_irq(s);
    audio_adc_update_timer(s);
}

static void audio_adc_reset_all(STMP3770AudioADCState *s)
{
    audio_adc_reset_digital(s);
    /* Analog configuration registers reset on POR only. */
    s->advol = ADC_ADVOL_RESET;
    s->micline = 0;
    s->anaclk = ADC_ANACLK_RESET;
}

static uint64_t audio_adc_read(void *opaque, hwaddr offset, unsigned size)
{
    STMP3770AudioADCState *s = STMP3770_AUDIO_ADC(opaque);
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    uint32_t value;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-audio-adc: unsupported read size %u\n", size);
        return 0;
    }
    if (modifier && base != REG_VERSION) {
        /* SCT aliases read as zero. */
        return 0;
    }

    switch (base) {
    case REG_CTRL:
        return s->ctrl0;
    case REG_STAT:
        return STAT_PRESENT;
    case REG_SRR:
        return s->srr;
    case REG_VOLUME:
        return s->volume;
    case REG_DEBUG:
        return (s->debug & ADC_DEBUG_WRITABLE_MASK) |
               (s->dma_preq ? 2 : 0) | (s->fifo_count ? 1 : 0);
    case REG_ADC_ADVOL:
        return s->advol;
    case REG_ADC_MICLINE:
        return s->micline;
    case REG_ADC_ANACLKCTRL:
        return s->anaclk;
    case REG_ADC_DATA:
        if (audio_adc_fifo_pop(s, &value)) {
            return value;
        }
        return 0;
    case REG_VERSION:
        if (modifier) {
            break;
        }
        return AUDIO_VERSION;
    default:
        break;
    }
    qemu_log_mask(LOG_GUEST_ERROR,
                  "stmp3770-audio-adc: read from offset 0x%" HWADDR_PRIx "\n",
                  offset);
    return 0;
}

static void audio_adc_write(void *opaque, hwaddr offset, uint64_t value,
                            unsigned size)
{
    STMP3770AudioADCState *s = STMP3770_AUDIO_ADC(opaque);
    uint32_t val = value;
    hwaddr base = offset & ~0xfULL;
    unsigned int modifier = offset & 0xf;
    uint32_t old_ctrl;

    if (size != 4) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-audio-adc: unsupported write size %u\n", size);
        return;
    }

    switch (base) {
    case REG_CTRL:
        old_ctrl = s->ctrl0;
        s->ctrl0 = audio_apply_sct(s->ctrl0, val, ADC_CTRL_WRITABLE_MASK,
                                   modifier);
        /* FIFO error status bits are W1C via the SCT clear alias only. */
        if (modifier == 0 || modifier == REG_TOG) {
            s->ctrl0 = (s->ctrl0 & ~CTRL_IRQ_STATUS_BITS) |
                       (old_ctrl & CTRL_IRQ_STATUS_BITS);
        }
        if (s->ctrl0 & CTRL_SFTRST) {
            audio_adc_reset_digital(s);
            return;
        }
        if ((old_ctrl & CTRL_RUN) && !(s->ctrl0 & CTRL_RUN)) {
            /* PDF Table 971: clearing RUN also sets CLKGATE. */
            s->ctrl0 |= CTRL_CLKGATE;
        }
        if (s->voice) {
            AUD_set_active_in(s->voice,
                              (s->ctrl0 & CTRL_RUN) && !audio_adc_gated(s));
        }
        audio_adc_update_irq(s);
        audio_adc_update_timer(s);
        return;
    case REG_STAT:
    case REG_ADC_DATA:
    case REG_VERSION:
        /* Read-only registers; writes are ignored. */
        return;
    case REG_SRR:
        s->srr = audio_apply_sct(s->srr, val, SRR_WRITABLE_MASK, modifier);
        audio_adc_update_timer(s);
        return;
    case REG_VOLUME:
        s->volume = audio_apply_sct(s->volume, val,
                                    ADC_VOLUME_WRITABLE_MASK, modifier);
        return;
    case REG_DEBUG:
        s->debug = audio_apply_sct(s->debug, val, ADC_DEBUG_WRITABLE_MASK,
                                   modifier);
        return;
    case REG_ADC_ADVOL:
        s->advol = audio_apply_sct(s->advol, val, ADC_ADVOL_WRITABLE_MASK,
                                   modifier);
        return;
    case REG_ADC_MICLINE:
        s->micline = audio_apply_sct(s->micline, val,
                                     ADC_MICLINE_WRITABLE_MASK, modifier);
        return;
    case REG_ADC_ANACLKCTRL:
        s->anaclk = audio_apply_sct(s->anaclk, val,
                                    ADC_ANACLK_WRITABLE_MASK, modifier);
        return;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-audio-adc: write to offset 0x%" HWADDR_PRIx
                      "\n", offset);
        return;
    }
}

static const MemoryRegionOps audio_adc_ops = {
    .read = audio_adc_read,
    .write = audio_adc_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static int stmp3770_audio_adc_dma_handler(STMP3770DMAState *dma,
                                          int channel, STMP3770DMAEvent event,
                                          void *buf, size_t len, void *opaque)
{
    STMP3770AudioADCState *s = STMP3770_AUDIO_ADC(opaque);
    uint32_t *pio = (uint32_t *)buf;
    size_t i;
    uint32_t word;

    if (event == STMP3770_DMA_EVENT_PIO) {
        if (len >= sizeof(uint32_t)) {
            audio_adc_write(s, REG_CTRL, pio[0], 4);
        }
        return (int)len;
    }
    if (event == STMP3770_DMA_EVENT_DATA_READ) {
        uint8_t *dst = (uint8_t *)buf;

        for (i = 0; i + 4 <= len; i += 4) {
            if (!audio_adc_fifo_pop(s, &word)) {
                break;
            }
            dst[i + 0] = word & 0xff;
            dst[i + 1] = (word >> 8) & 0xff;
            dst[i + 2] = (word >> 16) & 0xff;
            dst[i + 3] = (word >> 24) & 0xff;
        }
        return (int)i;
    }
    return 0;
}

void stmp3770_audio_adc_set_dma(STMP3770AudioADCState *s,
                                STMP3770DMAState *dma, int channel)
{
    if (!dma) {
        return;
    }
    stmp3770_dma_set_channel_handler(dma, channel,
                                     stmp3770_audio_adc_dma_handler, s);
}

static void audio_adc_reset(DeviceState *dev)
{
    audio_adc_reset_all(STMP3770_AUDIO_ADC(dev));
}

static void audio_adc_realize(DeviceState *dev, Error **errp)
{
    STMP3770AudioADCState *s = STMP3770_AUDIO_ADC(dev);
    SysBusDevice *sbd = SYS_BUS_DEVICE(dev);
    struct audsettings as = {
        .freq = SAMPLE_RATE,
        .nchannels = SAMPLE_CHANNELS,
        .fmt = SAMPLE_FORMAT,
        .endianness = 0,
    };

    memory_region_init_io(&s->iomem, OBJECT(dev), &audio_adc_ops, s,
                          TYPE_STMP3770_AUDIO_ADC, 0x2000);
    sysbus_init_mmio(sbd, &s->iomem);
    sysbus_init_irq(sbd, &s->irq);
    s->frame_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, audio_adc_frame_tick, s);

    if (s->card.state && AUD_register_card(TYPE_STMP3770_AUDIO_ADC,
                                             &s->card, errp)) {
        s->voice = AUD_open_in(&s->card, NULL, "stmp3770-audio-adc", s,
                                NULL, &as);
        if (!s->voice) {
            AUD_log(TYPE_STMP3770_AUDIO_ADC, "Could not open ADC voice\n");
        }
    }
}

static int audio_adc_post_load(void *opaque, int version_id)
{
    audio_adc_update_timer(STMP3770_AUDIO_ADC(opaque));
    return 0;
}

static const VMStateDescription vmstate_audio_adc = {
    .name = "stmp3770-audio-adc",
    .version_id = 2,
    .minimum_version_id = 1,
    .post_load = audio_adc_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(ctrl0, STMP3770AudioADCState),
        VMSTATE_UINT32_V(srr, STMP3770AudioADCState, 2),
        VMSTATE_UINT32_V(volume, STMP3770AudioADCState, 2),
        VMSTATE_UINT32_V(debug, STMP3770AudioADCState, 2),
        VMSTATE_UINT32_V(advol, STMP3770AudioADCState, 2),
        VMSTATE_UINT32_V(micline, STMP3770AudioADCState, 2),
        VMSTATE_UINT32_V(anaclk, STMP3770AudioADCState, 2),
        VMSTATE_UINT32_ARRAY_V(fifo, STMP3770AudioADCState,
                               STMP3770_AUDIO_FIFO_WORDS, 2),
        VMSTATE_UINT32_V(fifo_count, STMP3770AudioADCState, 2),
        VMSTATE_BOOL_V(dma_preq, STMP3770AudioADCState, 2),
        VMSTATE_END_OF_LIST()
    }
};

static void audio_adc_init(Object *obj)
{
    audio_adc_reset_all(STMP3770_AUDIO_ADC(obj));
}

static const Property audio_adc_properties[] = {
    DEFINE_AUDIO_PROPERTIES(STMP3770AudioADCState, card),
};

static void audio_adc_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = audio_adc_realize;
    device_class_set_legacy_reset(dc, audio_adc_reset);
    dc->vmsd = &vmstate_audio_adc;
    device_class_set_props(dc, audio_adc_properties);
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
}

static const TypeInfo audio_adc_type_info = {
    .name          = TYPE_STMP3770_AUDIO_ADC,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(STMP3770AudioADCState),
    .instance_init = audio_adc_init,
    .class_init    = audio_adc_class_init,
};

static void stmp3770_audio_register_types(void)
{
    type_register_static(&audio_dac_type_info);
    type_register_static(&audio_adc_type_info);
}

type_init(stmp3770_audio_register_types)
