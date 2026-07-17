#!/usr/bin/env python3
"""Decode constant pool values and peripheral addresses in STMP3770 mask ROM."""
import os
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

ROM_BASE = 0xFFFF0000

def ror(val, n):
    n = n % 32
    return ((val >> n) | (val << (32 - n))) & 0xFFFFFFFF

def decode_arm_imm(w):
    """Decode ARM immediate operand from instruction word."""
    imm = w & 0xFF
    rot = (w >> 8) & 0xF
    return ror(imm, rot * 2)

def load_rom(path):
    with open(path, 'rb') as f:
        return f.read()

# STMP3770 peripheral address map
PERIPHERALS = {
    0x80000000: 'ICOLL',
    0x80004000: 'APBH_DMA',
    0x80008000: 'ECC8/BCH',
    0x8000C000: 'GPMI',
    0x80010000: 'SSP1',
    0x80018000: 'PINCTRL',
    0x8001C000: 'DIGCTL',
    0x80020000: 'ELCDIF?',
    0x80024000: 'APBX_DMA',
    0x80028000: 'DCP',
    0x8002C000: 'OCOTP',
    0x80030000: 'LCDIF',
    0x80034000: 'SSP2',
    0x80040000: 'CLKCTRL',
    0x80044000: 'POWER',
    0x80048000: 'AUDIOOUT',
    0x8004C000: 'AUDIOIN',
    0x80050000: 'LRADC',
    0x80058000: 'I2C',
    0x8005C000: 'RTC',
    0x80064000: 'PWM',
    0x80068000: 'TIMERS',
    0x8006C000: 'APPUART',
    0x80070000: 'DBGUART',
    0x8007C000: 'USBPHY',
    0x80080000: 'USB',
    0x800C0000: 'DFLPT',
}

def identify_addr(addr):
    """Identify which peripheral a address belongs to."""
    for base, name in sorted(PERIPHERALS.items()):
        if addr >= base and addr < base + 0x4000:
            offset = addr - base
            return f'{name}+0x{offset:03X}'
    if 0xFFFF0000 <= addr <= 0xFFFFFFFF:
        return f'OCROM+0x{addr - 0xFFFF0000:04X}'
    return f'0x{addr:08X}'

def analyze_ldr_pool(data, func_offset, func_size):
    """Find LDR [pc, #imm] instructions and decode their constant pool values."""
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    code = data[func_offset:func_offset + func_size * 4]

    print(f'\nConstant pool references:')
    for insn in md.disasm(code, ROM_BASE + func_offset):
        if insn.mnemonic == 'ldr' and '[pc' in insn.op_str:
            # Extract PC-relative offset
            # PC = insn.address + 8
            pc = insn.address + 8
            # Parse offset from op_str like "r0, [pc, #0x198]"
            import re
            m = re.search(r'#(0x[0-9a-fA-F]+|\d+)', insn.op_str)
            if m:
                off_str = m.group(1)
                off = int(off_str, 0)
                pool_addr = pc + off
                pool_off = pool_addr - ROM_BASE
                if pool_off + 4 <= len(data):
                    val = struct.unpack_from('<I', data, pool_off)[0]
                    desc = identify_addr(val)
                    print(f'  0x{insn.address:08X}: {insn.mnemonic} {insn.op_str:30s} -> pool@0x{pool_addr:08X} = 0x{val:08X} ({desc})')

def analyze_str_targets(data, func_offset, func_size):
    """Find STR instructions and trace back the address computation."""
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    code = data[func_offset:func_offset + func_size * 4]

    reg_vals = {}

    print(f'\nMemory writes (STR):')
    for insn in md.disasm(code, ROM_BASE + func_offset):
        # Track MOV and ADD with immediates
        if insn.mnemonic == 'mov' and insn.op_str.startswith('r') and '#' in insn.op_str:
            import re
            m = re.match(r'(r\d+), #(\d+), #(\d+)', insn.op_str)
            if m:
                reg = m.group(1)
                imm = int(m.group(2))
                rot = int(m.group(3))
                reg_vals[reg] = ror(imm, rot)
        elif insn.mnemonic == 'add' and '#' in insn.op_str:
            import re
            m = re.match(r'(r\d+), (r\d+), #(\d+), #(\d+)', insn.op_str)
            if m:
                dst = m.group(1)
                src = m.group(2)
                imm = int(m.group(3))
                rot = int(m.group(4))
                if src in reg_vals:
                    reg_vals[dst] = (reg_vals[src] + ror(imm, rot)) & 0xFFFFFFFF
        elif insn.mnemonic == 'str':
            # Try to identify the target address
            import re
            m = re.match(r'(r\d+), \[(r\d+)\]', insn.op_str)
            if m:
                src_reg = m.group(1)
                dst_reg = m.group(2)
                if dst_reg in reg_vals:
                    addr = reg_vals[dst_reg]
                    desc = identify_addr(addr)
                    src_val = reg_vals.get(src_reg, None)
                    src_desc = f'0x{src_val:08X}' if src_val is not None else src_reg
                    print(f'  0x{insn.address:08X}: str {src_reg}({src_desc}) -> [{dst_reg}] = 0x{addr:08X} ({desc})')

def main():
    data = load_rom(os.path.expanduser('~/Downloads/maskrom64K'))

    # Analyze reset handler peripheral writes
    print('=' * 60)
    print('Reset Handler Peripheral Initialization')
    print('=' * 60)
    analyze_str_targets(data, 0x2338, 30)

    # Analyze init_func_1 (0x15A4)
    print('\n' + '=' * 60)
    print('init_func_1 (0xFFFF15A4)')
    print('=' * 60)
    analyze_ldr_pool(data, 0x15A4, 30)
    analyze_str_targets(data, 0x15A4, 30)

    # Analyze init_func_2 (0x1858) - UART init?
    print('\n' + '=' * 60)
    print('init_func_2 (0xFFFF1858) - UART/clock init')
    print('=' * 60)
    analyze_ldr_pool(data, 0x1858, 60)
    analyze_str_targets(data, 0x1858, 60)

    # Analyze init_func_7 (0x1CA4) - complex init
    print('\n' + '=' * 60)
    print('init_func_7 (0xFFFF1CA4) - boot mode/clock init')
    print('=' * 60)
    analyze_ldr_pool(data, 0x1CA4, 120)
    analyze_str_targets(data, 0x1CA4, 120)

    # Analyze main_boot (0x2590)
    print('\n' + '=' * 60)
    print('main_boot (0xFFFF2590)')
    print('=' * 60)
    analyze_ldr_pool(data, 0x2590, 200)

    # Analyze the NCB/LDLB/DBBT data area
    print('\n' + '=' * 60)
    print('Boot signature data area (0xBA00)')
    print('=' * 60)
    sigs = [
        (0xBA00, 'NCB chunk tag'),
        (0xBA04, 'STMP NCB signature'),
        (0xBA08, 'NCB RBI'),
        (0xBA0C, 'RBI NCB'),
        (0xBA10, 'STMP LDLB'),
        (0xBA14, 'LDLB RBI'),
        (0xBA18, 'RBI LDLB'),
        (0xBA1C, 'STMP DBBT'),
        (0xBA20, 'DBBT RBI'),
        (0xBA24, 'RBI DBBT'),
    ]
    for off, desc in sigs:
        if off + 4 <= len(data):
            w = struct.unpack_from('<I', data, off)[0]
            ascii_repr = data[off:off+4].decode('ascii', errors='replace')
            print(f'  0x{ROM_BASE + off:08X}: 0x{w:08X} ({ascii_repr!r}) - {desc}')

    # Decode the NCB structure at 0xBA28+
    print('\nNCB/DBBT pointer table:')
    for i in range(8):
        off = 0xBA28 + i * 4
        if off + 4 <= len(data):
            w = struct.unpack_from('<I', data, off)[0]
            print(f'  0x{ROM_BASE + off:08X}: 0x{w:08X} ({identify_addr(w)})')

    # Check the 1MB maskromread_block file
    print('\n' + '=' * 60)
    print('Checking maskromread_block (3) - 1MB file')
    print('=' * 60)
    with open(os.path.expanduser('~/Downloads/maskromread_block (3)'), 'rb') as f:
        block_data = f.read(4096)  # Read first 4KB
    print(f'First 32 bytes: {block_data[:32].hex()}')
    # Check if it starts with NCB signature
    for sig, name in [(b'STMP', 'STMP'), (b'NCB', 'NCB'), (b'LDLB', 'LDLB'), (b'DBBT', 'DBBT')]:
        idx = block_data.find(sig)
        if idx >= 0:
            print(f'  Found {name} at offset 0x{idx:04X}')

    # Check OSLoader.sb
    print('\n' + '=' * 60)
    print('Checking OSLoader.sb')
    print('=' * 60)
    with open(os.path.expanduser('~/Downloads/OSLoader.sb'), 'rb') as f:
        sb_data = f.read(256)
    print(f'Size: {len(open(os.path.expanduser("~/Downloads/OSLoader.sb"), "rb").read())} bytes')
    print(f'First 32 bytes: {sb_data[:32].hex()}')
    # SB file header starts with signature bytes
    # Check for SB signature (usually starts with 0x00 or specific magic)
    for sig, name in [(b'STMP', 'STMP'), (b'stgt', 'sgtl'), (b'fsgt', 'fsgtl')]:
        idx = sb_data.find(sig)
        if idx >= 0:
            print(f'  Found {name!r} at offset 0x{idx:04X}')

if __name__ == '__main__':
    main()
