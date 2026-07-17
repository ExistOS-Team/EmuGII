/*
 * USB PHY + USB OTG controller register test for STMP3770 QEMU
 */



#include "common/uart.h"
#define USBPHY_BASE  0x8007C000
#define USB_BASE     0x80080000




static int failures;

static void check_eq(const char *name, unsigned int got, unsigned int exp) {
    if (got != exp) {
        failures++;
        uart_puts("FAIL ");
        uart_puts(name);
        uart_puts(" got ");
        uart_puthex(got);
        uart_puts(" expected ");
        uart_puthex(exp);
        uart_putc('\n');
    }
}

void _start(void) __attribute__((section(".text.startup"), naked));
void _start(void) {
    __asm__ volatile (
        "ldr sp, =0x00080000\n\t"
        "bl run_tests\n\t"
        "b .\n\t"
    );
}

void run_tests(void) {
    volatile unsigned int *usbphy_ctrl0  = (volatile unsigned int *)(USBPHY_BASE + 0x00);
    volatile unsigned int *usbphy_ctrl0_clr = (volatile unsigned int *)(USBPHY_BASE + 0x08);
    volatile unsigned int *usbphy_status = (volatile unsigned int *)(USBPHY_BASE + 0x10);
    volatile unsigned int *usbphy_version = (volatile unsigned int *)(USBPHY_BASE + 0x30);

    volatile unsigned int *usb_id      = (volatile unsigned int *)(USB_BASE + 0x000);
    volatile unsigned int *usb_usbcmd  = (volatile unsigned int *)(USB_BASE + 0x140);
    volatile unsigned int *usb_usbsts  = (volatile unsigned int *)(USB_BASE + 0x144);
    volatile unsigned int *usb_dccparams = (volatile unsigned int *)(USB_BASE + 0x124);
    volatile unsigned int *usb_portsc1 = (volatile unsigned int *)(USB_BASE + 0x184);
    volatile unsigned int *usb_usbmode = (volatile unsigned int *)(USB_BASE + 0x1A8);

    UART_CR = CR_UARTEN | CR_TXE;
    failures = 0;

    uart_puts("STMP3770 USB test\n");

    /* USB PHY tests */
    check_eq("USBPHY VERSION", *usbphy_version, 0x43000000);
    check_eq("USBPHY CTRL0 reset", *usbphy_ctrl0, 0xC0000000);
    *usbphy_ctrl0_clr = 0xC0000000;
    check_eq("USBPHY CTRL0 after clear", *usbphy_ctrl0, 0);
    check_eq("USBPHY STATUS", *usbphy_status, (1 << 2) | (1 << 0));

    /* USB controller tests */
    check_eq("USB ID", *usb_id, 0x01000000);
    check_eq("USB DCCPARAMS", *usb_dccparams, 0x88);
    check_eq("USB USBMODE", *usb_usbmode, 2);
    check_eq("USB PORTSC1", *usb_portsc1, 0x1005);
    check_eq("USB USBSTS reset", *usb_usbsts, (1 << 6));

    *usb_usbsts = (1 << 6);  /* write-1-to-clear URI */
    check_eq("USB USBSTS after clear", *usb_usbsts, 0);

    *usb_usbcmd = (1 << 1);  /* reset */
    check_eq("USB USBCMD after reset", *usb_usbcmd, 0);
    check_eq("USB USBSTS after cmd reset", *usb_usbsts, (1 << 6));

    if (failures == 0)
        uart_puts("USB TEST PASS\n");
    else
        uart_puts("USB TEST FAIL\n");
}
