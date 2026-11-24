OUTPUT_ARCH("riscv")
ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = YOLO_RAM_ORIGIN, LENGTH = YOLO_RAM_LENGTH }
SECTIONS {
  .init : { KEEP(*(.init)) } > ram
  .text : { *(.text .text.*) } > ram
  .rodata : ALIGN(64) { *(.rodata .rodata.* .srodata .srodata.*) } > ram
  .preinit_array : ALIGN(4) {
    PROVIDE_HIDDEN(__preinit_array_start = .); KEEP(*(.preinit_array))
    PROVIDE_HIDDEN(__preinit_array_end = .);
  } > ram
  .init_array : ALIGN(4) {
    PROVIDE_HIDDEN(__init_array_start = .); KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*))) KEEP(*(.init_array))
    PROVIDE_HIDDEN(__init_array_end = .);
  } > ram
  .fini_array : ALIGN(4) {
    PROVIDE_HIDDEN(__fini_array_start = .); KEEP(*(.fini_array .fini_array.*))
    PROVIDE_HIDDEN(__fini_array_end = .);
  } > ram
  .data : ALIGN(8) {
    *(.data .data.*) PROVIDE(__global_pointer$ = . + 0x800); *(.sdata .sdata.*)
  } > ram
  .bss (NOLOAD) : ALIGN(64) {
    __bss_start = .; *(.bss .bss.* .sbss .sbss.* COMMON) . = ALIGN(64); _end = .; end = .;
  } > ram
  .heap (NOLOAD) : ALIGN(16) { . += 128K; _heap_end = .; } > ram
  .stack (NOLOAD) : ALIGN(64) { _stack_bottom = .; . += 256K; _sp = .; } > ram
  ASSERT(_sp <= ORIGIN(ram) + LENGTH(ram), "YOLO image exceeds reserved software DDR")
  /DISCARD/ : { *(.eh_frame .eh_frame.*) }
}
