# RV32I register-immediate ALU sweep
        addi  x1, x0, 5
        addi  x2, x0, 9
        add   x3, x1, x2          # 14
        sub   x4, x1, x2          # -4
        slt   x5, x1, x2          # 1
        slt   x6, x2, x1          # 0
        sltu  x7, x0, x1          # 1 (0 < 5)
        xori  x8, x1, 3           # 6
        ori   x9, x1, 2           # 7
        andi  x10, x1, 3          # 1
        slli  x11, x1, 2          # 20
        srli  x12, x11, 1         # 10
        srai  x13, x4, 1          # -2
        addi  x14, x0, -1
        srli  x15, x14, 28        # 15
        srai  x16, x14, 3         # -1
        xori  x17, x0, -1         # all ones
        sltu  x18, x17, x0        # 0
        slt   x19, x17, x0        # 1
        li    x20, 4096           # li expansion check (lui x20, 1)
        lui   x21, 1              # 0x1000
        addi  x21, x21, -1        # 0xFFF
        auipc x22, 0              # pc of this auipc
        slti  x23, x17, 0         # 1
        sltiu x24, x17, 0         # 0
        and   x25, x17, x1        # 5
        or    x26, x25, x2        # 13
        xor   x27, x26, x1        # 8
        sll   x28, x1, x2         # 5<<9 = 2560
        srl   x29, x28, x1        # 80
        sra   x30, x4, x1         # -1
        slt   x31, x4, x0         # 1
        ebreak
