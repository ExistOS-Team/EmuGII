/* Common Debug UART helpers for bare-metal STMP3770 tests */
#ifndef BAREMETAL_UART_H
#define BAREMETAL_UART_H

#define UART_BASE 0x80070000
#define UART_DR   (*(volatile unsigned int *)(UART_BASE + 0x00))
#define UART_FR   (*(volatile unsigned int *)(UART_BASE + 0x18))
#define UART_CR   (*(volatile unsigned int *)(UART_BASE + 0x30))

#define UART_FR_TXFF (1 << 5)
#define CR_UARTEN    (1 << 0)
#define CR_TXE       (1 << 8)

void uart_putc(char c);
void uart_puts(const char *s);
void uart_puthex(unsigned int v);

#endif
