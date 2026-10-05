# CSR read/write/set/clear + mscratch round trip (m-mode only)
main:
    li   x1, 0x55aa55aa
    csrw mscratch, x1
    csrr x2, mscratch            # x2 = 0x55aa55aa
    li   x3, 0x0f0f0f0f
    csrw mscratch, x3
    csrrwi x0, mscratch, 5       # mscratch = 5
    csrrci x4, mscratch, 5       # x4 = 5, clear bits -> 0
    csrr x5, mscratch            # 0
    li   x6, 0b1010
    csrw mscratch, x6
    csrrsi x7, mscratch, 0b0101  # x7 = 0b1010, set -> 0b1111
    csrr x8, mscratch            # 0b1111
    csrrci x9, mscratch, 0b1111  # x9 = 0b1111 -> mscratch = 0
    csrr x10, mscratch           # 0
    ebreak
l:
    j l
