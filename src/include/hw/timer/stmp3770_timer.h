/*
 * STMP3770 Timers and Rotary Decoder (TIMROT)
 *
 * Based on STMP3770 Reference Manual Chapter 18
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef STMP3770_TIMER_H
#define STMP3770_TIMER_H

#include "hw/sysbus.h"
#include "hw/ptimer.h"

#define TYPE_STMP3770_TIMER "stmp3770-timer"
OBJECT_DECLARE_SIMPLE_TYPE(STMP3770TimerState, STMP3770_TIMER)

#define STMP3770_NUM_TIMERS 4
#define STMP3770_TIMER_NUM_PWM_INPUTS 5

typedef struct STMP3770TimerChannel {
    uint32_t timctrl;
    uint32_t fixed_count;
    ptimer_state *ptimer;
    bool running;
} STMP3770TimerChannel;

typedef struct STMP3770TimerCBInfo {
    STMP3770TimerState *s;
    int idx;
} STMP3770TimerCBInfo;

struct STMP3770TimerState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;
    qemu_irq irq[STMP3770_NUM_TIMERS];

    /* Rotary decoder */
    uint32_t rotctrl;
    uint32_t rotcount;
    uint8_t pwm_input[STMP3770_TIMER_NUM_PWM_INPUTS];
    uint16_t duty_running_count;
    uint16_t duty_low_count;
    uint16_t duty_high_count;
    bool duty_have_high;
    bool test_signal_level;
    bool test_signal_seen;

    /* Per-timer state */
    STMP3770TimerChannel timer[STMP3770_NUM_TIMERS];

    STMP3770TimerCBInfo cb_info[STMP3770_NUM_TIMERS];

    uint32_t version;
};

void stmp3770_timer_set_pwm_input(STMP3770TimerState *s,
                                  unsigned int channel, bool level);

#endif /* STMP3770_TIMER_H */
