"""adapters.py - how to read a program's well off the screen, and which keys it uses.

An adapter is the only program-specific part of the test suite. `well(vm)` returns the playfield as rows of 10 booleans
(True = a block, whether settled or falling); walls and floor are not part of it. Keys are named by what they do on
screen: `left` moves the piece toward the left edge of the screen."""


class Adapter:
    def __init__(self, name, well, left, right, rotate, rows):
        self.name, self.well, self.left, self.right, self.rotate, self.rows = name, well, left, right, rotate, rows


def _tinytris_well(vm):
    # 13 cells of two characters, attribute 0x44 = block. Cell 0 is the right wall (bit 12), cells 1..10 the well.
    scr = vm.screen()
    return [[scr[r][2 * (1 + c)][1] == 0x44 for c in range(10)] for r in range(24)]


def _microtris_well(vm):
    # 15 cells of two characters (bit 14 = left wall, bits 13..4 the well, bits 3..0 the right wall). A cell is empty when the background has the red bit (attribute bit 6, which the
    # program takes from ZF), a block when it has not. Cell 0 is the left wall, cells 1..10 the well.
    scr = vm.screen()
    return [[not scr[r][2 * (1 + c)][1] & 0x40 for c in range(10)] for r in range(24)]


TINYTRIS = Adapter('tinytris', _tinytris_well, left='j', right='l', rotate='k', rows=24)

MICROTRIS = Adapter('microtris', _microtris_well, left='j', right='l', rotate='k', rows=24)

ADAPTERS = {'tinytris': TINYTRIS, 'microtris': MICROTRIS}
