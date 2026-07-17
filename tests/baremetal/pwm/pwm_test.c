/*
 * STMP3770 PWM register smoke test
 */



#include "common/uart.h"
#define PWM_BASE 0x80064000
#define PWM_CTRL0     (*(volatile unsigned int *)(PWM_BASE + 0x000))
#define PWM_CTRL0_CLR (*(volatile unsigned int *)(PWM_BASE + 0x008))
#define PWM_PERIOD(ch) (*(volatile unsigned int *)(PWM_BASE + 0x100 + (ch)*0x10))
#define PWM_DUTY(ch)   (*(volatile unsigned int *)(PWM_BASE + 0x180 + (ch)*0x10))
#define PWM_ACTIVE(ch) (*(volatile unsigned int *)(PWM_BASE + 0x200 + (ch)*0x10))
#define PWM_VERSION    (*(volatile unsigned int *)(PWM_BASE + 0x1F0))

#define CTRL0_SFTRST  (1U << 31)
#define CTRL0_CLKGATE (1U << 30)




static int fail;

static void check_eq(const char *name, unsigned int got, unsigned int exp) {
    if (got != exp) {
        uart_puts("FAIL ");
        uart_puts(name);
        uart_puts(" got ");
        uart_puthex(got);
        uart_puts(" expected ");
        uart_puthex(exp);
        uart_puts("\n");
        fail = 1;
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
    int ch;

    UART_CR = CR_UARTEN | CR_TXE;
    uart_puts("PWM smoke test\n");

    check_eq("VERSION", PWM_VERSION, 0x01000000);

    PWM_CTRL0_CLR = CTRL0_SFTRST | CTRL0_CLKGATE;
    if (PWM_CTRL0 & (CTRL0_SFTRST | CTRL0_CLKGATE)) {
        uart_puts("FAIL CTRL0 reset bits not cleared\n");
        fail = 1;
    }

    for (ch = 0; ch < 5; ch++) {
        PWM_PERIOD(ch) = 0x1000 + ch;
        PWM_DUTY(ch)   = 0x2000 + ch;
        PWM_ACTIVE(ch) = 0x3000 + ch;
        check_eq("PERIOD", PWM_PERIOD(ch), 0x1000 + ch);
        check_eq("DUTY",   PWM_DUTY(ch),   0x2000 + ch);
        check_eq("ACTIVE", PWM_ACTIVE(ch), 0x3000 + ch);
    }

    if (!fail) {
        uart_puts("PASS\n");
    } else {
        uart_puts("FAIL\n");
    }
}
