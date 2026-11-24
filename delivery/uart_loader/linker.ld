OUTPUT_ARCH("riscv")
ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0x00c00000, LENGTH = 64K }
SECTIONS {
 .init : { KEEP(*(.init)) } > ram
 .text : { *(.text .text.*) } > ram
 .rodata : { *(.rodata .rodata.*) } > ram
 .data : ALIGN(4) { *(.data .data.*) PROVIDE(__global_pointer$ = . + 0x800); *(.sdata .sdata.*) } > ram
 .bss (NOLOAD) : ALIGN(4) { __bss_start = .; *(.bss .bss.* .sbss .sbss.* COMMON) . = ALIGN(4); __bss_end = .; } > ram
 .stack (NOLOAD) : ALIGN(16) { . += 8K; _sp = .; } > ram
 ASSERT(_sp <= ORIGIN(ram)+LENGTH(ram), "UART loader exceeds scratch DDR")
 /DISCARD/ : { *(.eh_frame .eh_frame.*) *(.comment) }
}
