/*
 * LCDIF basic test for STMP3770 QEMU
 *
 * Configures a small 16x8 RGB565 framebuffer, enables the controller,
 * and verifies register writes do not hang or trigger unimplemented warnings.
 */

#include <stdint.h>

#define UART_BASE 0x80070000
#define UART_DR   (*(volatile unsigned int *)(UART_BASE + 0x00))
#define UART_FR   (*(volatile unsigned int *)(UART_BASE + 0x18))
#define UART_CR   (*(volatile unsigned int *)(UART_BASE + 0x30))

#define UART_FR_TXFF (1 << 5)
#define CR_UARTEN (1 << 0)
#define CR_TXE    (1 << 8)

#define LCDIF_BASE 0x80030000
#define LCDIF_CTRL0     (*(volatile unsigned int *)(LCDIF_BASE + 0x000))
#define LCDIF_CTRL0_CLR (*(volatile unsigned int *)(LCDIF_BASE + 0x008))
#define LCDIF_CTRL1     (*(volatile unsigned int *)(LCDIF_BASE + 0x010))
#define LCDIF_TIMING0   (*(volatile unsigned int *)(LCDIF_BASE + 0x040))
#define LCDIF_TIMING1   (*(volatile unsigned int *)(LCDIF_BASE + 0x050))
#define LCDIF_CUR_BUF   (*(volatile unsigned int *)(LCDIF_BASE + 0x020))
#define LCDIF_IRQ_EN    (*(volatile unsigned int *)(LCDIF_BASE + 0x0D0))

#define CTRL0_SFTRST    (1U << 31)
#define CTRL0_CLKGATE   (1U << 30)
#define CTRL0_RUN       (1U << 0)

#define FB_ADDR 0x40020000

static void uart_putc(char c) {
    while (UART_FR & UART_FR_TXFF);
    UART_DR = c;
}

static void uart_puts(const char *s) {
    while (*s) {
        if (*s == '\n') uart_putc('\r');
        uart_putc(*s++);
    }
}

void _start(void) __attribute__((section(".text.startup"), naked));
void _start(void) {
    __asm__ volatile (
        "ldr sp, =0x00080000\n\t"
        "bl main\n\t"
        "b .\n\t"
    );
}

void main(void) {
    volatile uint16_t *fb = (volatile uint16_t *)FB_ADDR;
    int i;

    UART_CR = CR_UARTEN | CR_TXE;
    uart_puts("LCDIF test\n");

    /* Fill framebuffer with alternating pixels */
    for (i = 0; i < 16 * 8; i++) {
        fb[i] = (i & 1) ? 0xF800 : 0x07E0;
    }

    /* Reset and ungate, then enable */
    LCDIF_CTRL0_CLR = CTRL0_SFTRST | CTRL0_CLKGATE;
    LCDIF_TIMING0 = 16;        /* width */
    LCDIF_TIMING1 = 8;         /* height */
    LCDIF_CUR_BUF = FB_ADDR;
    LCDIF_IRQ_EN = 0;
    LCDIF_CTRL1 = 0;
    LCDIF_CTRL0 = CTRL0_RUN;

    uart_puts("LCDIF OK\n");
    while (1);
}
