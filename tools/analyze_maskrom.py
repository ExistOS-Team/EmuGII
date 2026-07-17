#!/usr/bin/env python3
"""Analyze STMP3770 mask ROM content for boot loader logic extraction."""

import os
import struct
import sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

ROM_SIZE = 0x10000
ROM_BASE = 0xFFFF0000

def load_rom(path):
    with open(path, 'rb') as f:
        return f.read()

def disasm(data, offset, count=32, base=ROM_BASE):
    """Disassemble ARM instructions at given file offset."""
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    code = data[offset:offset + count * 4]
    for insn in md.disasm(code, base + offset):
        print(f"  0x{insn.address:08X}: 0x{struct.unpack('<I', insn.bytes[:4])[0]:08X}  {insn.mnemonic:8s} {insn.op_str}")

def find_strings(data, min_len=4):
    """Find ASCII strings in ROM data."""
    strings = []
    i = 0
    while i < len(data):
        if 0x20 <= data[i] < 0x7F:
            start = i
            while i < len(data) and 0x20 <= data[i] < 0x7F:
                i += 1
            if i - start >= min_len:
                s = data[start:i].decode('ascii')
                strings.append((start, s))
        else:
            i += 1
    return strings

def find_bl_targets(data, base=ROM_BASE):
    """Find all BL (branch-link) targets to identify function calls."""
    targets = {}
    for i in range(0, len(data) - 4, 4):
        w = struct.unpack_from('<I', data, i)[0]
        # BL instruction: 0xEBxxxxxx
        if (w & 0xFF000000) == 0xEB000000:
            offset = w & 0x00FFFFFF
            if offset & 0x00800000:
                offset |= 0xFF000000  # sign extend
            target = base + i + 8 + (offset << 2)
            target &= 0xFFFFFFFF
            if base <= target < base + len(data):
                targets.setdefault(target, []).append(base + i)
    return targets

def find_b_targets(data, base=ROM_BASE):
    """Find all B (branch) targets."""
    targets = {}
    for i in range(0, len(data) - 4, 4):
        w = struct.unpack_from('<I', data, i)[0]
        # B instruction: 0xEAxxxxxx
        if (w & 0xFF000000) == 0xEA000000:
            offset = w & 0x00FFFFFF
            if offset & 0x00800000:
                offset |= 0xFF000000
            target = base + i + 8 + (offset << 2)
            target &= 0xFFFFFFFF
            if base <= target < base + len(data):
                targets.setdefault(target, []).append(base + i)
    return targets

def analyze_exception_vectors(data):
    """Analyze ARM exception vector table."""
    labels = ['Reset', 'Undef', 'SWI', 'PAbort', 'DAbort', 'Reserved', 'IRQ', 'FIQ']
    print("=" * 60)
    print("Exception Vector Table")
    print("=" * 60)
    handlers = []
    for i in range(8):
        w = struct.unpack_from('<I', data, i * 4)[0]
        addr = struct.unpack_from('<I', data, 0x20 + i * 4)[0]
        print(f"  {labels[i]:10s}: vector=0x{w:08X}  handler=0x{addr:08X}")
        handlers.append(addr)
    return handlers

def analyze_function_calls(data, base=ROM_BASE):
    """Analyze function call graph."""
    print("\n" + "=" * 60)
    print("Function Call Analysis (BL targets)")
    print("=" * 60)
    bl_targets = find_bl_targets(data, base)
    # Sort by number of callers (most called functions first)
    for target, callers in sorted(bl_targets.items(), key=lambda x: -len(x[1])):
        off = target - base
        print(f"  0x{target:08X} (off 0x{off:04X}): called {len(callers)} times")

def analyze_boot_signatures(data):
    """Find boot-related signatures."""
    print("\n" + "=" * 60)
    print("Boot Signatures")
    print("=" * 60)
    signatures = [
        (b'STMP', 'STMP NCB signature'),
        (b'NCB', 'NCB (NAND Control Block)'),
        (b'LDLB', 'LDLB (Logical Data Load Block)'),
        (b'DBBT', 'DBBT (Discovered Bad Block Table)'),
        (b'RBI', 'RBI (ROM Boot Image)'),
    ]
    for sig, desc in signatures:
        idx = 0
        while True:
            idx = data.find(sig, idx)
            if idx < 0:
                break
            # Show context
            context = data[idx:idx + 32]
            print(f"  0x{ROM_BASE + idx:08X} (off 0x{idx:04X}): {desc}")
            print(f"    Context: {context[:16].hex()}")
            idx += 1

def analyze_strings(data):
    """Find and display meaningful strings."""
    print("\n" + "=" * 60)
    print("ASCII Strings (length >= 4)")
    print("=" * 60)
    strings = find_strings(data, min_len=4)
    for off, s in strings:
        if len(s) >= 4:
            print(f"  0x{ROM_BASE + off:08X} (off 0x{off:04X}): {s!r}")

def analyze_reset_handler(data):
    """Disassemble reset handler."""
    print("\n" + "=" * 60)
    print("Reset Handler Disassembly")
    print("=" * 60)
    reset_addr = struct.unpack_from('<I', data, 0x20)[0]
    reset_off = reset_addr - ROM_BASE
    print(f"Reset handler at 0x{reset_addr:08X} (file offset 0x{reset_off:04X}):")
    disasm(data, reset_off, 64)

def analyze_irq_handler(data):
    """Disassemble IRQ handler."""
    print("\n" + "=" * 60)
    print("IRQ Handler Disassembly")
    print("=" * 60)
    irq_addr = struct.unpack_from('<I', data, 0x20 + 6 * 4)[0]
    irq_off = irq_addr - ROM_BASE
    print(f"IRQ handler at 0x{irq_addr:08X} (file offset 0x{irq_off:04X}):")
    disasm(data, irq_off, 32)

def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Downloads/maskrom64K')
    data = load_rom(rom_path)

    print(f"ROM size: {len(data)} bytes")
    print(f"ROM base: 0x{ROM_BASE:08X}")

    # Analyze exception vectors
    handlers = analyze_exception_vectors(data)

    # Analyze boot signatures
    analyze_boot_signatures(data)

    # Analyze strings
    analyze_strings(data)

    # Analyze function calls
    analyze_function_calls(data)

    # Disassemble reset handler
    analyze_reset_handler(data)

    # Disassemble IRQ handler
    analyze_irq_handler(data)

    # Disassemble around STMP signature
    print("\n" + "=" * 60)
    print("Code around STMP signature (0x2A50)")
    print("=" * 60)
    disasm(data, 0x2A40, 32)

    # Disassemble around NCB/LDLB/DBBT signatures
    print("\n" + "=" * 60)
    print("Data around NCB/LDLB/DBBT signatures (0xBA00)")
    print("=" * 60)
    for off in range(0xBA00, 0xBA40, 4):
        if off + 4 <= len(data):
            w = struct.unpack_from('<I', data, off)[0]
            print(f"  0x{ROM_BASE + off:08X}: 0x{w:08X}")

if __name__ == '__main__':
    main()
