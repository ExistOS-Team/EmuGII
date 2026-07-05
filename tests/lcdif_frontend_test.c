/*
 * LCDIF frontend test pattern for STMP3770 QEMU.
 *
 * Writes a 256x128 grayscale pattern through the same APBH/LCDIF panel command
 * path used by ExistOS.  The LCD controller addresses X in 3-byte columns, so
 * ExistOS flushes each visible line separately and writes 256 bytes per line.
 * Host-side verification uses QEMU screendump to check that the LCDIF frontend
 * presents those visible bytes on the graphics surface.
 */

#include <stdint.h>

#define UART_BASE 0x80070000
#define UART_DR   (*(volatile uint32_t *)(UART_BASE + 0x00))
#define UART_FR   (*(volatile uint32_t *)(UART_BASE + 0x18))
#define UART_CR   (*(volatile uint32_t *)(UART_BASE + 0x30))

#define UART_FR_TXFF (1U << 5)
#define CR_UARTEN    (1U << 0)
#define CR_TXE       (1U << 8)

#define APBH_BASE 0x80004000
#define APBH_CTRL0           (*(volatile uint32_t *)(APBH_BASE + 0x000))
#define APBH_CTRL0_CLR       (*(volatile uint32_t *)(APBH_BASE + 0x008))
#define APBH_CH_NXTCMDAR(ch) (*(volatile uint32_t *)(APBH_BASE + 0x040 + (ch) * 0x70 + 0x10))
#define APBH_CH_SEMA(ch)     (*(volatile uint32_t *)(APBH_BASE + 0x040 + (ch) * 0x70 + 0x40))

#define LCDIF_BASE 0x80030000
#define LCDIF_CTRL_CLR  (*(volatile uint32_t *)(LCDIF_BASE + 0x008))
#define LCDIF_CTRL1     (*(volatile uint32_t *)(LCDIF_BASE + 0x010))

#define LCDIF_DMA_CH 0

#define DMA_CMD_COMMAND_DMA_WRITE 1U
#define DMA_CMD_COMMAND_DMA_READ  2U
#define DMA_CMD_IRQONCMPLT        (1U << 3)
#define DMA_CMD_SEMAPHORE         (1U << 6)
#define DMA_CMD_CMDWORDS_SHIFT    12
#define DMA_CMD_XFER_COUNT_SHIFT  16

#define LCDIF_CTRL_READ_WRITEB (1U << 29)
#define LCDIF_CTRL_DATA_SELECT (1U << 18)
#define LCDIF_CTRL_WORD_LENGTH (1U << 17)
#define LCDIF_CTRL_RUN         (1U << 16)

#define TEST_DESC_ADDR 0x00004000
#define TEST_CMD_ADDR  0x00005000
#define TEST_DATA_ADDR 0x00006000

#define LCD_W 256
#define LCD_H 128
#define LCD_Y_OFFSET 8

struct dma_desc {
    uint32_t next;
    uint32_t cmd;
    uint32_t bar;
    uint32_t pio[15];
};

static void uart_putc(char c)
{
    while (UART_FR & UART_FR_TXFF) {
    }
    UART_DR = (uint32_t)c;
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

static uint32_t make_dma_cmd(uint32_t command, uint32_t len)
{
    return command |
           DMA_CMD_SEMAPHORE |
           DMA_CMD_IRQONCMPLT |
           (1U << DMA_CMD_CMDWORDS_SHIFT) |
           (len << DMA_CMD_XFER_COUNT_SHIFT);
}

static uint32_t make_lcdif_pio(uint32_t data_select, uint32_t read_write,
                               uint32_t len)
{
    return (len & 0xFFFFU) |
           LCDIF_CTRL_RUN |
           LCDIF_CTRL_WORD_LENGTH |
           (data_select ? LCDIF_CTRL_DATA_SELECT : 0U) |
           (read_write ? LCDIF_CTRL_READ_WRITEB : 0U);
}

static void run_lcdif_dma(uint8_t *buf, uint32_t len,
                          uint32_t data_select, uint32_t read_write)
{
    struct dma_desc *desc = (struct dma_desc *)TEST_DESC_ADDR;

    desc->next = 0;
    desc->cmd = make_dma_cmd(read_write ? DMA_CMD_COMMAND_DMA_WRITE :
                                        DMA_CMD_COMMAND_DMA_READ, len);
    desc->bar = (uint32_t)buf;
    desc->pio[0] = make_lcdif_pio(data_select, read_write, len);

    __asm__ volatile ("" ::: "memory");

    APBH_CTRL0_CLR = (1U << 16) << LCDIF_DMA_CH;
    APBH_CH_NXTCMDAR(LCDIF_DMA_CH) = (uint32_t)desc;
    APBH_CH_SEMA(LCDIF_DMA_CH) = 1;

    while (APBH_CH_SEMA(LCDIF_DMA_CH) & 0xFF0000U) {
    }
}

static void lcd_cmd(uint8_t cmd)
{
    uint8_t *cmd_buf = (uint8_t *)TEST_CMD_ADDR;

    cmd_buf[0] = cmd;
    run_lcdif_dma(cmd_buf, 1, 0, 0);
}

static void lcd_data_write(const uint8_t *src, uint32_t len)
{
    run_lcdif_dma((uint8_t *)src, len, 1, 0);
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
    uint8_t window_x[4] = { 0x00, 0x00, 0x00, 0x55 };
    uint8_t window_y[4];
    uint8_t *pixels = (uint8_t *)TEST_DATA_ADDR;
    uint32_t x;
    uint32_t y;
    uint32_t panel_y;

    UART_CR = CR_UARTEN | CR_TXE;
    APBH_CTRL0 = 0;
    LCDIF_CTRL_CLR = (1U << 31) | (1U << 30);
    LCDIF_CTRL1 = 0;

    for (y = 0; y < LCD_H; y++) {
        for (x = 0; x < LCD_W; x++) {
            pixels[y * LCD_W + x] = (uint8_t)((x ^ (y * 3)) & 0xFF);
        }
    }

    lcd_cmd(0x2A);
    lcd_data_write(window_x, sizeof(window_x));

    for (y = 0; y < LCD_H; y++) {
        panel_y = y + LCD_Y_OFFSET;
        window_y[0] = (uint8_t)(panel_y >> 8);
        window_y[1] = (uint8_t)panel_y;
        window_y[2] = (uint8_t)(panel_y >> 8);
        window_y[3] = (uint8_t)panel_y;

        lcd_cmd(0x2B);
        lcd_data_write(window_y, sizeof(window_y));
        lcd_cmd(0x2C);
        lcd_data_write(&pixels[y * LCD_W], LCD_W);
    }

    uart_puts("LCDIF FRONTEND TEST READY\n");

    while (1) {
    }
}
