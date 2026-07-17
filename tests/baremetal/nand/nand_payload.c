/*
 * Minimal NAND boot payload: gets loaded to 0x40010000 by the boot test.
 */





#include "common/uart.h"
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
    uart_puts("BOOT OK\n");
    while (1);
}
