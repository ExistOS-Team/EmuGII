/*
 * NAND ID Read Test
 * 验证 GPMI 命令/地址处理和 ID 读取功能
 */

#include <stdint.h>

#define APBH_BASE       0x80004000
#define GPMI_BASE       0x8000C000

#define HW_APBH_CTRL0           (*(volatile uint32_t *)(APBH_BASE + 0x000))
#define HW_APBH_CTRL0_CLR       (*(volatile uint32_t *)(APBH_BASE + 0x008))
#define HW_APBH_CH4_NXTCMDAR    (*(volatile uint32_t *)(APBH_BASE + 0x160))
#define HW_APBH_CH4_SEMA        (*(volatile uint32_t *)(APBH_BASE + 0x180))

#define HW_GPMI_CTRL0           (*(volatile uint32_t *)(GPMI_BASE + 0x000))
#define HW_GPMI_CTRL0_CLR       (*(volatile uint32_t *)(GPMI_BASE + 0x008))

#define UART_BASE       0x80070000
#define UART_DR         (*(volatile uint32_t *)(UART_BASE + 0x000))
#define UART_FR         (*(volatile uint32_t *)(UART_BASE + 0x018))

typedef struct {
    uint32_t nxtcmdar;
    uint32_t cmd;
    uint32_t bar;
    uint32_t ctrl0;
    uint32_t compare;
    uint32_t eccctrl;
} gpmi_dma_desc_t;

static uint8_t cmd_buf[8] __attribute__((aligned(4)));
static uint8_t id_buf[8] __attribute__((aligned(4)));
static gpmi_dma_desc_t desc[3] __attribute__((aligned(16)));

void uart_putc(char c) {
    while (UART_FR & 0x20);
    UART_DR = c;
}

void uart_puts(const char *s) {
    while (*s) uart_putc(*s++);
}

static const char hex[] = "0123456789abcdef";

void uart_puthex(uint32_t val) {
    for (int i = 7; i >= 0; i--) {
        uart_putc(hex[(val >> (i * 4)) & 0xF]);
    }
}

void delay(int n) {
    for (volatile int i = 0; i < n * 1000; i++);
}

int main(void) {
    uart_puts("NAND ID Test\r\n");

    // 清除 APBH/GPMI 复位和时钟门控
    HW_APBH_CTRL0_CLR = (1U << 31) | (1U << 30) | (0x10 << 8);
    HW_GPMI_CTRL0_CLR = (1U << 31) | (1U << 30);
    delay(10);

    // 准备命令缓冲区：0x90 (READ_ID) + 0x00 (地址)
    cmd_buf[0] = 0x90;
    cmd_buf[1] = 0x00;

    // 描述符 1: 发送命令+地址 (DMA_READ, memory->NAND)
    desc[0].nxtcmdar = (uint32_t)&desc[1];
    desc[0].cmd      = (2 << 16) |        // XFER_COUNT=2
                       (3 << 12) |        // CMDWORDS=3
                       (1 << 7) |         // WAIT4ENDCMD
                       (1 << 4) |         // NANDLOCK
                       (1 << 2) |         // CHAIN
                       (2 << 0);          // COMMAND=DMA_READ
    desc[0].bar      = (uint32_t)cmd_buf;
    desc[0].ctrl0    = (1 << 24) |        // COMMAND_MODE=WRITE
                       (8 << 16) |        // WORD_LENGTH=8bit
                       (0 << 8) |         // CS=0
                       (2 << 4) |         // ADDRESS=CLE
                       (1 << 3) |         // ADDRESS_INCREMENT
                       (2 << 0);          // XFER_COUNT=2
    desc[0].compare  = 0;
    desc[0].eccctrl  = 0;

    // 描述符 2: 读取 ID (DMA_WRITE, NAND->memory)
    desc[1].nxtcmdar = (uint32_t)&desc[2];
    desc[1].cmd      = (6 << 16) |        // XFER_COUNT=6
                       (3 << 12) |        // CMDWORDS=3
                       (1 << 3) |         // IRQONCMPLT
                       (1 << 6) |         // SEMAPHORE
                       (1 << 2) |         // CHAIN
                       (1 << 0);          // COMMAND=DMA_WRITE
    desc[1].bar      = (uint32_t)id_buf;
    desc[1].ctrl0    = (2 << 24) |        // COMMAND_MODE=READ
                       (8 << 16) |        // WORD_LENGTH=8bit
                       (0 << 8) |         // CS=0
                       (0 << 4) |         // ADDRESS=DATA
                       (6 << 0);          // XFER_COUNT=6
    desc[1].compare  = 0;
    desc[1].eccctrl  = 0;

    // 描述符 3: 终止
    desc[2].nxtcmdar = 0;
    desc[2].cmd      = (1 << 3) | (1 << 6); // IRQONCMPLT | SEMAPHORE
    desc[2].bar      = 0;

    // 启动 DMA 链
    HW_APBH_CH4_NXTCMDAR = (uint32_t)&desc[0];
    HW_APBH_CH4_SEMA = 1;

    // 等待完成（轮询信号量）
    uart_puts("Waiting for DMA...\r\n");
    int timeout = 100000;
    while ((HW_APBH_CH4_SEMA & 0xFF0000) > 0 && timeout-- > 0);

    if (timeout <= 0) {
        uart_puts("TIMEOUT!\r\n");
        return 1;
    }

    // 显示结果
    uart_puts("NAND ID: ");
    for (int i = 0; i < 6; i++) {
        if (i > 0) uart_putc(' ');
        uart_putc(hex[(id_buf[i] >> 4) & 0xF]);
        uart_putc(hex[id_buf[i] & 0xF]);
    }
    uart_puts("\r\n");

    // 验证预期值
    if (id_buf[0] == 0xEC && id_buf[3] == 0x95) {
        uart_puts("SUCCESS: ID matches expected Samsung NAND\r\n");
        return 0;
    } else {
        uart_puts("FAIL: ID mismatch\r\n");
        return 1;
    }
}
