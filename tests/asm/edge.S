# Edge cases: sub-word stores on every byte lane, JALR LSB masking,
# back-to-back taken branches, a branch depending on an in-flight load,
# load->use chains at distance 1/2/3, and x0 as a destination.
main:
    la   x10, data

    # --- stores on every byte lane, read back ---
    li   x1, 0x11
    sb   x1, 0(x10)
    li   x2, 0x22
    sb   x2, 1(x10)
    li   x3, 0x33
    sb   x3, 2(x10)
    li   x4, 0x44
    sb   x4, 3(x10)
    lw   x5, 0(x10)              # 0x44332211
    li   x6, 0x5566
    sh   x6, 4(x10)
    lh   x7, 4(x10)              # 0x00005566
    li   x8, 0xf0e0
    sh   x8, 6(x10)
    lh   x9, 6(x10)              # sign-extended fff0e0 -> 0xfffff0e0
    lhu  x7, 6(x10)              # 0x0000f0e0

    # --- ALU forwarding chain (distance 1 producers) ---
    li   x1, 7
    add  x2, x1, x1              # 14
    add  x3, x2, x2              # 28
    add  x4, x3, x1              # 35

    # --- load->use at distance 1 (stall), 2 and 3 ---
    sw   x1, 8(x10)
    lw   x11, 8(x10)             # 7
    add  x12, x11, x11           # distance 1 -> 14
    add  x13, x12, x11           # 21
    lw   x14, 8(x10)
    addi x15, x0, 1
    add  x16, x14, x15           # distance 2 -> 8
    lw   x17, 8(x10)
    addi x18, x0, 2
    addi x19, x0, 3
    add  x20, x17, x18           # distance 3 -> 9

    # --- back-to-back taken branches ---
    li   x1, 3
    li   x2, 5
    beq  x1, x1, t1
    addi x0, x0, 111             # all of these are skipped
t1: bne  x1, x2, t2
    addi x0, x0, 222
t2: blt  x1, x2, t3
    addi x0, x0, 333
t3: bge  x1, x1, t4
    addi x0, x0, 444
t4: bltu x1, x2, t5
    addi x0, x0, 555
t5: bgeu x2, x1, t6
    addi x0, x0, 666
t6:

    # --- branch on a load that is still in flight ---
    lw   x21, 8(x10)
    beq  x21, x21, bhit          # load-use stall, then redirect
    addi x0, x0, 777
bhit:

    # --- JALR with an odd target: bit 0 must be ignored ---
    la   x22, even
    ori  x22, x22, 1
    jalr x0, 0(x22)
    addi x0, x0, 888             # skipped
even:

    # --- x0 destination never writes and never forwards ---
    li   x23, 9
    addi x0, x23, 1
    addi x24, x0, 5              # reads x0 = 5
    add  x25, x23, x0            # 9 + 0 = 9

    ebreak
loop:
    j loop

    .section .data
    .align 2
data:
    .space 128
