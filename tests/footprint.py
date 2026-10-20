#!/usr/bin/python3
"""footprint.py - where does the program write? Every store the CPU makes outside the program's own 64 KB segment is checked.

    python3 -I tests/footprint.py <program.com> <adapter> [--seg 0xNNNN] [--frames N]

Extra evidence, not one of the six features. The VM maps all 1 MB as RAM, so a program that scribbles over memory it does
not own would still pass the six checks; this one would not. The program is played with random keys and idle stretches,
then left alone until the stack reaches the top, then watched for a while after game over. Allowed:
  * anywhere in its own segment (PSP, image, stack) - the board lives there, but see the last point,
  * the 4000 bytes of the first text page (B800:0000..0F9F),
and nothing else: not the other text pages, not the video ROM above B800, not low memory, not other segments.
The image may be written at one single address (the opcode byte the shared routine patches); any other store into the
program's own code is reported."""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
sys.path.insert(0, HERE)
from unicorn import UC_HOOK_MEM_WRITE                                          # noqa: E402
from dosvm import DosVM                                                        # noqa: E402
from adapters import ADAPTERS                                                  # noqa: E402

SCREEN, PAGE = 0xB8000, 4000
OTHER_KEYS = ['x', 'a', 'space', 'enter', 'esc', 'up', 'down']


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('com')
    p.add_argument('adapter', choices=sorted(ADAPTERS))
    p.add_argument('--seg', type=lambda s: int(s, 0), default=0x1000)
    p.add_argument('--frames', type=int, default=20000, help='frames of random play before the idle stretch')
    a = p.parse_args(argv)
    with open(a.com, 'rb') as f:
        com = f.read()
    ad = ADAPTERS[a.adapter]
    vm = DosVM(com, seg=a.seg)
    base = a.seg << 4
    image = range(base + 0x100, base + 0x100 + len(com))
    forbidden = {}                                                             # name -> [first (address, size), count]
    image_writes = set()

    def hit(name):
        def cb(uc, access, addr, size, value, _):
            e = forbidden.setdefault(name, [(addr, size), 0])
            e[1] += 1
            if e[1] == 1:
                uc.emu_stop()
        return cb

    def image_cb(uc, access, addr, size, value, _):
        image_writes.update(range(addr, addr + size))

    uc = vm.uc
    uc.hook_add(UC_HOOK_MEM_WRITE, hit('low memory below the segment'), None, 0, base - 1)
    uc.hook_add(UC_HOOK_MEM_WRITE, image_cb, None, image.start, image.stop - 1)
    uc.hook_add(UC_HOOK_MEM_WRITE, hit('between the segment and the screen'), None, base + 0x10000, SCREEN - 1)
    uc.hook_add(UC_HOOK_MEM_WRITE, hit('the screen beyond the first text page, and the video ROM above it'), None,
                SCREEN + PAGE, 0xFFFFF)

    rng = random.Random(7)
    frames = 0
    keys = [ad.left, ad.right, ad.rotate] * 3 + OTHER_KEYS
    for _ in range(a.frames):
        if rng.random() < 0.02:
            vm.press(rng.choice(keys))
        why = vm.frame()
        frames += 1
        if why != 'poll' or forbidden:
            break
    while not forbidden and why == 'poll' and frames < a.frames + 60000:          # no keys: the stack grows to the top
        why = vm.frame()
        frames += 1
    if not forbidden:
        vm.run(300000)                                                          # after game over (a freeze, or whatever it does)
    if forbidden:
        for name, ((addr, size), _) in forbidden.items():
            print(f'{a.com}: FOOTPRINT FAILED: a {size}-byte store to {name}, at linear {addr:#07x} '
                  f'(= {addr >> 4:04X}:{addr & 15:04X}), after {frames} frames')
        return 1
    if vm.faulted:
        print(f'{a.com}: FOOTPRINT FAILED: the CPU faulted: {vm.faulted}')
        return 1
    if len(image_writes) > 1:
        offs = sorted(x - base for x in image_writes)
        print(f'{a.com}: FOOTPRINT FAILED: {len(offs)} different bytes of the program image were written (first {offs[0]:#x})')
        return 1
    patched = ', '.join(f'{x - base:#05x}' for x in sorted(image_writes)) or 'none'
    print(f'{a.com}: {len(com)} bytes, {frames} frames then game over: stores only into its own segment and the first text '
          f'page; code bytes written: {patched}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
