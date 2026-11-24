.section .init,"ax",@progbits
.global _start
_start:
    csrci mstatus, 8
    csrw mie, zero
    .word 0x0000500f
    fence rw, rw
    .word 0x0000100f
    .option push
    .option norelax
    la gp, __global_pointer$
    .option pop
    la sp, _sp
    la t0, trap
    csrw mtvec, t0
    la a0, __bss_start
    la a1, __bss_end
1:  bgeu a0, a1, 2f
    sw zero, 0(a0)
    addi a0, a0, 4
    j 1b
2:  call loader_main
.align 2
trap:
    li t0, 0x00c0f000
    csrr t1, mcause
    sw t1, 0(t0)
    csrr t1, mepc
    sw t1, 4(t0)
    csrr t1, mtval
    sw t1, 8(t0)
3:  j 3b
