/*
 * STMP3770 DMA controllers (APBH + APBX)
 *
 * Based on STMP3770 Reference Manual Chapters 11 and 12
 *
 * Copyright (C) 2024
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 */

#ifndef STMP3770_DMA_H
#define STMP3770_DMA_H

#include "hw/sysbus.h"

#define TYPE_STMP3770_DMA        "stmp3770-dma"
#define TYPE_STMP3770_APBH_DMA   "stmp3770-apbh-dma"
#define TYPE_STMP3770_APBX_DMA   "stmp3770-apbx-dma"

#define STMP3770_DMA_NUM_CHANNELS 8

OBJECT_DECLARE_SIMPLE_TYPE(STMP3770DMAState, STMP3770_DMA)

struct STMP3770DMAState;

typedef enum {
    STMP3770_DMA_EVENT_PIO,
    STMP3770_DMA_EVENT_DATA_READ,   /* DMA reads data from peripheral into buf */
    STMP3770_DMA_EVENT_DATA_WRITE,  /* DMA writes data from buf to peripheral */
    STMP3770_DMA_EVENT_SENSE,       /* DMA samples the peripheral sense line */
} STMP3770DMAEvent;

/*
 * Channel callback.  Called when PIO words are loaded, and again when a
 * data transfer needs to be performed.  The handler should copy up to @len
 * bytes to/from @buf and return the number of bytes actually transferred.
 * For PIO events @buf points to the PIO words and @len is the number of
 * PIO words times four.
 */
typedef int (*STMP3770DMAHandler)(struct STMP3770DMAState *dma,
                                  int channel, STMP3770DMAEvent event,
                                  void *buf, size_t len, void *opaque);
typedef void (*STMP3770DMACompletionFn)(struct STMP3770DMAState *dma,
                                        int channel, void *opaque);

typedef struct STMP3770DMAChannelHandler {
    STMP3770DMAHandler handler;
    void *opaque;
    bool sense_capable;
} STMP3770DMAChannelHandler;

/*
 * Channel state.  Most fields mirror the channel registers visible to
 * software; the loaded_* fields hold the command structure that was
 * fetched from guest memory.
 */
typedef struct STMP3770DMAChannel {
    uint32_t curcmdar;
    uint32_t nxtcmdar;
    uint32_t cmd;
    uint32_t bar;
    uint32_t sema;
    uint32_t debug1;
    uint32_t debug2;

    /* Internal state */
    uint32_t loaded_nxtcmdar;
    uint32_t loaded_cmd;
    uint32_t loaded_bar;
    uint32_t pio_words[15];
    unsigned int num_pio_words;

    /*
     * WAIT4ENDCMD pending state.  wait4endcmd_pending is set when a command
     * with WAIT4ENDCMD has been loaded and the DMA is waiting for the
     * peripheral completion callback.  wait4endcmd_completion is set when
     * the completion callback arrives but the channel is not active (frozen,
     * clock-gated or reset) so the completion cannot be processed immediately.
     */
    bool wait4endcmd_pending;
    bool wait4endcmd_completion;

    /* Pre-allocated transfer buffer reused for this channel to avoid
     * a g_malloc0/g_free cycle on every DMA command.
     */
    uint8_t *xfer_buf;
    size_t xfer_buf_size;
} STMP3770DMAChannel;

struct STMP3770DMAState {
    SysBusDevice parent_obj;

    MemoryRegion iomem;

    qemu_irq irq[STMP3770_DMA_NUM_CHANNELS];

    uint32_t ctrl0;
    uint32_t ctrl1;
    uint32_t devsel;

    STMP3770DMAChannel ch[STMP3770_DMA_NUM_CHANNELS];

    /* Optional per-channel peripheral callbacks */
    STMP3770DMAChannelHandler ch_handler[STMP3770_DMA_NUM_CHANNELS];
    STMP3770DMACompletionFn completion_cb[STMP3770_DMA_NUM_CHANNELS];
    void *completion_opaque[STMP3770_DMA_NUM_CHANNELS];

    /* true for APBX, false for APBH */
    bool is_apbx;
};

/* Register a callback for a DMA channel (e.g. GPMI on APBH channels 4-7) */
void stmp3770_dma_set_channel_handler(STMP3770DMAState *s, int channel,
                                      STMP3770DMAHandler handler, void *opaque);
void stmp3770_dma_set_channel_sense_capable(STMP3770DMAState *s,
                                            int channel, bool capable);
void stmp3770_dma_set_channel_completion_callback(STMP3770DMAState *s,
                                                  int channel,
                                                  STMP3770DMACompletionFn cb,
                                                  void *opaque);
void stmp3770_dma_complete_channel_command(STMP3770DMAState *s, int channel);

#endif /* STMP3770_DMA_H */
