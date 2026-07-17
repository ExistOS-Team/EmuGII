/* Linker script for NAND boot payload (loaded at 0x40010000) */

MEMORY
{
    DRAM (rwx) : ORIGIN = 0x40010000, LENGTH = 128M
}

ENTRY(_start)

SECTIONS
{
    . = 0x40010000;

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
