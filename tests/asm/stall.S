# Hazard stress: back-to-back dependent ALU ops (register file bypass path)
# and interleaved load-use sequences (1-cycle stall path).
main:
    la   x10, data               # data base (position-independent)
    li   x1, 3
    li   x2, 4
    li   x3, 5

    # pure ALU dependency chain (each depends on previous)
    add  x4, x1, x2
    add  x5, x4, x3
    add  x6, x5, x4
    sub  x7, x6, x5
    and  x8, x6, x7
    or   x9, x8, x1
    xor  x11, x9, x2
    sll  x12, x11, x1
    srl  x13, x12, x2

    # load-use chains
    sw   x13, 0(x10)
    lw   x14, 0(x10)
    add  x15, x14, x14           # stalls on x14
    add  x16, x15, x15           # stalls chain continues
    lw   x17, 0(x10)
    lw   x18, 0(x10)
    add  x19, x17, x18           # both loads stall
    sub  x20, x19, x16

    # store followed by load to same address ( forwarding through RAM )
    li   x21, 0xabcd1234
    sw   x21, 4(x10)
    lw   x22, 4(x10)
    add  x23, x22, x0

    # branch right after dependent loads
    lw   x24, 0(x10)
    lw   x25, 4(x10)
    add  x26, x24, x25
    beq  x26, x0, fail           # must not be taken
    li   x31, 1
    sw   x31, 8(x10)
    ebreak
fail:
    ebreak

    .section .data
    .align 2
data:
    .space 128
