/*
 * STMP3770 Audio DAC/ADC emulation
 *
 * Based on STMP3770 Reference Manual Chapters 25 (AUDIOOUT/DAC) and
 * 24 (AUDIOIN/ADC)
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef STMP3770_AUDIO_H
#define STMP3770_AUDIO_H

#include "hw/sysbus.h"
#include "audio/audio.h"
#include "hw/dma/stmp3770_dma.h"
#include "qemu/timer.h"

#define TYPE_STMP3770_AUDIO_DAC "stmp3770-audio-dac"
#define TYPE_STMP3770_AUDIO_ADC "stmp3770-audio-adc"

OBJECT_DECLARE_SIMPLE_TYPE(STMP3770AudioDACState, STMP3770_AUDIO_DAC)
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770AudioADCState, STMP3770_AUDIO_ADC)

#define STMP3770_AUDIO_FIFO_WORDS 8

struct STMP3770AudioDACState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    QEMUSoundCard card;
    SWVoiceOut *voice;
    qemu_irq irq;
    QEMUTimer *frame_timer;

    uint32_t ctrl0;
    uint32_t srr;
    uint32_t volume;
    uint32_t debug;
    uint32_t hpvol;
    uint32_t pwrdn;
    uint32_t refctrl;
    uint32_t anactrl;
    uint32_t test;
    uint32_t bistctrl;
    uint32_t anaclk;
    uint32_t lineout;
    uint32_t fifo[STMP3770_AUDIO_FIFO_WORDS];
    uint32_t fifo_count;
    bool dma_preq;
};

struct STMP3770AudioADCState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    QEMUSoundCard card;
    SWVoiceIn *voice;
    qemu_irq irq;
    QEMUTimer *frame_timer;

    uint32_t ctrl0;
    uint32_t srr;
    uint32_t volume;
    uint32_t debug;
    uint32_t advol;
    uint32_t micline;
    uint32_t anaclk;
    uint32_t fifo[STMP3770_AUDIO_FIFO_WORDS];
    uint32_t fifo_count;
    bool dma_preq;
};

void stmp3770_audio_dac_set_dma(STMP3770AudioDACState *s,
                                STMP3770DMAState *dma, int channel);
void stmp3770_audio_adc_set_dma(STMP3770AudioADCState *s,
                                STMP3770DMAState *dma, int channel);

#endif /* STMP3770_AUDIO_H */
