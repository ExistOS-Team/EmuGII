/*
 * Simple test program for STMP3770 QEMU
 * Prints "Hello from STMP3770!" to Debug UART
 */

#define UART_BASE 0x80070000
#define UART_DR   (*(volatile unsigned int *)(UART_BASE + 0x00))
#define UART_FR   (*(volatile unsigned int *)(UART_BASE + 0x18))
#define UART_CR   (*(volatile unsigned int *)(UART_BASE + 0x30))

#define UART_FR_TXFF (1 << 5)  /* Transmit FIFO full */

#define CR_UARTEN (1 << 0)     /* UART enable */
#define CR_TXE    (1 << 8)     /* Transmit enable */

void uart_putc(char c) {
    /* Wait until TX FIFO not full */
    while (UART_FR & UART_FR_TXFF);
    UART_DR = c;
}

void uart_puts(const char *s) {
    while (*s) {
        if (*s == '\n') {
            uart_putc('\r');
        }
        uart_putc(*s++);
    }
}

void _start(void) __attribute__((section(".text.startup"), naked));

void _start(void) {
    __asm__ volatile (
        "ldr sp, =0x00080000\n\t"
        "bl init_uart\n\t"
        "b .\n\t"
    );
}

void init_uart(void) {
    /* Enable UART and transmitter */
    UART_CR = CR_UARTEN | CR_TXE;

    uart_puts("Hello from STMP3770!\n");
    uart_puts("UART is working!\n");
}
