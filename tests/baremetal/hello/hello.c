/*
 * Simple test program for STMP3770 QEMU
 * Prints "Hello from STMP3770!" to Debug UART
 */






#include "common/uart.h"
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
