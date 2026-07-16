/*
 * STMP3770 Data Co-Processor (DCP)
 *
 * Implements the documented control register file and the channel 0
 * work-packet engine: memory-copy, AES-128 (ECB/CBC, encrypt/decrypt),
 * SHA-1 and CRC-32 hashing. Blit and CSC execution are not modeled.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "crypto/aes.h"
#include "hw/irq.h"
#include "hw/misc/stmp3770_dcp.h"
#include "hw/misc/stmp3770_ocotp.h"
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

/*
 * Per-channel SCT alias availability per PDF Table 649 (address table):
 *
 *   CH0 STAT: SET + CLR (no TOG)    CH0 OPTS: SET + CLR (no TOG)
 *   CH1 STAT: SET + CLR (no TOG)    CH1 OPTS: SET + CLR + TOG
 *   CH2 STAT: SET + CLR + TOG       CH2 OPTS: SET + CLR + TOG
 *   CH3 STAT: SET + CLR + TOG       CH3 OPTS: SET + CLR + TOG
 *
 * CSCSTAT: SET only (no CLR, no TOG).
 */
static const bool dcp_ch_stat_has_tog[DCP_CHANNELS] = {
    false, false, true, true,
};
static const bool dcp_ch_opts_has_tog[DCP_CHANNELS] = {
    false, true, true, true,
};

#define CTRL_SFTRST                 (1U << 31)
#define CTRL_CLKGATE                (1U << 30)
#define CTRL_PRESENT_MASK           (3U << 28)
#define CTRL_GATHER_RESIDUAL        (1U << 23)
#define CTRL_CONTEXT_CACHING        (1U << 22)
#define CTRL_CONTEXT_SWITCHING      (1U << 21)
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
#define PACKET_CTRL_CHAIN_CONTIG    (1U << 3)
#define PACKET_CTRL_MEMCOPY         (1U << 4)
#define PACKET_CTRL_CIPHER          (1U << 5)
#define PACKET_CTRL_HASH            (1U << 6)
#define PACKET_CTRL_BLIT            (1U << 7)
#define PACKET_CTRL_CIPHER_ENCRYPT  (1U << 8)
#define PACKET_CTRL_CIPHER_INIT     (1U << 9)
#define PACKET_CTRL_OTP_KEY         (1U << 10)
#define PACKET_CTRL_PAYLOAD_KEY     (1U << 11)
#define PACKET_CTRL_HASH_INIT       (1U << 12)
#define PACKET_CTRL_HASH_TERM       (1U << 13)
#define PACKET_CTRL_CHECK_HASH      (1U << 14)
#define PACKET_CTRL_HASH_OUTPUT     (1U << 15)
#define PACKET_CTRL_CONSTANT_FILL   (1U << 16)
#define PACKET_CTRL_KEY_BYTESWAP    (1U << 18)
#define PACKET_CTRL_KEY_WORDSWAP    (1U << 19)
#define PACKET_CTRL_INPUT_BYTESWAP  (1U << 20)
#define PACKET_CTRL_INPUT_WORDSWAP  (1U << 21)
#define PACKET_CTRL_OUTPUT_BYTESWAP (1U << 22)
#define PACKET_CTRL_OUTPUT_WORDSWAP (1U << 23)

#define PACKET_CTRL1_CIPHER_SELECT(x)   ((x) & 0xf)
#define PACKET_CTRL1_CIPHER_MODE(x)     (((x) >> 4) & 0xf)
#define PACKET_CTRL1_KEY_SELECT(x)      (((x) >> 8) & 0xff)
#define PACKET_CTRL1_HASH_SELECT(x)     (((x) >> 16) & 0xf)

#define DCP_CIPHER_AES128       0
#define DCP_CIPHER_MODE_ECB     0
#define DCP_CIPHER_MODE_CBC     1
#define DCP_HASH_SHA1           0
#define DCP_HASH_CRC32          1

#define CH_ERROR_HASH_MISMATCH      (1U << 1)
#define CH_ERROR_SETUP              (1U << 2)
#define CH_ERROR_PACKET             (1U << 3)
#define CH_ERROR_SRC                (1U << 4)
#define CH_ERROR_DST                (1U << 5)
#define CH_STAT_ERROR_BITS          0x3eU
#define CH_ERROR_NEXT_CHAIN_ZERO    0x01U
#define CH_ERROR_NO_CHAIN           0x02U
#define CH_ERROR_CONTEXT            0x03U
#define CH_ERROR_PAYLOAD            0x04U
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

    /* Per-channel cipher (CBC chaining) and hash continuation contexts. */
    uint8_t ch_cipher_ctx[DCP_CHANNELS][16];
    uint32_t ch_sha_h[DCP_CHANNELS][5];
    uint32_t ch_crc[DCP_CHANNELS];
    uint32_t ch_hash_len[DCP_CHANNELS];
    uint8_t ch_hash_buf[DCP_CHANNELS][64];

    /* Arbiter/channel state: last granted channel and executing channel. */
    int32_t arb_last;
    int32_t last_channel;
    int32_t cur_channel;

    /* OTP controller providing the hardware key (NULL when unconnected). */
    STMP3770OCOTPState *ocotp;
};

void stmp3770_dcp_set_ocotp(STMP3770DCPState *s, STMP3770OCOTPState *ocotp)
{
    s->ocotp = ocotp;
}

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
    memset(s->ch_cipher_ctx, 0, sizeof(s->ch_cipher_ctx));
    memset(s->ch_sha_h, 0, sizeof(s->ch_sha_h));
    memset(s->ch_crc, 0, sizeof(s->ch_crc));
    memset(s->ch_hash_len, 0, sizeof(s->ch_hash_len));
    memset(s->ch_hash_buf, 0, sizeof(s->ch_hash_buf));
    s->arb_last = DCP_CHANNELS - 1;
    s->last_channel = -1;
    s->cur_channel = -1;
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

/*
 * A channel is schedulable while enabled, holding semaphore tokens and not
 * stalled on a latched error (PDF 15.3 CHnSTAT: processing stops until the
 * error is handled by software).
 */
static bool dcp_channel_ready(STMP3770DCPState *s, unsigned int ch)
{
    return !(s->ctrl & (CTRL_SFTRST | CTRL_CLKGATE)) &&
           (s->channelctrl & (1U << ch)) && s->ch_sema[ch] != 0 &&
           !(s->ch_stat[ch] & CH_STAT_ERROR_BITS);
}

/* Terminating error: the chain is aborted and the semaphore is consumed. */
static void dcp_channel_error(STMP3770DCPState *s, unsigned int ch,
                              uint32_t error_bit, uint32_t error_code)
{
    s->ch_stat[ch] = (s->ch_stat[ch] & 0xff000000U) |
                     ((error_code & 0xff) << 16) | error_bit;
    s->ch_sema[ch] = 0;
    s->stat |= 1U << ch;
    dcp_update_irq(s);
}

/*
 * Recoverable error (PDF: "the channel's processing stops until the error
 * is handled by software"): the semaphore is preserved so that the channel
 * resumes once software clears the CHnSTAT error bits.
 */
static void dcp_channel_stall(STMP3770DCPState *s, unsigned int ch,
                              uint32_t error_bit, uint32_t error_code)
{
    s->ch_stat[ch] = (s->ch_stat[ch] & 0xff000000U) |
                     ((error_code & 0xff) << 16) | error_bit;
    s->stat |= 1U << ch;
    dcp_update_irq(s);
}

static bool dcp_context_switching(STMP3770DCPState *s)
{
    return (s->ctrl & CTRL_CONTEXT_SWITCHING) && s->context != 0;
}

/* PDF 15.2 context buffer layout: channel N cipher at 0x78-0x28*N. */
static hwaddr dcp_context_cipher_addr(STMP3770DCPState *s, unsigned int ch)
{
    return (hwaddr)s->context + 0x78 - ch * 0x28;
}

static hwaddr dcp_context_hash_addr(STMP3770DCPState *s, unsigned int ch)
{
    return dcp_context_cipher_addr(s, ch) + 0x10;
}

/*
 * Save the channel's continuation context after a context-producing
 * packet (CBC cipher context and/or SHA-1 hash context, PDF: "the control
 * logic writes to the context buffer only if the function is being used").
 */
static bool dcp_context_save(STMP3770DCPState *s, unsigned int ch,
                             bool cbc, bool sha1)
{
    uint32_t buf[6];
    int i;

    if (!dcp_context_switching(s)) {
        return true;
    }
    if (cbc) {
        for (i = 0; i < 4; i++) {
            buf[i] = ldl_le_p(s->ch_cipher_ctx[ch] + 4 * i);
        }
        if (address_space_write(&address_space_memory,
                                dcp_context_cipher_addr(s, ch),
                                MEMTXATTRS_UNSPECIFIED, buf, 16) != MEMTX_OK) {
            return false;
        }
    }
    if (sha1) {
        for (i = 0; i < 5; i++) {
            buf[i] = cpu_to_le32(s->ch_sha_h[ch][i]);
        }
        /* 32-bit hash bit counter (PDF 15.1.1). */
        buf[5] = cpu_to_le32(s->ch_hash_len[ch] * 8);
        if (address_space_write(&address_space_memory,
                                dcp_context_hash_addr(s, ch),
                                MEMTXATTRS_UNSPECIFIED, buf, 24) != MEMTX_OK) {
            return false;
        }
    }
    return true;
}

/*
 * Restore continuation context when a channel resumes after another
 * channel has used the engine.  Per PDF, no reload occurs when the same
 * channel resumes without an intermediate operation from another channel.
 */
static bool dcp_context_load(STMP3770DCPState *s, unsigned int ch,
                             bool cbc, bool sha1)
{
    uint32_t buf[6];
    int i;

    if (!dcp_context_switching(s) || s->last_channel < 0 ||
        s->last_channel == (int32_t)ch) {
        return true;
    }
    if (cbc) {
        if (address_space_read(&address_space_memory,
                               dcp_context_cipher_addr(s, ch),
                               MEMTXATTRS_UNSPECIFIED, buf, 16) != MEMTX_OK) {
            return false;
        }
        for (i = 0; i < 4; i++) {
            stl_le_p(s->ch_cipher_ctx[ch] + 4 * i, buf[i]);
        }
    }
    if (sha1) {
        if (address_space_read(&address_space_memory,
                               dcp_context_hash_addr(s, ch),
                               MEMTXATTRS_UNSPECIFIED, buf, 24) != MEMTX_OK) {
            return false;
        }
        for (i = 0; i < 5; i++) {
            s->ch_sha_h[ch][i] = le32_to_cpu(buf[i]);
        }
        s->ch_hash_len[ch] = le32_to_cpu(buf[5]) / 8;
    }
    return true;
}

/*
 * Data/key byte ordering (PDF 15.2.2, Tables 668/670).
 *
 * The AES engine views each 128-bit quantity (data block or key) as the
 * big-endian serialization of the integer formed by four little-endian
 * 32-bit words w[0..3] (w[0] = lowest address, or key subword 0 which the
 * PDF defines as the least-significant key word):
 *
 *     engine byte (4 * j + c) = (w[3 - j] >> (24 - 8 * c)) & 0xff
 *
 * With no swap controls a byte stream stored in memory is therefore
 * processed fully reversed.  BYTESWAP applies bswap32() to each word and
 * WORDSWAP reverses the word order; setting both yields natural
 * byte-stream order ("big-endian data" per the PDF).  The payload CBC IV
 * follows the KEY swap controls.
 */
static void dcp_apply_swaps(uint32_t w[4], bool byteswap, bool wordswap)
{
    uint32_t t;
    int i;

    if (byteswap) {
        for (i = 0; i < 4; i++) {
            w[i] = bswap32(w[i]);
        }
    }
    if (wordswap) {
        t = w[0];
        w[0] = w[3];
        w[3] = t;
        t = w[1];
        w[1] = w[2];
        w[2] = t;
    }
}

static void dcp_words_to_block(uint8_t out[16], const uint32_t w[4])
{
    int j;
    int c;

    for (j = 0; j < 4; j++) {
        for (c = 0; c < 4; c++) {
            out[4 * j + c] = (w[3 - j] >> (24 - 8 * c)) & 0xff;
        }
    }
}

static void dcp_block_to_words(uint32_t w[4], const uint8_t in[16])
{
    int j;
    int c;

    for (j = 0; j < 4; j++) {
        uint32_t v = 0;

        for (c = 0; c < 4; c++) {
            v |= (uint32_t)in[4 * j + c] << (24 - 8 * c);
        }
        w[3 - j] = v;
    }
}

/* Compact SHA-1 (FIPS PUB 180-1) for the DCP hashing engine. */
static uint32_t dcp_sha1_rol(uint32_t v, int n)
{
    return (v << n) | (v >> (32 - n));
}

static void dcp_sha1_block(uint32_t h[5], const uint8_t *data)
{
    uint32_t w[80];
    uint32_t a;
    uint32_t b;
    uint32_t c;
    uint32_t d;
    uint32_t e;
    int i;

    for (i = 0; i < 16; i++) {
        w[i] = ldl_be_p(data + 4 * i);
    }
    for (i = 16; i < 80; i++) {
        w[i] = dcp_sha1_rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    }
    a = h[0];
    b = h[1];
    c = h[2];
    d = h[3];
    e = h[4];
    for (i = 0; i < 80; i++) {
        uint32_t f;
        uint32_t k;
        uint32_t tmp;

        if (i < 20) {
            f = (b & c) | (~b & d);
            k = 0x5a827999;
        } else if (i < 40) {
            f = b ^ c ^ d;
            k = 0x6ed9eba1;
        } else if (i < 60) {
            f = (b & c) | (b & d) | (c & d);
            k = 0x8f1bbcdc;
        } else {
            f = b ^ c ^ d;
            k = 0xca62c1d6;
        }
        tmp = dcp_sha1_rol(a, 5) + f + e + k + w[i];
        e = d;
        d = c;
        c = dcp_sha1_rol(b, 30);
        b = a;
        a = tmp;
    }
    h[0] += a;
    h[1] += b;
    h[2] += c;
    h[3] += d;
    h[4] += e;
}

static void dcp_sha1_init(STMP3770DCPState *s, unsigned int ch)
{
    s->ch_sha_h[ch][0] = 0x67452301;
    s->ch_sha_h[ch][1] = 0xefcdab89;
    s->ch_sha_h[ch][2] = 0x98badcfe;
    s->ch_sha_h[ch][3] = 0x10325476;
    s->ch_sha_h[ch][4] = 0xc3d2e1f0;
    s->ch_hash_len[ch] = 0;
}

static void dcp_sha1_update(STMP3770DCPState *s, unsigned int ch,
                            const uint8_t *data, uint32_t len)
{
    uint32_t buffered = s->ch_hash_len[ch] & 63;

    s->ch_hash_len[ch] += len;
    if (buffered) {
        uint32_t fill = MIN(64 - buffered, len);

        memcpy(s->ch_hash_buf[ch] + buffered, data, fill);
        data += fill;
        len -= fill;
        buffered += fill;
        if (buffered == 64) {
            dcp_sha1_block(s->ch_sha_h[ch], s->ch_hash_buf[ch]);
        }
    }
    while (len >= 64) {
        dcp_sha1_block(s->ch_sha_h[ch], data);
        data += 64;
        len -= 64;
    }
    if (len) {
        memcpy(s->ch_hash_buf[ch], data, len);
    }
}

static void dcp_sha1_final(STMP3770DCPState *s, unsigned int ch)
{
    /* PDF 15.1.1: hardware implements a 32-bit bit counter. */
    uint32_t bits = s->ch_hash_len[ch] * 8;
    uint32_t buffered = s->ch_hash_len[ch] & 63;
    uint8_t *buf = s->ch_hash_buf[ch];

    buf[buffered++] = 0x80;
    if (buffered > 56) {
        memset(buf + buffered, 0, 64 - buffered);
        dcp_sha1_block(s->ch_sha_h[ch], buf);
        buffered = 0;
    }
    memset(buf + buffered, 0, 56 - buffered);
    buf[56] = 0;
    buf[57] = 0;
    buf[58] = 0;
    buf[59] = 0;
    buf[60] = bits >> 24;
    buf[61] = bits >> 16;
    buf[62] = bits >> 8;
    buf[63] = bits;
    dcp_sha1_block(s->ch_sha_h[ch], buf);
}

/*
 * DCP CRC-32 (PDF 15.2.3): reflected Ethernet polynomial, initialized to
 * 0xffffffff, trailing bytes padded with zeros to a 32-bit boundary and
 * no post-pended length or final complement.
 */
static uint32_t dcp_crc32_byte(uint32_t crc, uint8_t byte)
{
    int i;

    crc ^= byte;
    for (i = 0; i < 8; i++) {
        crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320U : 0);
    }
    return crc;
}

static bool dcp_load_cipher_key(STMP3770DCPState *s, uint32_t ctrl0,
                                uint32_t ctrl1, hwaddr payload,
                                uint32_t *payload_off, AES_KEY *aes_key,
                                bool encrypt)
{
    uint32_t kw[4];
    uint8_t key_bytes[16];
    unsigned int sel = PACKET_CTRL1_KEY_SELECT(ctrl1);
    int i;

    if (ctrl0 & PACKET_CTRL_PAYLOAD_KEY) {
        uint32_t raw_key[4];

        /* PAYLOAD_KEY takes precedence over OTP_KEY (PDF Table 668). */
        if (address_space_read(&address_space_memory, payload,
                               MEMTXATTRS_UNSPECIFIED, raw_key,
                               sizeof(raw_key)) != MEMTX_OK) {
            return false;
        }
        for (i = 0; i < 4; i++) {
            kw[i] = le32_to_cpu(raw_key[i]);
        }
        *payload_off += 16;
    } else if (ctrl0 & PACKET_CTRL_OTP_KEY) {
        for (i = 0; i < 4; i++) {
            kw[i] = s->ocotp ? s->ocotp->crypto[i] : 0;
        }
    } else {
        for (i = 0; i < 4; i++) {
            kw[i] = s->key_data[sel & 3][i];
        }
    }
    dcp_apply_swaps(kw, ctrl0 & PACKET_CTRL_KEY_BYTESWAP,
                    ctrl0 & PACKET_CTRL_KEY_WORDSWAP);
    dcp_words_to_block(key_bytes, kw);
    if (encrypt) {
        AES_set_encrypt_key(key_bytes, 128, aes_key);
    } else {
        AES_set_decrypt_key(key_bytes, 128, aes_key);
    }
    return true;
}

static void dcp_cipher_block(uint32_t ctrl0, bool cbc, const AES_KEY *aes_key,
                             uint8_t prev[16], uint8_t data[16])
{
    bool encrypt = ctrl0 & PACKET_CTRL_CIPHER_ENCRYPT;
    uint32_t w[4];
    uint8_t block[16];
    int i;

    for (i = 0; i < 4; i++) {
        w[i] = ldl_le_p(data + 4 * i);
    }
    dcp_apply_swaps(w, ctrl0 & PACKET_CTRL_INPUT_BYTESWAP,
                    ctrl0 & PACKET_CTRL_INPUT_WORDSWAP);
    dcp_words_to_block(block, w);

    if (cbc) {
        if (encrypt) {
            for (i = 0; i < 16; i++) {
                block[i] ^= prev[i];
            }
            AES_encrypt(block, block, aes_key);
            memcpy(prev, block, 16);
        } else {
            uint8_t ct[16];

            memcpy(ct, block, 16);
            AES_decrypt(block, block, aes_key);
            for (i = 0; i < 16; i++) {
                block[i] ^= prev[i];
            }
            memcpy(prev, ct, 16);
        }
    } else if (encrypt) {
        AES_encrypt(block, block, aes_key);
    } else {
        AES_decrypt(block, block, aes_key);
    }

    dcp_block_to_words(w, block);
    dcp_apply_swaps(w, ctrl0 & PACKET_CTRL_OUTPUT_BYTESWAP,
                    ctrl0 & PACKET_CTRL_OUTPUT_WORDSWAP);
    for (i = 0; i < 4; i++) {
        stl_le_p(data + 4 * i, w[i]);
    }
}

static void dcp_hash_bytes(STMP3770DCPState *s, unsigned int ch, bool crc32,
                           const uint8_t *data, uint32_t len)
{
    uint32_t i;

    if (crc32) {
        uint32_t crc = s->ch_crc[ch];

        for (i = 0; i < len; i++) {
            crc = dcp_crc32_byte(crc, data[i]);
        }
        s->ch_crc[ch] = crc;
        s->ch_hash_len[ch] += len;
    } else {
        dcp_sha1_update(s, ch, data, len);
    }
}

static void dcp_process_packet(STMP3770DCPState *s, unsigned int ch)
{
    DCPWorkPacket raw;
    DCPWorkPacket packet;
    uint32_t tag;
    uint32_t remaining;
    uint32_t hash_todo;
    uint32_t hash_select;
    uint32_t payload_off = 0;
    hwaddr source;
    hwaddr destination;
    hwaddr packet_addr;
    bool memcopy;
    bool cipher;
    bool hash;
    bool blit;
    bool encrypt;
    bool cbc;
    bool crc32;
    bool hash_output;
    bool check_hash;
    AES_KEY aes_key;
    uint8_t prev[16];
    uint8_t buffer[4096];

    if (!dcp_channel_ready(s, ch)) {
        return;
    }

    packet_addr = s->ch_cmdptr[ch];
    if (address_space_read(&address_space_memory, packet_addr,
                           MEMTXATTRS_UNSPECIFIED, &raw, sizeof(raw)) !=
        MEMTX_OK) {
        dcp_channel_stall(s, ch, CH_ERROR_PACKET, 0);
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

    memcopy = packet.ctrl0 & PACKET_CTRL_MEMCOPY;
    cipher = packet.ctrl0 & PACKET_CTRL_CIPHER;
    hash = packet.ctrl0 & PACKET_CTRL_HASH;
    blit = packet.ctrl0 & PACKET_CTRL_BLIT;

    /* PDF Table 640: valid HASH/CIPHER/BLIT/MEMCOPY combinations. */
    if (blit || (cipher && memcopy)) {
        if (blit) {
            qemu_log_mask(LOG_UNIMP, "stmp3770-dcp: blit operation\n");
        }
        dcp_channel_error(s, ch, CH_ERROR_SETUP, CH_ERROR_INVALID_MODE);
        return;
    }
    if (cipher && (PACKET_CTRL1_CIPHER_SELECT(packet.ctrl1) != DCP_CIPHER_AES128 ||
                   PACKET_CTRL1_CIPHER_MODE(packet.ctrl1) > DCP_CIPHER_MODE_CBC)) {
        dcp_channel_error(s, ch, CH_ERROR_SETUP, CH_ERROR_INVALID_MODE);
        return;
    }
    hash_select = PACKET_CTRL1_HASH_SELECT(packet.ctrl1);
    if (hash && hash_select > DCP_HASH_CRC32) {
        dcp_channel_error(s, ch, CH_ERROR_SETUP, CH_ERROR_INVALID_MODE);
        return;
    }
    if (!memcopy && !cipher && !hash) {
        dcp_channel_error(s, ch, CH_ERROR_SETUP, CH_ERROR_INVALID_MODE);
        return;
    }

    encrypt = packet.ctrl0 & PACKET_CTRL_CIPHER_ENCRYPT;
    cbc = cipher &&
          PACKET_CTRL1_CIPHER_MODE(packet.ctrl1) == DCP_CIPHER_MODE_CBC;
    crc32 = hash && hash_select == DCP_HASH_CRC32;
    hash_output = packet.ctrl0 & PACKET_CTRL_HASH_OUTPUT;
    check_hash = packet.ctrl0 & PACKET_CTRL_CHECK_HASH;

    if (cipher) {
        if (!dcp_load_cipher_key(s, packet.ctrl0, packet.ctrl1,
                                 packet.payload, &payload_off, &aes_key,
                                 encrypt)) {
            dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_PAYLOAD);
            return;
        }
        if (cbc) {
            if (packet.ctrl0 & PACKET_CTRL_CIPHER_INIT) {
                uint32_t raw_iv[4];
                uint32_t w[4];
                int i;

                if (address_space_read(&address_space_memory,
                                       packet.payload + payload_off,
                                       MEMTXATTRS_UNSPECIFIED, raw_iv,
                                       sizeof(raw_iv)) != MEMTX_OK) {
                    dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_PAYLOAD);
                    return;
                }
                for (i = 0; i < 4; i++) {
                    w[i] = le32_to_cpu(raw_iv[i]);
                }
                dcp_apply_swaps(w, packet.ctrl0 & PACKET_CTRL_KEY_BYTESWAP,
                                packet.ctrl0 & PACKET_CTRL_KEY_WORDSWAP);
                dcp_words_to_block(prev, w);
                payload_off += 16;
            } else {
                if (!dcp_context_load(s, ch, true, false)) {
                    dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_CONTEXT);
                    return;
                }
                memcpy(prev, s->ch_cipher_ctx[ch], 16);
            }
        }
        /* AES operates on 16-byte blocks; round up per PDF 15.1.1. */
        remaining = (packet.size + 15) & ~15U;
    } else {
        remaining = packet.size;
    }

    if (hash) {
        if (packet.ctrl0 & PACKET_CTRL_HASH_INIT) {
            if (crc32) {
                s->ch_crc[ch] = 0xffffffffU;
                s->ch_hash_len[ch] = 0;
            } else {
                dcp_sha1_init(s, ch);
            }
        } else if (!crc32 && !dcp_context_load(s, ch, false, true)) {
            dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_CONTEXT);
            return;
        }
        hash_todo = hash_output ? remaining : packet.size;
    } else {
        hash_todo = 0;
    }

    source = packet.source;
    destination = packet.destination;
    while (remaining) {
        size_t length = MIN((uint32_t)sizeof(buffer), remaining);

        if (memcopy && (packet.ctrl0 & PACKET_CTRL_CONSTANT_FILL)) {
            size_t i;

            for (i = 0; i + 4 <= length; i += 4) {
                stl_le_p(buffer + i, packet.source);
            }
        } else {
            if (address_space_read(&address_space_memory, source,
                                   MEMTXATTRS_UNSPECIFIED, buffer, length) !=
                MEMTX_OK) {
                dcp_channel_stall(s, ch, CH_ERROR_SRC, 0);
                return;
            }
        }
        if (hash && !hash_output && hash_todo) {
            uint32_t take = MIN((uint32_t)length, hash_todo);

            dcp_hash_bytes(s, ch, crc32, buffer, take);
            hash_todo -= take;
        }
        if (cipher) {
            size_t off;

            for (off = 0; off < length; off += 16) {
                dcp_cipher_block(packet.ctrl0, cbc, &aes_key, prev,
                                 buffer + off);
            }
        }
        if (memcopy || cipher) {
            if (address_space_write(&address_space_memory, destination,
                                    MEMTXATTRS_UNSPECIFIED, buffer, length) !=
                MEMTX_OK) {
                dcp_channel_stall(s, ch, CH_ERROR_DST, 0);
                return;
            }
        }
        if (hash && hash_output && hash_todo) {
            uint32_t take = MIN((uint32_t)length, hash_todo);

            dcp_hash_bytes(s, ch, crc32, buffer, take);
            hash_todo -= take;
        }
        source += length;
        destination += length;
        remaining -= length;
    }

    if (cipher && cbc) {
        memcpy(s->ch_cipher_ctx[ch], prev, 16);
    }

    if (hash) {
        if (crc32) {
            /* Pad trailing bytes with zeros to a 32-bit boundary. */
            while (s->ch_hash_len[ch] & 3) {
                s->ch_crc[ch] = dcp_crc32_byte(s->ch_crc[ch], 0);
                s->ch_hash_len[ch]++;
            }
        }
        if (packet.ctrl0 & PACKET_CTRL_HASH_TERM) {
            uint32_t result[5];
            uint32_t expected[5];
            unsigned int words = crc32 ? 1 : 5;
            unsigned int i;
            bool mismatch = false;

            if (crc32) {
                result[0] = s->ch_crc[ch];
            } else {
                dcp_sha1_final(s, ch);
                for (i = 0; i < 5; i++) {
                    result[i] = s->ch_sha_h[ch][i];
                }
            }
            if (check_hash) {
                /* Sample the expected digest before overwriting the payload. */
                if (address_space_read(&address_space_memory,
                                       packet.payload + payload_off,
                                       MEMTXATTRS_UNSPECIFIED, expected,
                                       words * 4) != MEMTX_OK) {
                    dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_PAYLOAD);
                    return;
                }
                for (i = 0; i < words; i++) {
                    if (le32_to_cpu(expected[i]) != result[i]) {
                        mismatch = true;
                    }
                }
            }
            for (i = 0; i < words; i++) {
                uint32_t le = cpu_to_le32(result[i]);

                if (address_space_write(&address_space_memory,
                                        packet.payload + 4 * i,
                                        MEMTXATTRS_UNSPECIFIED, &le,
                                        sizeof(le)) != MEMTX_OK) {
                    dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_PAYLOAD);
                    return;
                }
            }
            if (mismatch) {
                /* Mismatch interrupts and terminates the chain. */
                dcp_channel_error(s, ch, CH_ERROR_HASH_MISMATCH, 0);
                return;
            }
        }
    }

    if (!dcp_context_save(s, ch, cbc, hash && !crc32)) {
        dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_CONTEXT);
        return;
    }

    raw.status = cpu_to_le32((tag << 24) | 1U);
    if (address_space_write(&address_space_memory, packet_addr + 0x1c,
                            MEMTXATTRS_UNSPECIFIED, &raw.status,
                            sizeof(raw.status)) != MEMTX_OK) {
        dcp_channel_stall(s, ch, CH_ERROR_PACKET, 0);
        return;
    }

    s->ch_stat[ch] = tag << 24;
    if (packet.ctrl0 & PACKET_CTRL_DECR_SEMA) {
        s->ch_sema[ch]--;
    }
    if (packet.ctrl0 & PACKET_CTRL_CHAIN) {
        if (packet.next == 0) {
            dcp_channel_error(s, ch, CH_ERROR_PACKET, CH_ERROR_NEXT_CHAIN_ZERO);
            return;
        }
        s->ch_cmdptr[ch] = packet.next;
    } else if (packet.ctrl0 & PACKET_CTRL_CHAIN_CONTIG) {
        /* Next descriptor follows this packet contiguously in memory. */
        s->ch_cmdptr[ch] = packet_addr + sizeof(DCPWorkPacket);
    } else if (s->ch_sema[ch] != 0) {
        /* PDF: NO_CHAIN, semaphore nonzero and neither chain bit set. */
        dcp_channel_stall(s, ch, CH_ERROR_PACKET, CH_ERROR_NO_CHAIN);
        return;
    }
    if (packet.ctrl0 & PACKET_CTRL_INTERRUPT) {
        s->stat |= 1U << ch;
    }
    dcp_update_irq(s);
}

/*
 * Channel arbitration (PDF 15.2.5.1): channels with outstanding semaphore
 * tokens are granted one packet each; the high-priority pool is serviced
 * before the low-priority pool and each pool is round-robin fair.  A
 * channel whose CHnOPTS.RECOVERY_TIMER is non-zero sits out the
 * arbitration cycle following its grant.
 */
#define DCP_ARBITRATION_LIMIT 1024

static void dcp_arbitrate(STMP3770DCPState *s)
{
    unsigned int skip = 0;
    unsigned int count = 0;

    while (count++ < DCP_ARBITRATION_LIMIT) {
        uint32_t ready = 0;
        uint32_t high;
        uint32_t pool;
        unsigned int ch = DCP_CHANNELS;
        unsigned int k;

        if (s->ctrl & (CTRL_SFTRST | CTRL_CLKGATE)) {
            break;
        }
        for (k = 0; k < DCP_CHANNELS; k++) {
            if (dcp_channel_ready(s, k)) {
                ready |= 1U << k;
            }
        }
        if (!ready) {
            break;
        }
        high = ready & ((s->channelctrl >> 8) & 0xf);
        pool = ready & ~skip;
        if (!pool) {
            /* Recovery penalty expires once no other channel can grant. */
            skip = 0;
            pool = ready;
        }
        if (pool & high) {
            pool = high;
        }
        for (k = 1; k <= DCP_CHANNELS; k++) {
            unsigned int candidate = (s->arb_last + k) % DCP_CHANNELS;

            if (pool & (1U << candidate)) {
                ch = candidate;
                break;
            }
        }
        if (ch == DCP_CHANNELS) {
            break;
        }
        s->arb_last = ch;
        s->cur_channel = ch;
        dcp_process_packet(s, ch);
        s->last_channel = ch;
        if (s->ch_opts[ch] & 0xffffU) {
            skip |= 1U << ch;
        }
    }
    s->cur_channel = -1;
    if (count >= DCP_ARBITRATION_LIMIT) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "stmp3770-dcp: arbitration packet limit reached\n");
    }
    dcp_update_irq(s);
}

#define CSCCTRL0_ENABLE         (1U << 0)
#define CSCCTRL0_DELTA          (1U << 10)
#define CSCCTRL0_SUBSAMPLE      (1U << 11)
#define CSCCTRL0_ROTATE         (1U << 12)
#define CSCCTRL0_SCALE          (1U << 13)
#define CSCCTRL0_UPSAMPLE       (1U << 14)

#define CSCSTAT_COMPLETE        (1U << 0)
#define CSCSTAT_ERROR_SETUP     (1U << 2)
#define CSCSTAT_ERROR_SRC       (1U << 4)
#define CSCSTAT_ERROR_DST       (1U << 5)
#define CSCSTAT_DYNAMIC_MASK    0x00ff0035U

#define CSC_ERROR_LUMA          0x01U
#define CSC_ERROR_CHROMA_U      0x03U
#define CSC_ERROR_CHROMA_V      0x04U

static void dcp_csc_finish(STMP3770DCPState *s, uint32_t status)
{
    s->cscstat = (s->cscstat & ~CSCSTAT_DYNAMIC_MASK) |
                 (status & CSCSTAT_DYNAMIC_MASK);
    /* ENABLE is software-managed; CSCSTAT.COMPLETE reports completion. */
    s->stat |= 1U << 8;
    dcp_update_irq(s);
}

/*
 * Color-space converter (PDF 15.2.4, Tables 711-726): register-driven
 * planar YUV/YCbCr to RGB frame conversion.  Scaling, rotation and delta
 * green subsampling are not modeled.
 */
static void dcp_csc_run(STMP3770DCPState *s)
{
    uint32_t ctrl0 = s->cscctrl0;
    uint32_t rgb_format = (ctrl0 >> 8) & 3;
    uint32_t yuv_format = (ctrl0 >> 4) & 0xf;
    uint32_t out_line = s->cscoutbufparam & 0xfff;
    uint32_t field = (s->cscoutbufparam >> 12) & 0xfff;
    uint32_t in_line = s->cscinbufparam & 0xfff;
    uint32_t in_chroma = (in_line + 1) / 2;
    int32_t c0 = (s->csccoeff[0] >> 16) & 0x3ff;
    int32_t uv_offset = (s->csccoeff[0] >> 8) & 0xff;
    int32_t y_offset = s->csccoeff[0] & 0xff;
    int32_t c1 = (s->csccoeff[1] >> 16) & 0x3ff;
    int32_t c4 = s->csccoeff[1] & 0x3ff;
    int32_t c2 = (s->csccoeff[2] >> 16) & 0x3ff;
    int32_t c3 = s->csccoeff[2] & 0x3ff;
    hwaddr rgb = s->cscbuf[0];
    hwaddr luma = s->cscbuf[1];
    hwaddr chromau = s->cscbuf[2];
    hwaddr chromav = s->cscbuf[3];
    uint32_t chroma_lines = yuv_format == 0 ? (field + 1) / 2 : field;
    uint32_t x;
    uint32_t y;

    if (ctrl0 & (CSCCTRL0_SCALE | CSCCTRL0_ROTATE | CSCCTRL0_SUBSAMPLE)) {
        qemu_log_mask(LOG_UNIMP,
                      "stmp3770-dcp: CSC scale/rotate/subsample\n");
        dcp_csc_finish(s, CSCSTAT_ERROR_SETUP);
        return;
    }
    if ((yuv_format != 0 && yuv_format != 2) || rgb_format == 1 ||
        ((ctrl0 & CSCCTRL0_DELTA) && rgb_format != 2)) {
        dcp_csc_finish(s, CSCSTAT_ERROR_SETUP);
        return;
    }

    for (y = 0; y < field; y++) {
        uint32_t chroma_y = yuv_format == 0 ? y / 2 : y;

        x = 0;
        while (x < out_line) {
            uint8_t yv[2] = { 0, 0 };
            uint8_t uu[2] = { 0, 0 };
            uint8_t vv[2] = { 0, 0 };
            unsigned int pair = (rgb_format == 3 && x + 1 < out_line) ? 2 : 1;
            unsigned int p;

            for (p = 0; p < pair; p++) {
                uint32_t cx = (x + p) / 2;
                uint32_t cx1 = MIN(cx + 1, in_chroma ? in_chroma - 1 : 0);

                if (address_space_read(&address_space_memory,
                                       luma + y * in_line + x + p,
                                       MEMTXATTRS_UNSPECIFIED, &yv[p], 1) !=
                    MEMTX_OK) {
                    dcp_csc_finish(s, CSCSTAT_ERROR_SRC |
                                   (CSC_ERROR_LUMA << 16));
                    return;
                }
                if (address_space_read(&address_space_memory,
                                       chromau + chroma_y * in_chroma + cx,
                                       MEMTXATTRS_UNSPECIFIED, &uu[p], 1) !=
                    MEMTX_OK) {
                    dcp_csc_finish(s, CSCSTAT_ERROR_SRC |
                                   (CSC_ERROR_CHROMA_U << 16));
                    return;
                }
                if (address_space_read(&address_space_memory,
                                       chromav + chroma_y * in_chroma + cx,
                                       MEMTXATTRS_UNSPECIFIED, &vv[p], 1) !=
                    MEMTX_OK) {
                    dcp_csc_finish(s, CSCSTAT_ERROR_SRC |
                                   (CSC_ERROR_CHROMA_V << 16));
                    return;
                }
                if ((ctrl0 & CSCCTRL0_UPSAMPLE) && ((x + p) & 1)) {
                    uint8_t u1 = 0;
                    uint8_t v1 = 0;

                    if (address_space_read(&address_space_memory,
                                           chromau + chroma_y * in_chroma + cx1,
                                           MEMTXATTRS_UNSPECIFIED, &u1, 1) !=
                        MEMTX_OK) {
                        dcp_csc_finish(s, CSCSTAT_ERROR_SRC |
                                       (CSC_ERROR_CHROMA_U << 16));
                        return;
                    }
                    if (address_space_read(&address_space_memory,
                                           chromav + chroma_y * in_chroma + cx1,
                                           MEMTXATTRS_UNSPECIFIED, &v1, 1) !=
                        MEMTX_OK) {
                        dcp_csc_finish(s, CSCSTAT_ERROR_SRC |
                                       (CSC_ERROR_CHROMA_V << 16));
                        return;
                    }
                    uu[p] = (uu[p] + u1 + 1) / 2;
                    vv[p] = (vv[p] + v1 + 1) / 2;
                }
            }

            if (rgb_format == 3) {
                /* Interleaved YCbCr 4:2:2 (PDF Table 634): U Y0 V Y1. */
                uint8_t out[4] = { uu[0], yv[0], vv[0], yv[1] };

                if (address_space_write(&address_space_memory,
                                        rgb + 2 * (y * out_line + x),
                                        MEMTXATTRS_UNSPECIFIED, out,
                                        pair * 2) != MEMTX_OK) {
                    dcp_csc_finish(s, CSCSTAT_ERROR_DST);
                    return;
                }
            } else {
                for (p = 0; p < pair; p++) {
                    int32_t yy = (int32_t)yv[p] - y_offset;
                    int32_t cb = (int32_t)uu[p] - uv_offset;
                    int32_t cr = (int32_t)vv[p] - uv_offset;
                    int32_t r = (c0 * yy + c1 * cr + 0x80) >> 8;
                    int32_t g = (c0 * yy - c2 * cr - c3 * cb + 0x80) >> 8;
                    int32_t b = (c0 * yy + c4 * cb + 0x80) >> 8;

                    r = MAX(0, MIN(255, r));
                    g = MAX(0, MIN(255, g));
                    b = MAX(0, MIN(255, b));
                    if (rgb_format == 0) {
                        /* RGB16_565 */
                        uint16_t px = ((uint16_t)(r >> 3) << 11) |
                                      ((uint16_t)(g >> 2) << 5) |
                                      (uint16_t)(b >> 3);
                        uint8_t out[2] = { px & 0xff, px >> 8 };

                        if (address_space_write(&address_space_memory,
                                                rgb + 2 * (y * out_line + x + p),
                                                MEMTXATTRS_UNSPECIFIED, out,
                                                2) != MEMTX_OK) {
                            dcp_csc_finish(s, CSCSTAT_ERROR_DST);
                            return;
                        }
                    } else {
                        /* RGB24 unpacked; delta swaps R/G on odd lines. */
                        uint8_t out[4] = { 0, r, g, b };

                        if ((ctrl0 & CSCCTRL0_DELTA) && (y & 1)) {
                            out[1] = g;
                            out[2] = b;
                            out[3] = r;
                        }
                        if (address_space_write(&address_space_memory,
                                                rgb + 4 * (y * out_line + x + p),
                                                MEMTXATTRS_UNSPECIFIED, out,
                                                4) != MEMTX_OK) {
                            dcp_csc_finish(s, CSCSTAT_ERROR_DST);
                            return;
                        }
                    }
                }
            }
            x += pair;
        }
    }

    /* Buffer pointers are working registers and advance past the frame. */
    s->cscbuf[1] += field * in_line;
    s->cscbuf[2] += chroma_lines * in_chroma;
    s->cscbuf[3] += chroma_lines * in_chroma;
    s->cscbuf[0] += (uint32_t)field * out_line * (rgb_format == 0 ? 2 :
                                                  rgb_format == 2 ? 4 : 2);
    dcp_csc_finish(s, CSCSTAT_COMPLETE);
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
    case REG_STAT: {
        uint32_t live = s->stat;
        unsigned int k;

        /* READY_CHANNELS and CUR_CHANNEL are live arbiter views. */
        live &= ~((0xffU << 16) | (0xfU << 24));
        if (!(s->ctrl & (CTRL_SFTRST | CTRL_CLKGATE))) {
            for (k = 0; k < DCP_CHANNELS; k++) {
                if (dcp_channel_ready(s, k)) {
                    live |= 1U << (16 + k);
                }
            }
            if (s->cur_channel >= 0) {
                live |= (uint32_t)(s->cur_channel + 1) << 24;
            }
        }
        return live;
    }
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
        /* PDF 15.2.2.1: keys written into the key storage are not readable. */
        return 0;
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
            dcp_arbitrate(s);
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
        dcp_arbitrate(s);
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
    case REG_CSCCTRL0: {
        uint32_t old = s->cscctrl0;

        s->cscctrl0 = dcp_apply_sct(s->cscctrl0, val,
                                    CSCCTRL0_WRITABLE_MASK, modifier);
        if (!(old & CSCCTRL0_ENABLE) && (s->cscctrl0 & CSCCTRL0_ENABLE)) {
            dcp_csc_run(s);
        }
        return;
    }
    case REG_CSCSTAT:
        /* PDF Table 649: CSCSTAT has SET only, no CLR/TOG. */
        if (modifier == 0 || modifier == REG_SET) {
            s->cscstat = dcp_apply_sct(s->cscstat, val,
                                       CSCSTAT_WRITABLE_MASK, modifier);
        }
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
            dcp_arbitrate(s);
        }
        break;
    case REG_CH_SEMA:
        if (modifier == 0) {
            s->ch_sema[ch] = MIN(0xffU, s->ch_sema[ch] + (val & 0xff));
            dcp_arbitrate(s);
        } else if (modifier == REG_CLR && (val & 0xff)) {
            s->ch_sema[ch] = 0;
        }
        break;
    case REG_CH_STAT:
        if (modifier == REG_TOG && !dcp_ch_stat_has_tog[ch]) {
            break;
        }
        s->ch_stat[ch] = dcp_apply_sct(s->ch_stat[ch], val,
                                       CH_STAT_WRITABLE_MASK, modifier);
        /* Clearing latched error bits makes the channel schedulable again. */
        dcp_arbitrate(s);
        break;
    case REG_CH_OPTS:
        if (modifier == REG_TOG && !dcp_ch_opts_has_tog[ch]) {
            break;
        }
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
    .version_id = 3,
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
        VMSTATE_UINT8_2DARRAY_V(ch_cipher_ctx, STMP3770DCPState,
                                DCP_CHANNELS, 16, 2),
        VMSTATE_UINT32_2DARRAY_V(ch_sha_h, STMP3770DCPState,
                                 DCP_CHANNELS, 5, 2),
        VMSTATE_UINT32_ARRAY_V(ch_crc, STMP3770DCPState, DCP_CHANNELS, 2),
        VMSTATE_UINT32_ARRAY_V(ch_hash_len, STMP3770DCPState,
                               DCP_CHANNELS, 2),
        VMSTATE_UINT8_2DARRAY_V(ch_hash_buf, STMP3770DCPState,
                                DCP_CHANNELS, 64, 2),
        VMSTATE_INT32_V(arb_last, STMP3770DCPState, 3),
        VMSTATE_INT32_V(last_channel, STMP3770DCPState, 3),
        VMSTATE_INT32_V(cur_channel, STMP3770DCPState, 3),
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
