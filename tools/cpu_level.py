#!/usr/bin/python3
"""cpu_level.py - the oldest x86 a .COM program can run on, read from its bytes and from a run.

    python3 -I tools/cpu_level.py <program.com> [--data N] [--max 186]

Two passes, because a static listing alone can be fooled by self-modifying code and by data inside the code:
  1. static: disassemble from 0x100 to the end of the code (the last N bytes of the file are data, default 7: the piece
     table) with capstone in 16-bit mode and put every instruction into a generation by its opcode bytes:
        8086   everything else (with the 8086's own prefixes)
        80186  PUSHA POPA BOUND PUSH imm IMUL r,rm,imm INS/OUTS shift/rotate by imm8 ENTER LEAVE
        286+   an 0F escape (on the 8086 that byte is POP CS)
        386+   an operand-size / address-size / FS / GS prefix (and so 32-bit registers)
  2. dynamic: run the program on the VM for a few thousand frames with random keys, hooking every basic block it
     enters and every store into its own code, so that (a) every block starts on an instruction the static pass
     found, inside the code and not in the data, and (b) the instruction bytes written by self-modifying code are
     classified too.
It also lists the undocumented-but-universal opcodes it finds (AAM/AAD with a base other than 10), which behave the
same on every Intel and AMD part but not on the NEC V20/V30. Exit status 1 if anything needs more than --max
(default 186)."""

import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from capstone import CS_ARCH_X86, CS_MODE_16, Cs  # noqa: E402
from dosvm import DosVM  # noqa: E402
from unicorn import UC_HOOK_BLOCK, UC_HOOK_MEM_WRITE  # noqa: E402

NAMES = {86: '8086', 186: '80186', 286: '80286+', 386: '80386+'}
PREFIX_86 = {0x26, 0x2E, 0x36, 0x3E, 0xF0, 0xF2, 0xF3}  # ES CS SS DS LOCK REPNE REP
ONLY_186 = {0x60, 0x61, 0x62, 0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F, 0xC0, 0xC1, 0xC8, 0xC9}
ORG = 0x100


def generation(raw):
    """(generation, note) of one instruction given as bytes."""
    i = 0
    while i < len(raw) and raw[i] in PREFIX_86:
        i += 1
    op = raw[i]
    if op in (0x64, 0x65, 0x66, 0x67):
        return 386, 'operand/address-size or FS/GS prefix'
    if op == 0x0F:
        return (286 if raw[i + 1] in (0x00, 0x01, 0x02, 0x03, 0x05, 0x06) else 386), '0F escape'
    if op in ONLY_186:
        return 186, ''
    if op in (0xD4, 0xD5) and raw[i + 1] != 10:
        return (
            86,
            f'{"AAM" if op == 0xD4 else "AAD"} with base {raw[i + 1]}: undocumented, same on Intel/AMD, '
            'base fixed at 10 on NEC V20/V30',
        )
    return 86, ''


def classify(md, data, addr):
    insns = list(md.disasm(bytes(data), addr))
    if not insns:
        raise SystemExit(f'cannot disassemble the bytes at {addr:#x}: {bytes(data[:8]).hex()}')
    return insns[0]


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('com')
    p.add_argument('--data', type=int, default=7, help='bytes of data at the end of the file (the piece table)')
    p.add_argument('--max', type=int, default=186, choices=[86, 186, 286, 386])
    p.add_argument('--frames', type=int, default=3000)
    a = p.parse_args(argv)
    with open(a.com, 'rb') as f:
        com = f.read()
    code = com[: len(com) - a.data]
    md = Cs(CS_ARCH_X86, CS_MODE_16)

    # ---- 1. static
    listing = {}
    off = 0
    while off < len(code):
        insn = next(md.disasm(code[off : off + 16], ORG + off), None)
        if insn is None:
            raise SystemExit(
                f'{a.com}: the bytes at {ORG + off:#x} are not an instruction ({code[off : off + 4].hex()})'
            )
        if off + insn.size > len(code):
            raise SystemExit(f'{a.com}: the last instruction runs into the data at {ORG + off:#x}; check --data')
        listing[ORG + off] = (insn.size, insn.mnemonic + ' ' + insn.op_str, bytes(insn.bytes))
        off += insn.size
    found, notes = {}, []
    for addr, (_, text, raw) in listing.items():
        g, note = generation(raw)
        found.setdefault(g, []).append((addr, text, raw))
        if note:
            notes.append((addr, text, note))

    # ---- 2. dynamic
    vm = DosVM(com)
    base = vm.seg << 4
    bad, patched = [], set()

    def block(uc, address, size, _):
        ip = address - base
        if ip not in listing:
            bad.append(ip)
            uc.emu_stop()

    def store(uc, _access, address, size, value, _):
        patched.add((address - base, size, value & ((1 << 8 * size) - 1)))

    vm.uc.hook_add(UC_HOOK_BLOCK, block)
    vm.uc.hook_add(UC_HOOK_MEM_WRITE, store, None, base + ORG, base + ORG + len(com) - 1)
    rng = random.Random(3)
    keys = ['j', 'k', 'l', 'j', 'k', 'l', 'x', 'space', 'enter']
    for _ in range(a.frames):
        if rng.random() < 0.3:
            vm.press(rng.choice(keys))
        if vm.frame() != 'poll' or bad:
            break
    if bad:
        raise SystemExit(
            f'{a.com}: CPU entered {bad[0]:#x}, which is not the start of an instruction of the listing '
            f'(or is in the data)'
        )
    if vm.faulted:
        raise SystemExit(f'{a.com}: the CPU faulted: {vm.faulted}')
    dynamic = []
    for ip, size, value in sorted(patched):
        start = max(s0 for s0 in listing if s0 <= ip)
        if ip + size > start + listing[start][0]:
            raise SystemExit(f'{a.com}: a store at {ip:#x} reaches past the instruction at {start:#x}')
        raw = bytearray(listing[start][2])
        raw[ip - start : ip - start + size] = value.to_bytes(size, 'little')
        insn = classify(md, bytes(raw) + b'\x90' * 8, ORG + start)
        g, _ = generation(bytes(raw))
        dynamic.append((start, bytes(raw), g, insn.mnemonic + ' ' + insn.op_str))
    top = max(list(found) + [g for _, _, g, _ in dynamic])

    print(f'{a.com}: {len(com)} bytes ({len(code)} of code, {a.data} of data), {len(listing)} instructions')
    for g in sorted(found):
        print(f'  {NAMES[g]:7} {len(found[g]):3} instructions')
    for g in sorted(found):
        if g > 86:
            for addr, text, raw in found[g]:
                print(f'          {NAMES[g]:6} {addr:#05x}  {raw.hex():12} {text}')
    for addr, text, note in notes:
        print(f'  note    {addr:#05x}  {text}: {note}')
    for start, img, g, text in dynamic:
        print(
            f'  self-modified at {start:#05x}: the listing has {listing[start][2].hex()} ({listing[start][1]}), '
            f'at run time {img.hex()} ({text}), {NAMES[g]}'
        )
    print(
        f'  dynamic: {a.frames} frames with random keys; every basic block starts on an instruction of the listing, '
        f'none in the data'
    )
    print(f'  => needs {NAMES[top]} (limit {NAMES[a.max]})')
    return 0 if top <= a.max else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
