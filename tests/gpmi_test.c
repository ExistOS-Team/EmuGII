/*
 * GPMI/NAND smoke test for STMP3770 QEMU
 *
 * Performs a direct-register READ ID sequence and reports the result.
 */

#define UART_BASE 0x80070000
#define UART_DR   (*(volatile unsigned int *)(UART_BASE + 0x00))
#define UART_FR   (*(volatile unsigned int *)(UART_BASE + 0x18))
#define UART_CR   (*(volatile unsigned int *)(UART_BASE + 0x30))

#define UART_FR_TXFF (1 << 5)
#define CR_UARTEN (1 << 0)
#define CR_TXE    (1 << 8)

#define GPMI_BASE 0x8000C000
#define GPMI_CTRL0     (*(volatile unsigned int *)(GPMI_BASE + 0x00))
#define GPMI_DATA      (*(volatile unsigned int *)(GPMI_BASE + 0xA0))
#define GPMI_STAT      (*(volatile unsigned int *)(GPMI_BASE + 0xB0))

#define CTRL0_RUN           (1U << 29)
#define CTRL0_COMMAND_MODE_SHIFT 24
#define CTRL0_ADDRESS_SHIFT 17
#define CTRL0_XFER_COUNT_MASK 0xFFFF

#define COMMAND_MODE_WRITE 0
#define COMMAND_MODE_READ  1
#define ADDRESS_CLE 1
#define ADDRESS_ALE 2
#define ADDRESS_DATA 0

#define NAND_CMD_READ_ID 0x90

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

static void uart_puthex(unsigned int v) {
    int i;
    uart_puts("0x");
    for (i = 28; i >= 0; i -= 4) {
        unsigned int n = (v >> i) & 0xF;
        uart_putc(n < 10 ? '0' + n : 'A' + n - 10);
    }
}

static void gpmi_wait_done(void) {
    while (GPMI_CTRL0 & CTRL0_RUN);
}

static void gpmi_send_cmd(unsigned int mode, unsigned int addr,
                          unsigned int count, unsigned int data) {
    GPMI_DATA = data;
    /* Ensure GPMI is enabled (not in reset or clock gated) */
    GPMI_CTRL0 = 0;
    GPMI_CTRL0 = (mode << CTRL0_COMMAND_MODE_SHIFT) |
                 (addr << CTRL0_ADDRESS_SHIFT) |
                 (count & CTRL0_XFER_COUNT_MASK) |
                 CTRL0_RUN;
    gpmi_wait_done();
}

static unsigned int gpmi_read_data(void) {
    return GPMI_DATA;
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
    unsigned int id0, id1, id2, id3, id4;

    UART_CR = CR_UARTEN | CR_TXE;
    uart_puts("GPMI NAND READ ID test\n");

    /* Take GPMI out of reset */
    GPMI_CTRL0 = 0;

    /* Read ID: 0x90 command */
    gpmi_send_cmd(COMMAND_MODE_WRITE, ADDRESS_CLE, 1, NAND_CMD_READ_ID);
    /* Read ID: 0x00 address */
    gpmi_send_cmd(COMMAND_MODE_WRITE, ADDRESS_ALE, 1, 0x00);
    /* Read 5 ID bytes */
    gpmi_send_cmd(COMMAND_MODE_READ, ADDRESS_DATA, 5, 0);

    id0 = gpmi_read_data() & 0xFF;
    id1 = gpmi_read_data() & 0xFF;
    id2 = gpmi_read_data() & 0xFF;
    id3 = gpmi_read_data() & 0xFF;
    id4 = gpmi_read_data() & 0xFF;

    uart_puts("ID: ");
    uart_puthex(id0); uart_putc(' ');
    uart_puthex(id1); uart_putc(' ');
    uart_puthex(id2); uart_putc(' ');
    uart_puthex(id3); uart_putc(' ');
    uart_puthex(id4); uart_puts("\n");

    if (id0 == 0xEC) {
        uart_puts("PASS\n");
    } else {
        uart_puts("FAIL\n");
    }
}
