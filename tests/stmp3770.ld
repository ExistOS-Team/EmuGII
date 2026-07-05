/* Linker script for STMP3770 bare-metal program */

MEMORY
{
    SRAM (rwx) : ORIGIN = 0x00000000, LENGTH = 512K
    DRAM (rwx) : ORIGIN = 0x40000000, LENGTH = 128M
}

ENTRY(_start)

SECTIONS
{
    . = 0x40000000;

    .text : {
        *(.text.startup)
        *(.text)
        *(.text.*)
        *(.rodata)
        *(.rodata.*)
    } > DRAM

    .data : {
        *(.data)
        *(.data.*)
    } > DRAM

    .bss : {
        *(.bss)
        *(.bss.*)
        *(COMMON)
    } > DRAM

    /DISCARD/ : {
        *(.ARM.exidx)
        *(.ARM.attributes)
        *(.comment)
    }
}
