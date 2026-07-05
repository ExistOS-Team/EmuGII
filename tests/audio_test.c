/*
 * Audio DAC/ADC basic test for STMP3770 QEMU
 *
 * Verifies that the audio controllers can be reset, ungated, and enabled
 * without triggering unimplemented register warnings.
 */

#define UART_BASE 0x80070000
#define UART_DR   (*(volatile unsigned int *)(UART_BASE + 0x00))
#define UART_FR   (*(volatile unsigned int *)(UART_BASE + 0x18))
#define UART_CR   (*(volatile unsigned int *)(UART_BASE + 0x30))

#define UART_FR_TXFF (1 << 5)
#define CR_UARTEN (1 << 0)
#define CR_TXE    (1 << 8)

#define AUDIODAC_BASE 0x80048000
#define AUDIODAC_CTRL0     (*(volatile unsigned int *)(AUDIODAC_BASE + 0x000))
#define AUDIODAC_CTRL0_CLR (*(volatile unsigned int *)(AUDIODAC_BASE + 0x008))

#define AUDIOADC_BASE 0x8004C000
#define AUDIOADC_CTRL0     (*(volatile unsigned int *)(AUDIOADC_BASE + 0x000))
#define AUDIOADC_CTRL0_CLR (*(volatile unsigned int *)(AUDIOADC_BASE + 0x008))

#define CTRL0_SFTRST    (1U << 31)
#define CTRL0_CLKGATE   (1U << 30)
#define CTRL0_RUN       (1U << 0)

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
    UART_CR = CR_UARTEN | CR_TXE;
    uart_puts("Audio test\n");

    /* Reset/ungate and enable DAC */
    AUDIODAC_CTRL0_CLR = CTRL0_SFTRST | CTRL0_CLKGATE;
    AUDIODAC_CTRL0 = CTRL0_RUN;

    /* Reset/ungate and enable ADC */
    AUDIOADC_CTRL0_CLR = CTRL0_SFTRST | CTRL0_CLKGATE;
    AUDIOADC_CTRL0 = CTRL0_RUN;

    uart_puts("AUDIO OK\n");
    while (1);
}
