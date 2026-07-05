/*
 * HP39GII host-input to GPIO-matrix test for STMP3770 QEMU.
 *
 * Host-side verification sends QEMU key F1 after the READY line.  A correct
 * front panel input path must inject that key into the PINCTRL matrix so that
 * row 0 / column 0 reads as an active-low pressed key.
 */

#define UART_BASE 0x80070000
#define UART_DR   (*(volatile unsigned int *)(UART_BASE + 0x00))
#define UART_FR   (*(volatile unsigned int *)(UART_BASE + 0x18))
#define UART_CR   (*(volatile unsigned int *)(UART_BASE + 0x30))

#define UART_FR_TXFF (1 << 5)
#define CR_UARTEN    (1 << 0)
#define CR_TXE       (1 << 8)

#define PINCTRL_BASE 0x80018000
#define PINCTRL_DOUT0 (*(volatile unsigned int *)(PINCTRL_BASE + 0x400))
#define PINCTRL_DOUT1 (*(volatile unsigned int *)(PINCTRL_BASE + 0x410))
#define PINCTRL_DOUT2 (*(volatile unsigned int *)(PINCTRL_BASE + 0x420))
#define PINCTRL_DIN1  (*(volatile unsigned int *)(PINCTRL_BASE + 0x510))
#define PINCTRL_DOE0  (*(volatile unsigned int *)(PINCTRL_BASE + 0x600))
#define PINCTRL_DOE1  (*(volatile unsigned int *)(PINCTRL_BASE + 0x610))
#define PINCTRL_DOE2  (*(volatile unsigned int *)(PINCTRL_BASE + 0x620))

#define KEY_COL0_PIN (1U << 23)
#define KEY_COL_MASK ((1U << 22) | (1U << 23) | (1U << 25) | \
                      (1U << 26) | (1U << 27))
#define KEY_ROW2_MASK ((1U << 14) | (1U << 8) | (1U << 7) | \
                       (1U << 6) | (1U << 5) | (1U << 4) | \
                       (1U << 3) | (1U << 2))
#define KEY_ROW0_PIN (1U << 6)

static void uart_putc(char c)
{
    while (UART_FR & UART_FR_TXFF) {
    }
    UART_DR = c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n') {
            uart_putc('\r');
        }
        uart_putc(*s++);
    }
}

static void keyboard_gpio_init(void)
{
    PINCTRL_DOUT1 |= KEY_COL_MASK;
    PINCTRL_DOE1 &= ~KEY_COL_MASK;

    PINCTRL_DOUT2 |= KEY_ROW2_MASK;
    PINCTRL_DOE2 |= KEY_ROW2_MASK;

    PINCTRL_DOUT1 |= (1U << 24);
    PINCTRL_DOE1 |= (1U << 24);

    PINCTRL_DOUT0 |= (1U << 20);
    PINCTRL_DOE0 |= (1U << 20);

    PINCTRL_DOUT0 |= (1U << 14);
    PINCTRL_DOE0 &= ~(1U << 14);
}

static void select_row0(void)
{
    PINCTRL_DOUT2 |= KEY_ROW2_MASK;
    PINCTRL_DOUT1 |= (1U << 24);
    PINCTRL_DOUT0 |= (1U << 20);
    PINCTRL_DOUT2 &= ~KEY_ROW0_PIN;
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
    unsigned int i;

    UART_CR = CR_UARTEN | CR_TXE;
    keyboard_gpio_init();
    select_row0();

    uart_puts("KEYBOARD INPUT TEST READY\n");

    for (i = 0; i < 10000000U; i++) {
        select_row0();
        if ((PINCTRL_DIN1 & KEY_COL0_PIN) == 0) {
            uart_puts("KEYBOARD INPUT TEST PASS\n");
            while (1) {
            }
        }
    }

    uart_puts("KEYBOARD INPUT TEST FAIL\n");
    while (1) {
    }
}
