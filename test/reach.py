#!/usr/bin/python3
"""reach.py - every position a piece can reach in microtris on an empty well, checked for lost cells.

    python3 -I test/reach.py build/microtris.com

The program shifts a 4x4 mask left by CL, and a count outside 0..15 throws every cell away; a lost cell never collides
(tinytris loses a vertical I at the right wall this way). Breadth-first search over (mask, CL, row) with the program's
own rules (move = CL +/- 1 as a byte, rotate = the column gather, fall = one row); at every state all 4 cells must exist
and lie inside the well. An empty well is enough: blocks only take positions away. This models the code and does not
run it: the piece table is read from the .COM, the layout constants are repeated here, and fuzz.py runs the binary."""

import sys

WELL_LO, WELL_HI = 4, 13  # bit numbers of the well in the row word (bit 14 is the left wall)
ROW_EMPTY, FLOOR_ROW, ROWS = 0x400F, 0xFFFF, 24
SPAWN_CL = 7


def rotate(mask):
    out = 0
    for col in range(4):
        ax = (mask >> col) & 0x1111
        ax = (ax * 0x1248) & 0xFFFF
        out = ((out << 4) | (ax >> 12)) & 0xFFFF
    return out


def shifted_rows(mask, cl, row):
    """The (board row, bits) pairs the test routine ANDs, with the shift as the CPU does it (count & 31, 16 bits)."""
    out = []
    r = row
    while mask:
        out.append((r, ((mask & 0xF) << (cl & 31)) & 0xFFFF))
        mask >>= 4
        r += 1
    return out


def collides(mask, cl, row):
    for r, bits in shifted_rows(mask, cl, row):
        board = FLOOR_ROW if r >= ROWS else ROW_EMPTY
        if bits & board:
            return True
    return False


def main(path):
    with open(path, 'rb') as f:
        table = f.read()[-7:]
    seen_all = {}
    for piece in table:
        start = (piece, SPAWN_CL, 0)
        assert not collides(*start), 'spawn collides'
        seen, todo = {start}, [start]
        while todo:
            mask, cl, row = todo.pop()
            cells = 0
            for _, bits in shifted_rows(mask, cl, row):
                cells += bin(bits).count('1')
                if bits & ~(((1 << (WELL_HI + 1)) - 1) & ~((1 << WELL_LO) - 1)):
                    raise SystemExit(f'piece {piece:02X}: cells outside the well at mask {mask:04X} cl {cl} row {row}')
            if cells != 4:
                raise SystemExit(f'piece {piece:02X}: only {cells} cells left at mask {mask:04X} cl {cl} row {row}')
            for nxt in (
                (mask, (cl + 1) & 255, row),
                (mask, (cl - 1) & 255, row),
                (rotate(mask), cl, row),
                (mask, cl, row + 1),
            ):
                if nxt not in seen and not collides(*nxt):
                    seen.add(nxt)
                    todo.append(nxt)
        seen_all[piece] = len(seen)
    print(
        f'{path}: all positions of all 7 pieces are whole and inside the well: '
        + ', '.join(f'{p:02X}:{n}' for p, n in seen_all.items())
        + ' states'
    )


if __name__ == '__main__':
    main(sys.argv[1])
