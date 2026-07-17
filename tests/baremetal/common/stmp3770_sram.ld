/* Linker script for STMP3770 bare-metal tests loaded at SRAM base. */

MEMORY
{
    SRAM (rwx) : ORIGIN = 0x00000000, LENGTH = 512K
}

ENTRY(_start)

SECTIONS
{
    . = 0x00000000;

    .text : {
        *(.text.startup)
        *(.text)
        *(.text.*)
        *(.rodata)
        *(.rodata.*)
    } > SRAM

    .data : {
        *(.data)
        *(.data.*)
    } > SRAM

    .bss : {
        *(.bss)
        *(.bss.*)
        *(COMMON)
    } > SRAM

    /DISCARD/ : {
        *(.ARM.exidx)
        *(.ARM.attributes)
        *(.comment)
    }
}
