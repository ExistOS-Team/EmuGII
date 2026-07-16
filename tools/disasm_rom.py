#!/usr/bin/env python3
"""Disassemble specific functions from STMP3770 mask ROM."""
import struct
import sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

ROM_BASE = 0xFFFF0000

def load_rom(path):
    with open(path, 'rb') as f:
        return f.read()

def disasm_func(data, offset, max_insns=200, name=None):
    """Disassemble a function, stopping at likely return instructions."""
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    code = data[offset:offset + max_insns * 4]
    label = name or f'0x{ROM_BASE + offset:08X}'
    print(f'\n{"=" * 60}')
    print(f'Function {label} (offset 0x{offset:04X})')
    print(f'{"=" * 60}')
    count = 0
    for insn in md.disasm(code, ROM_BASE + offset):
        raw = struct.unpack_from('<I', data, insn.address - ROM_BASE)[0]
        print(f'  0x{insn.address:08X}: 0x{raw:08X}  {insn.mnemonic:8s} {insn.op_str}')
        count += 1
        # Stop at BX LR or POP {..., PC} (function return)
        if insn.mnemonic == 'bx' and 'lr' in insn.op_str:
            break
        if insn.mnemonic == 'pop' and 'pc' in insn.op_str:
            break
        if count >= max_insns:
            print(f'  ... (truncated at {max_insns} instructions)')
            break

def disasm_range(data, offset, count, name=None):
    """Disassemble a fixed number of instructions."""
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    code = data[offset:offset + count * 4]
    label = name or f'0x{ROM_BASE + offset:08X}'
    print(f'\n{"=" * 60}')
    print(f'Code range {label} (offset 0x{offset:04X}, {count} insns)')
    print(f'{"=" * 60}')
    for insn in md.disasm(code, ROM_BASE + offset):
        raw = struct.unpack_from('<I', data, insn.address - ROM_BASE)[0]
        print(f'  0x{insn.address:08X}: 0x{raw:08X}  {insn.mnemonic:8s} {insn.op_str}')

def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else 'D:/UserData/Downloads/maskrom64K'
    data = load_rom(rom_path)

    # Key functions from reset handler call chain
    funcs = [
        (0x15A4, 'init_func_1'),
        (0x1858, 'init_func_2'),
        (0x1518, 'init_func_3'),
        (0x1538, 'init_func_4'),
        (0x154C, 'init_func_5'),
        (0x1554, 'init_func_6'),
        (0x1CA4, 'init_func_7'),
        (0x2264, 'init_func_8'),
        (0x21F4, 'init_func_9'),
        (0x15FC, 'init_func_10'),
        (0x2590, 'main_boot'),
        (0x197C, 'print_func'),
    ]

    for off, name in funcs:
        disasm_func(data, off, 80, name)

    # Also disassemble the most-called functions
    hot_funcs = [
        (0x193C, 'hot_func_20x'),  # called 20 times
        (0x0530, 'hot_func_18x'),  # called 18 times
        (0x2038, 'hot_func_7x'),   # called 7 times
        (0x0F68, 'hot_func_5x'),   # called 5 times
    ]
    for off, name in hot_funcs:
        disasm_func(data, off, 60, name)

if __name__ == '__main__':
    main()
