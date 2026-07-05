/*
 * STMP3770 Audio DAC/ADC emulation
 *
 * Based on STMP3770 Reference Manual Chapters 16 (DAC) and 17 (ADC)
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

#ifndef STMP3770_AUDIO_H
#define STMP3770_AUDIO_H

#include "hw/sysbus.h"
#include "audio/audio.h"
#include "hw/dma/stmp3770_dma.h"

#define TYPE_STMP3770_AUDIO_DAC "stmp3770-audio-dac"
#define TYPE_STMP3770_AUDIO_ADC "stmp3770-audio-adc"

OBJECT_DECLARE_SIMPLE_TYPE(STMP3770AudioDACState, STMP3770_AUDIO_DAC)
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770AudioADCState, STMP3770_AUDIO_ADC)

struct STMP3770AudioDACState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    QEMUSoundCard card;
    SWVoiceOut *voice;

    uint32_t ctrl0;
    qemu_irq irq;
};

struct STMP3770AudioADCState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    QEMUSoundCard card;
    SWVoiceIn *voice;

    uint32_t ctrl0;
    qemu_irq irq;
};

void stmp3770_audio_dac_set_dma(STMP3770AudioDACState *s,
                                STMP3770DMAState *dma, int channel);
void stmp3770_audio_adc_set_dma(STMP3770AudioADCState *s,
                                STMP3770DMAState *dma, int channel);

#endif /* STMP3770_AUDIO_H */
