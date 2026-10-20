"""tetris_model.py - the rules of Tetris as plain Python sets of (row, col) cells: what the tests judge programs by."""

W = 10  # well width every program is expected to have

BASE = {  # one orientation of each tetromino, as (row, col)
    'I': {(0, 0), (0, 1), (0, 2), (0, 3)},
    'O': {(0, 0), (0, 1), (1, 0), (1, 1)},
    'T': {(0, 0), (0, 1), (0, 2), (1, 1)},
    'S': {(0, 1), (0, 2), (1, 0), (1, 1)},
    'Z': {(0, 0), (0, 1), (1, 1), (1, 2)},
    'J': {(0, 0), (1, 0), (1, 1), (1, 2)},
    'L': {(0, 2), (1, 0), (1, 1), (1, 2)},
}


def norm(cells):
    """Shift a shape so its top-left corner is (0, 0)."""
    r0 = min(r for r, _ in cells)
    c0 = min(c for _, c in cells)
    return frozenset((r - r0, c - c0) for r, c in cells)


def rotate_cw(cells):
    return norm({(c, -r) for r, c in cells})


def orientations(cells):
    """All distinct orientations (by rotation only; a mirror image is a different piece), normalised."""
    out, cur = [], norm(cells)
    for _ in range(4):
        if cur not in out:
            out.append(cur)
        cur = rotate_cw(cur)
    return out


CLASSES = {}  # normalised orientation -> piece name
for _name, _cells in BASE.items():
    for _o in orientations(_cells):
        CLASSES[_o] = _name


def classify(cells):
    """'I'..'L' if the cells are exactly one tetromino in some orientation, else None."""
    return CLASSES.get(norm(cells)) if len(cells) == 4 else None


def drop(settled, piece, rows):
    """Let `piece` fall straight down until it rests on `settled` or the floor (row index `rows`)."""
    piece = set(piece)
    while all(r + 1 < rows and (r + 1, c) not in settled for r, c in piece):
        piece = {(r + 1, c) for r, c in piece}
    return piece


def clear_lines(cells, rows):
    """Remove full rows and let everything above fall. Returns (cells, number of rows removed)."""
    full = [r for r in range(rows) if all((r, c) in cells for c in range(W))]
    if not full:
        return set(cells), 0
    out = set()
    for r, c in cells:
        if r in full:
            continue
        out.add((r + sum(1 for f in full if f > r), c))
    return out, len(full)


def land(settled, piece, rows):
    """The board after `piece` is dropped and settles, and how many rows that cleared."""
    return clear_lines(set(settled) | drop(settled, piece, rows), rows)
