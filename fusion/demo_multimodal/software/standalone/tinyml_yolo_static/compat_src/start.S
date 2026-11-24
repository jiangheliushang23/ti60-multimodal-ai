.section .init,"ax",@progbits
.global _start
.type _start,@function
_start:
    csrci mstatus, 8
    csrw mie, zero
#ifndef YOLO_QEMU
    /* Same Sapphire cache synchronization used by the working camera build. */
    .word 0x0000500f
    fence rw, rw
    .word 0x0000100f
    nop
    nop
    nop
#endif
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, _sp
    la t0, compat_trap_entry
    csrw mtvec, t0
    la a0, __bss_start
    la a1, _end
1:  bgeu a0, a1, 2f
    sw zero, 0(a0)
    addi a0, a0, 4
    j 1b
2:
#ifdef YOLO_RAW_REPLAY
    li t0, 0xf8010000
    li t1, 24
    sw t1, 8(t0)
    li t1, 7
    sw t1, 12(t0)
#endif
    call __libc_init_array
    call main
3:  j 3b

.global  compat_trap_entry
.align(2) //mtvec require 32 bits allignement
compat_trap_entry:
  addi sp,sp, -16*4
  sw x1,   0*4(sp)
  sw x5,   1*4(sp)
  sw x6,   2*4(sp)
  sw x7,   3*4(sp)
  sw x10,  4*4(sp)
  sw x11,  5*4(sp)
  sw x12,  6*4(sp)
  sw x13,  7*4(sp)
  sw x14,  8*4(sp)
  sw x15,  9*4(sp)
  sw x16, 10*4(sp)
  sw x17, 11*4(sp)
  sw x28, 12*4(sp)
  sw x29, 13*4(sp)
  sw x30, 14*4(sp)
  sw x31, 15*4(sp)
  call compat_trap
  lw x1 ,  0*4(sp)
  lw x5,   1*4(sp)
  lw x6,   2*4(sp)
  lw x7,   3*4(sp)
  lw x10,  4*4(sp)
  lw x11,  5*4(sp)
  lw x12,  6*4(sp)
  lw x13,  7*4(sp)
  lw x14,  8*4(sp)
  lw x15,  9*4(sp)
  lw x16, 10*4(sp)
  lw x17, 11*4(sp)
  lw x28, 12*4(sp)
  lw x29, 13*4(sp)
  lw x30, 14*4(sp)
  lw x31, 15*4(sp)
  addi sp,sp, 16*4
  mret

.global _init
_init:
    ret
