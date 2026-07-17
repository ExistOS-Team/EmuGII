/*
 * GPMI erase/write-style APBH completion regression test.
 *
 * ExistOS completes erase and write-meta through the APBH channel 4 command
 * completion interrupt, not the BCH interrupt. This test builds the same
 * erase/status/compare/completion chain shape and checks that CH4 completion
 * reaches both APBH_CTRL1 and ICOLL RAW0 bit 13.
 */

#include "common/uart.h"
#include <stdint.h>



#define ICOLL_BASE 0x80000000
#define ICOLL_VECTOR        (*(volatile uint32_t *)(ICOLL_BASE + 0x000))
#define ICOLL_CTRL          (*(volatile uint32_t *)(ICOLL_BASE + 0x020))
#define ICOLL_RAW0          (*(volatile uint32_t *)(ICOLL_BASE + 0x040))
#define ICOLL_PRIORITY3_SET (*(volatile uint32_t *)(ICOLL_BASE + 0x094))

#define APBH_BASE 0x80004000
#define APBH_CTRL0         (*(volatile uint32_t *)(APBH_BASE + 0x000))
#define APBH_CTRL1         (*(volatile uint32_t *)(APBH_BASE + 0x010))
#define APBH_CTRL1_SET     (*(volatile uint32_t *)(APBH_BASE + 0x014))
#define APBH_CTRL1_CLR     (*(volatile uint32_t *)(APBH_BASE + 0x018))
#define APBH_CH4_CURCMDAR  (*(volatile uint32_t *)(APBH_BASE + 0x200))
#define APBH_CH4_NXTCMDAR  (*(volatile uint32_t *)(APBH_BASE + 0x210))
#define APBH_CH4_SEMA      (*(volatile uint32_t *)(APBH_BASE + 0x240))

#define GPMI_BASE 0x8000C000
#define GPMI_CTRL0 (*(volatile uint32_t *)(GPMI_BASE + 0x00))

#define DMA_CMD_COMMAND_NO_DMA_XFER 0
#define DMA_CMD_COMMAND_DMA_READ    2
#define DMA_CMD_COMMAND_DMA_SENSE   3
#define DMA_CMD_IRQONCMPLT          (1U << 3)
#define DMA_CMD_CHAIN               (1U << 2)
#define DMA_CMD_SEMAPHORE           (1U << 6)
#define DMA_CMD_WAIT4ENDCMD         (1U << 7)
#define DMA_CMD_NANDWAIT4READY      (1U << 5)
#define DMA_CMD_NANDLOCK            (1U << 4)
#define DMA_CMD_CMDWORDS_SHIFT      12
#define DMA_CMD_XFER_COUNT_SHIFT    16

#define CTRL0_WORD_LENGTH           (1U << 23)
#define CTRL0_LOCK_CS               (1U << 22)
#define CTRL0_COMMAND_MODE_SHIFT    24
#define CTRL0_ADDRESS_SHIFT         17
#define CTRL0_ADDRESS_INCREMENT     (1U << 16)

#define COMMAND_MODE_WRITE          0
#define COMMAND_MODE_READ_COMPARE   2
#define COMMAND_MODE_WAIT_READY     3
#define ADDRESS_DATA                0
#define ADDRESS_CLE                 1

#define NAND_CMD_ERASE1             0x60
#define NAND_CMD_ERASE2             0xD0
#define NAND_CMD_STATUS             0x70

#define APBH_CH4_CMDCMPLT_IRQ       (1U << 4)
#define APBH_CH4_CMDCMPLT_IRQ_EN    (1U << 12)
#define APBH_CH4_AHB_ERROR_IRQ      (1U << 20)
#define ICOLL_GPMI_DMA_IRQ          (1U << 13)
#define ICOLL_IRQ_FINAL_ENABLE      (1U << 16)
#define ICOLL_IRQ13_ENABLE          (0x4U << 8)
#define STATUS_COMPARE_MASK_REF     0x00000100U

struct gpmi_dma_desc {
    uint32_t next;
    uint32_t cmd;
    uint32_t bar;
    uint32_t ctrl0;
    uint32_t compare;
    uint32_t eccctrl;
};

static struct gpmi_dma_desc desc[9] __attribute__((aligned(32)));
static uint8_t cmd_buf[8] __attribute__((aligned(4)));



static void uart_hex32(uint32_t v)
{
    static const char hex[] = "0123456789ABCDEF";

    uart_puts("0x");
    for (int i = 28; i >= 0; i -= 4) {
        uart_putc(hex[(v >> i) & 0xF]);
    }
}

static void uart_dec(uint32_t v)
{
    char buf[11];
    int i = 0;

    if (v == 0) {
        uart_putc('0');
        return;
    }

    while (v != 0 && i < (int)sizeof(buf)) {
        buf[i++] = (char)('0' + (v % 10));
        v /= 10;
    }
    while (i > 0) {
        uart_putc(buf[--i]);
    }
}

static uint32_t make_cmd(uint32_t command, uint32_t cmdwords,
                         uint32_t xfer_count, uint32_t flags)
{
    return command | flags |
           (cmdwords << DMA_CMD_CMDWORDS_SHIFT) |
           (xfer_count << DMA_CMD_XFER_COUNT_SHIFT);
}

static uint32_t make_ctrl0(uint32_t mode, uint32_t address, uint32_t count,
                           uint32_t flags)
{
    return (mode << CTRL0_COMMAND_MODE_SHIFT) |
           (address << CTRL0_ADDRESS_SHIFT) |
           CTRL0_WORD_LENGTH | flags | count;
}

void _start(void) __attribute__((section(".text.startup"), naked));
void _start(void)
{
    __asm__ volatile (
        "ldr sp, =0x00080000\n\t"
        "bl main\n\t"
        "b .\n\t"
    );
}

void main(void)
{
    uint32_t timeout;
    uint32_t failed_block = 0xFFFFFFFFU;
    uint32_t last_ctrl1 = 0;
    uint32_t last_raw0 = 0;
    uint32_t last_vector = 0;
    uint32_t last_cur = 0;

    UART_CR = CR_UARTEN | CR_TXE;
    uart_puts("GPMI write/erase IRQ test\n");

    ICOLL_CTRL = ICOLL_IRQ_FINAL_ENABLE;
    ICOLL_PRIORITY3_SET = ICOLL_IRQ13_ENABLE;
    APBH_CTRL0 = 0;
    GPMI_CTRL0 = 0;
    APBH_CTRL1_CLR = APBH_CH4_CMDCMPLT_IRQ | APBH_CH4_AHB_ERROR_IRQ;
    APBH_CTRL1_SET = APBH_CH4_CMDCMPLT_IRQ_EN;

    desc[0].next = (uint32_t)&desc[1];
    desc[0].cmd = make_cmd(DMA_CMD_COMMAND_DMA_READ, 3, 4,
                           DMA_CMD_WAIT4ENDCMD | DMA_CMD_NANDLOCK |
                           DMA_CMD_CHAIN);
    desc[0].bar = (uint32_t)&cmd_buf[0];
    desc[0].ctrl0 = make_ctrl0(COMMAND_MODE_WRITE, ADDRESS_CLE, 4,
                               CTRL0_LOCK_CS | CTRL0_ADDRESS_INCREMENT);

    desc[1].next = (uint32_t)&desc[2];
    desc[1].cmd = make_cmd(DMA_CMD_COMMAND_DMA_READ, 3, 1,
                           DMA_CMD_WAIT4ENDCMD | DMA_CMD_NANDLOCK |
                           DMA_CMD_CHAIN);
    desc[1].bar = (uint32_t)&cmd_buf[4];
    desc[1].ctrl0 = make_ctrl0(COMMAND_MODE_WRITE, ADDRESS_CLE, 1,
                               CTRL0_LOCK_CS);

    desc[2].next = (uint32_t)&desc[3];
    desc[2].cmd = make_cmd(DMA_CMD_COMMAND_NO_DMA_XFER, 1, 0,
                           DMA_CMD_WAIT4ENDCMD | DMA_CMD_NANDWAIT4READY |
                           DMA_CMD_CHAIN);
    desc[2].ctrl0 = make_ctrl0(COMMAND_MODE_WAIT_READY, ADDRESS_DATA, 0, 0);

    desc[3].next = (uint32_t)&desc[4];
    desc[3].cmd = make_cmd(DMA_CMD_COMMAND_DMA_SENSE, 0, 0, DMA_CMD_CHAIN);
    desc[3].bar = (uint32_t)&desc[8];

    desc[4].next = (uint32_t)&desc[5];
    desc[4].cmd = make_cmd(DMA_CMD_COMMAND_DMA_READ, 3, 1,
                           DMA_CMD_WAIT4ENDCMD | DMA_CMD_NANDLOCK |
                           DMA_CMD_CHAIN);
    desc[4].bar = (uint32_t)&cmd_buf[5];
    desc[4].ctrl0 = make_ctrl0(COMMAND_MODE_WRITE, ADDRESS_CLE, 1,
                               CTRL0_LOCK_CS);

    desc[5].next = (uint32_t)&desc[6];
    desc[5].cmd = make_cmd(DMA_CMD_COMMAND_NO_DMA_XFER, 2, 0,
                           DMA_CMD_WAIT4ENDCMD | DMA_CMD_NANDLOCK |
                           DMA_CMD_CHAIN);
    desc[5].ctrl0 = make_ctrl0(COMMAND_MODE_READ_COMPARE, ADDRESS_DATA, 1, 0);
    desc[5].compare = STATUS_COMPARE_MASK_REF;

    desc[6].next = (uint32_t)&desc[7];
    desc[6].cmd = make_cmd(DMA_CMD_COMMAND_DMA_SENSE, 0, 0, DMA_CMD_CHAIN);
    desc[6].bar = (uint32_t)&desc[8];

    desc[7].next = 0;
    desc[7].cmd = DMA_CMD_IRQONCMPLT | DMA_CMD_SEMAPHORE;

    desc[8].next = 0;
    desc[8].cmd = DMA_CMD_IRQONCMPLT | DMA_CMD_SEMAPHORE;

    for (uint32_t block = 0; block < 220U; block++) {
        uint32_t row = block * 64U;

        cmd_buf[0] = NAND_CMD_ERASE1;
        cmd_buf[1] = (uint8_t)((row >> 0) & 0xFF);
        cmd_buf[2] = (uint8_t)((row >> 8) & 0xFF);
        cmd_buf[3] = (uint8_t)((row >> 16) & 0xFF);
        cmd_buf[4] = NAND_CMD_ERASE2;
        cmd_buf[5] = NAND_CMD_STATUS;

        __asm__ volatile ("" ::: "memory");

        APBH_CH4_NXTCMDAR = (uint32_t)&desc[0];
        APBH_CH4_SEMA = 1;

        timeout = 1000000;
        while ((APBH_CH4_SEMA & 0xFFU) && timeout--) {
        }

        last_ctrl1 = APBH_CTRL1;
        last_raw0 = ICOLL_RAW0;
        last_vector = ICOLL_VECTOR;
        last_cur = APBH_CH4_CURCMDAR;

        if (timeout == 0 ||
            !(last_ctrl1 & APBH_CH4_CMDCMPLT_IRQ) ||
            !(last_raw0 & ICOLL_GPMI_DMA_IRQ) ||
            ((last_vector >> 2) != 13U)) {
            failed_block = block;
            break;
        }

        APBH_CTRL1_CLR = APBH_CH4_CMDCMPLT_IRQ | APBH_CH4_AHB_ERROR_IRQ;
    }

    uart_puts("block=");
    if (failed_block == 0xFFFFFFFFU) {
        uart_puts("none");
    } else {
        uart_dec(failed_block);
    }
    uart_puts(" sema=");
    uart_hex32(APBH_CH4_SEMA);
    uart_puts(" ctrl1=");
    uart_hex32(last_ctrl1);
    uart_puts(" raw0=");
    uart_hex32(last_raw0);
    uart_puts(" vector=");
    uart_hex32(last_vector);
    uart_puts(" cur=");
    uart_hex32(last_cur);
    uart_puts("\n");

    if (failed_block == 0xFFFFFFFFU) {
        uart_puts("GPMI WRITE ERASE IRQ TEST PASS\n");
    } else {
        uart_puts("GPMI WRITE ERASE IRQ TEST FAIL\n");
    }
}
