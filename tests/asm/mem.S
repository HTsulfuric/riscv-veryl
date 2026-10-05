# RV32I memory: all widths, sign extension, unaligned-address behaviour
main:
    li   x1, 0x12345678
    li   x2, 0xdeadbeef
    la   x10, data               # data base (in .data, position-independent)

    sw   x1, 0(x10)
    sw   x2, 4(x10)

    lw   x3, 0(x10)              # 0x12345678
    lw   x4, 4(x10)              # 0xdeadbeef

    lb   x5, 0(x10)              # sign-extend byte0 = 0x78
    lbu  x6, 0(x10)              # 0x78
    lb   x7, 1(x10)              # 0x56
    lbu  x8, 1(x10)              # 0x56
    lh   x9, 0(x10)              # 0x5678
    lhu  x11, 2(x10)             # 0x1234

    sb   x2, 8(x10)              # store byte 0xef
    lbu  x12, 8(x10)             # 0xef
    sh   x1, 10(x10)             # store half 0x5678
    lh   x13, 10(x10)            # 0x5678

    # load-use back-to-back (forces stalls)
    lw   x14, 0(x10)
    add  x15, x14, x14
    lw   x16, 4(x10)
    add  x17, x15, x16

    li   x31, 3
    sw   x31, 100(x10)
    ebreak
loop:
    j loop

    .section .data
    .align 2
data:
    .space 128
