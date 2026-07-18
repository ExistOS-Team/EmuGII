/*
 * STMP3770 / HP 39gII profiling helpers
 *
 * Lightweight event counters and per-event wall-time accumulators.
 * Used for temporary performance investigation.
 */

#ifndef HW_STMP3770_PROFILE_H
#define HW_STMP3770_PROFILE_H

#include "qemu/atomic.h"
#include "qemu/timer.h"

struct MachineState;

typedef enum EmuProfileEvent {
    EMU_PROF_ICOLL_TICK,
    EMU_PROF_PWM_TICK,
    EMU_PROF_TIMROT_TICK,
    EMU_PROF_TIMROT_ROTARY,
    EMU_PROF_DMA_RUN,
    EMU_PROF_LCDIF_REFRESH,
    EMU_PROF_FP_RENDER,
    EMU_PROF_GPMI_WAIT,
    EMU_PROF_GPMI_TRANSFER,
    EMU_PROF_GPMI_DATA,
    EMU_PROF_PINCTRL_KEY,
    EMU_PROF_USB_FRINDEX,
    EMU_PROF_USB_GPTIMER,
    EMU_PROF_USB_OTG1MS,
    EMU_PROF_USB_PORTRESET,
    EMU_PROF_USB_IRQ,
    EMU_PROF_ARM_EXCEPTION,
    EMU_PROF_DATA_ABORT,
    EMU_PROF_PREFETCH_ABORT,
    EMU_PROF_EXCP_SVC,
    EMU_PROF_EXCP_IRQ,
    EMU_PROF_EXCP_FIQ,
    EMU_PROF_EXCP_UDEF,
    EMU_PROF_EXCP_BKPT,
    EMU_PROF_EXCP_OTHER,
    EMU_PROF_NUM_EVENTS,
} EmuProfileEvent;

extern uint64_t emu_profile_counts[EMU_PROF_NUM_EVENTS];
extern uint64_t emu_profile_times_ns[EMU_PROF_NUM_EVENTS];

#define EMU_SVC_HIST_SIZE 4096

typedef struct EmuSvcHistEntry {
    uint64_t count;
    uint32_t pc;
} EmuSvcHistEntry;

extern EmuSvcHistEntry emu_svc_histogram[EMU_SVC_HIST_SIZE];

#define EMU_PROF_INC(ev)        qatomic_inc(&emu_profile_counts[(ev)])
#define EMU_PROF_TIME_START()   qemu_clock_get_ns(QEMU_CLOCK_REALTIME)
#define EMU_PROF_TIME_END(ev, start)                                 \
    do {                                                            \
        int64_t _dt = qemu_clock_get_ns(QEMU_CLOCK_REALTIME) - (start); \
        qatomic_fetch_add(&emu_profile_times_ns[(ev)], _dt);        \
    } while (0)

void stmp3770_profile_init(MachineState *machine);

#endif /* HW_STMP3770_PROFILE_H */
