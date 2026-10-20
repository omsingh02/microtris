#!/usr/bin/python3
"""features.py - does this .COM really play Tetris? Six checks, from outside: only the screen and the keyboard.

    python3 -I test/features.py <program.com> <adapter> [--pieces N] [--seed N]

Everything is deterministic: same program + same arguments = same verdict, on any machine. See RULES.md, section 3.
How it works: a tracker follows the falling piece and the settled stack on the screen frame by frame. Whenever a
piece lands, the board is compared with what the reference rules (test/tetris_model.py) say it must be, including
removal of full rows. A bot plays pieces to exercise this; scripted scenarios hit the 1-, 2-, 3- and 4-row clears."""

import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from adapters import ADAPTERS  # noqa: E402
from dosvm import DosVM  # noqa: E402
from tetris_model import BASE, W, classify, land, norm, orientations  # noqa: E402


class Fail(Exception):
    pass


class Stopped(Fail):
    """The program stopped asking for keys (a freeze, an exit, a fault). Whether that fails depends on the stack."""


def cells_of(well):
    return {(r, c) for r, row in enumerate(well) for c, v in enumerate(row) if v}


def picture(cells, rows, mark=None):
    mark = mark or set()
    return '\n'.join(
        f'{r:2} ' + ''.join('@' if (r, c) in mark else '#' if (r, c) in cells else '.' for c in range(W))
        for r in range(rows)
    )


def indent(text):
    return '\n'.join('      ' + line for line in text.split('\n'))


class Game:
    """A running program plus a tracker that follows the falling piece and the settled stack on screen, and checks
    every landing against the reference rules. Any disagreement raises Fail with both boards."""

    def __init__(self, com, adapter, seed=1, byte=None, profile='dos', seg=0x1000, machine=None):
        self.ad = adapter
        self.vm = machine or DosVM(
            com, seed=seed, profile=profile, seg=seg
        )  # any object with press(), frame(), screen()
        self.byte = byte  # None: the machine's own pseudo-random stream
        if byte is not None:
            self.vm.pit_fn = lambda: self.byte
        self.settled, self.piece, self.cls = set(), None, None
        self._raw = None  # the last screen, as bytes: a frame that changed nothing needs no decoding
        self.frames = 0
        self.cleared = []  # rows cleared by each landing, in order
        self.last_event = None
        self.step()  # run to the first frame: the first piece is there

    def cells(self):
        return cells_of(self.ad.well(self.vm))

    def top(self):
        return min(r for r, _ in self.piece)

    def bottom(self):
        return max(r for r, _ in self.piece)

    def minc(self):
        return min(c for _, c in self.piece)

    def maxc(self):
        return max(c for _, c in self.piece)

    def landed(self):
        return isinstance(self.last_event, tuple)

    def step(self, *keys):
        """Press keys, run one frame, update the tracker. Returns 'spawn', 'move' or ('land', rows_cleared)."""
        self.vm.press(*keys)
        why = self.vm.frame()
        if why != 'poll':
            raise Stopped(
                f'the program stopped ({why}; exited={self.vm.exited}; fault={self.vm.faulted}) '
                f'after {self.frames} frames'
            )
        self.frames += 1
        raw = bytes(self.vm.vram()) if hasattr(self.vm, 'vram') else None
        if raw is not None and raw == self._raw and self.piece is not None:
            self.last_event = 'move'
            return 'move'
        self._raw = raw
        shown = self.cells()
        if self.piece is None:
            cls = classify(shown)
            if cls is None:
                raise Fail(f'the first frame is not one tetromino:\n{picture(shown, self.ad.rows)}')
            self.piece, self.cls = shown, cls
            self.last_event = 'spawn'
            return 'spawn'
        fresh = shown - self.settled
        if self.settled <= shown and len(fresh) == 4 and classify(fresh) == self.cls:
            self.piece = fresh
            self.last_event = 'move'
            return 'move'
        expect, n = land(self.settled, self.piece, self.ad.rows)
        extra = shown - expect
        if expect <= shown and classify(extra) is not None:
            self.settled, self.piece, self.cls = expect, extra, classify(extra)
            self.cleared.append(n)
            self.last_event = ('land', n)
            return self.last_event
        raise Fail(
            'the board is not what the rules give.\n'
            '  before (the falling piece marked @):\n'
            f'{indent(picture(self.settled | self.piece, self.ad.rows, self.piece))}\n'
            '  rules say, once the piece has landed and full rows have gone:\n'
            f'{indent(picture(expect, self.ad.rows))}\n'
            f'  the screen shows:\n{indent(picture(shown, self.ad.rows))}'
        )

    def run_until_landing(self, limit=4000):
        for _ in range(limit):
            ev = self.step()
            if isinstance(ev, tuple):
                return ev
        raise Fail(f'no piece landed in {limit} frames')


# ---- placing pieces --------------------------------------------------------------------------------------------
def rotate_to(game, want):
    """Press rotate until the falling piece has orientation `want` (normalised). False if it will not get there."""
    for _ in range(5):
        if norm(game.piece) == want:
            return True
        game.step(game.ad.rotate)
        if game.landed():
            return False
    return norm(game.piece) == want


def move_to(game, col, limit=40):
    stuck = 0
    for _ in range(limit):
        if game.minc() == col:
            return True
        before = game.minc()
        game.step(game.ad.left if game.minc() > col else game.ad.right)
        if game.landed():
            return False
        stuck = stuck + 1 if game.minc() == before else 0
        if stuck > 3:
            return False
    return game.minc() == col


def place(game, want, col):
    """Orient the falling piece, slide it to `col`, then let it fall with no keys. Returns the rows it cleared."""
    if not rotate_to(game, want):
        raise Fail(f'could not rotate the {game.cls} piece into {sorted(want)}')
    if not move_to(game, col):
        raise Fail(f'could not move the {game.cls} piece to column {col} (it is at {game.minc()})')
    return game.run_until_landing()[1]


def play(ctx, plan, then=None):
    """plan: [(piece, orientation index, column)]. The random source is set so each piece is the one asked for."""
    g = Game(ctx.com, ctx.ad, byte=ctx.pieces[plan[0][0]], seg=ctx.seg, profile=ctx.profile)
    cleared = []
    for i, (cls, oi, col) in enumerate(plan):
        if g.cls != cls:
            raise Fail(f'asked for a {cls} piece, got a {g.cls}')
        nxt = plan[i + 1][0] if i + 1 < len(plan) else (then or cls)
        g.byte = ctx.pieces[nxt]
        cleared.append(place(g, orientations(BASE[cls])[oi], col))
    return g, cleared


# ---- the bot ---------------------------------------------------------------------------------------------------
def column_heights(cells, rows):
    return [rows - min((r for r, c2 in cells if c2 == c), default=rows) for c in range(W)]


def holes(cells, rows):
    n = 0
    for c in range(W):
        seen = False
        for r in range(rows):
            if (r, c) in cells:
                seen = True
            elif seen:
                n += 1
    return n


def height(cells, rows):
    return max(column_heights(cells, rows))


def bot_score(cells, lines, rows):
    """El-Tetris weights (Yiyuan Lee): few holes, low and even columns, many lines."""
    h = column_heights(cells, rows)
    bump = sum(abs(h[i] - h[i + 1]) for i in range(W - 1))
    return -0.510066 * sum(h) + 0.760666 * lines - 0.35663 * holes(cells, rows) - 0.184483 * bump


def bot_choice(settled, cls, rows, rng, explore):
    options = []
    for oi, o in enumerate(orientations(BASE[cls])):
        w = max(c for _, c in o) + 1
        for col in range(W - w + 1):
            piece = {(r, c + col) for r, c in o}
            after, n = land(settled, piece, rows)
            options.append((bot_score(after, n, rows) + rng.random() * 1e-6, oi, col))
    if rng.random() < explore and height(settled, rows) < 8:
        return rng.choice(options)[1:]
    return max(options)[1:]


# ---- the six checks --------------------------------------------------------------------------------------------
class Ctx:
    def __init__(self, com, ad, seed, pieces_to_play, seg=0x1000, profile='dos'):
        self.com, self.ad, self.seed, self.n, self.seg, self.profile = com, ad, seed, pieces_to_play, seg, profile
        self.pieces = {}  # piece name -> a PIT byte that makes the program spawn it
        self.spawned = {}


def learn_pieces(ctx):
    for b in range(256):
        g = Game(ctx.com, ctx.ad, byte=b, seg=ctx.seg, profile=ctx.profile)
        ctx.pieces.setdefault(g.cls, b)
        ctx.spawned[g.cls] = ctx.spawned.get(g.cls, 0) + 1


def check_pieces(ctx):
    """1. All seven tetrominoes appear; every spawn is exactly one tetromino."""
    missing = set(BASE) - set(ctx.pieces)
    if missing:
        raise Fail(f'pieces never seen: {sorted(missing)}; seen {sorted(ctx.pieces)}')
    spread = ' '.join(f'{k}:{ctx.spawned[k]}' for k in sorted(ctx.spawned))
    return f'all 7 appear; over 256 random-source values the spawns were {spread} (each exactly one tetromino)'


def check_gravity(ctx):
    """2. Gravity: with no keys every piece falls by itself, one row at a time, and lands."""
    drops = []
    for cls, b in sorted(ctx.pieces.items()):
        g = Game(ctx.com, ctx.ad, byte=b, seg=ctx.seg, profile=ctx.profile)
        rows = [g.top()]
        for _ in range(6000):
            if isinstance(g.step(), tuple):
                break
            if g.top() - rows[-1] not in (0, 1):
                raise Fail(f'{cls} piece jumped {g.top() - rows[-1]} rows in one frame')
            rows.append(g.top())
        else:
            raise Fail(f'{cls} piece did not land in 6000 frames (it stopped at row {rows[-1]})')
        if rows[-1] <= rows[0]:
            raise Fail(f'{cls} piece did not fall')
        drops.append(rows[-1] - rows[0])
    return f'every piece fell {min(drops)}..{max(drops)} rows on its own, one row at a time, and landed'


def check_movement(ctx):
    """3. Move left and right; the walls and settled blocks stop the piece."""
    for cls, b in sorted(ctx.pieces.items()):
        g = Game(ctx.com, ctx.ad, byte=b, seg=ctx.seg, profile=ctx.profile)
        for key, name, edge_col in ((g.ad.left, 'left', 0), (g.ad.right, 'right', W - 1)):
            for _ in range(16):
                g.step(key)
                if g.landed():
                    raise Fail(f'{cls}: landed while pressing {name}')
            edge = g.minc() if name == 'left' else g.maxc()
            if edge != edge_col:
                raise Fail(
                    f'{cls}: after 16 presses of {name} the piece spans columns {g.minc()}..{g.maxc()}, not the wall'
                )
    # a tower of three O pieces on the left; an O piece slid into it from the right must stop beside it
    g, _ = play(ctx, [('O', 0, 0)] * 3, then='O')
    tower = {(r, c) for r in range(ctx.ad.rows - 6, ctx.ad.rows) for c in (0, 1)}
    if g.settled != tower:
        raise Fail(f'three O pieces at column 0 did not make a 6-high tower:\n{picture(g.settled, ctx.ad.rows)}')
    for _ in range(4):
        g.step(g.ad.right)
    while g.bottom() < ctx.ad.rows - 6 + 1 and not g.landed():
        g.step()
    if g.landed():
        raise Fail('the O piece landed before it reached the tower')
    for _ in range(6):
        g.step(g.ad.left)
        if g.landed():
            break
    if g.landed():
        raise Fail('the piece landed while it was being pushed against the tower')
    if g.minc() != 2:
        raise Fail(f'pushed against a tower at columns 0-1, the O piece is at column {g.minc()}, not 2')
    return 'every piece reaches both walls and stops; an O piece pushed into a settled tower stops against it'


def check_rotation(ctx):
    """4. Rotation: 4 presses return the shape; a piece keeps its shape and stays in the well at walls and blocks."""
    for cls, b in sorted(ctx.pieces.items()):
        g = Game(ctx.com, ctx.ad, byte=b, seg=ctx.seg, profile=ctx.profile)
        shapes = [norm(g.piece)]
        for _ in range(4):
            g.step(g.ad.rotate)
            if g.landed():
                raise Fail(f'{cls}: landed while rotating')
            shapes.append(norm(g.piece))
        want = len(orientations(BASE[cls]))
        if shapes[0] != shapes[4] or len(set(shapes)) != want:
            raise Fail(
                f'{cls}: 4 rotations gave {len(set(shapes))} distinct shapes and '
                f'{"" if shapes[0] == shapes[4] else "did not "}came back; a {cls} has {want}'
            )
        for key, side in ((g.ad.left, 'left'), (g.ad.right, 'right')):
            for _ in range(12):
                g.step(key)
            for _ in range(5):
                g.step(g.ad.rotate)  # the tracker fails if cells are lost or the shape changes
                if g.landed():
                    break
                if not g.minc() >= 0 and g.maxc() < W:
                    raise Fail(f'{cls}: rotating at the {side} wall pushed the piece out of the well')
    # beside settled blocks: two vertical I pieces at column 0, then rotate every piece in the gap next to them
    for cls in sorted(ctx.pieces):
        g, _ = play(ctx, [('I', 1, 0)] * 2, then=cls)
        for _ in range(2):
            g.step(g.ad.left)
        for _ in range(12 * 5):
            if g.bottom() >= ctx.ad.rows - 8:
                break
            g.step()
        for _ in range(8):
            g.step(g.ad.rotate)
            if g.landed():
                break
            g.step(g.ad.left)
            if g.landed():
                break
    return (
        'every piece has the right number of orientations; 4 presses return to the start; rotating at both walls '
        'and beside a settled stack never loses or moves cells into blocks'
    )


def check_line_clearing(ctx):
    """5. Line clearing: scripted 1-, 2-, 3-, 4-row clears; then a bot plays and every landing is judged."""
    rows = ctx.ad.rows
    # 1 row: I I and an O along the bottom; the O's top half is left, and falls one row
    g, cl = play(ctx, [('I', 0, 0), ('I', 0, 4), ('O', 0, 8)])
    if cl[-1] != 1 or g.settled != {(rows - 1, 8), (rows - 1, 9)}:
        raise Fail(f'1 row: cleared {cl}, board:\n{picture(g.settled, rows)}')
    # 2 rows: five O pieces side by side
    g, cl = play(ctx, [('O', 0, c) for c in (0, 2, 4, 6, 8)])
    if cl[-1] != 2 or g.settled:
        raise Fail(f'2 rows: cleared {cl}, board:\n{picture(g.settled, rows)}')
    # 3 rows: four O (two rows), two flat I on top (third row), two upright I fill the gap and stick up one row
    g, cl = play(ctx, [('O', 0, c) for c in (0, 2, 4, 6)] + [('I', 0, 0), ('I', 0, 4), ('I', 1, 8), ('I', 1, 9)])
    if cl[-1] != 3 or g.settled != {(rows - 1, 8), (rows - 1, 9)}:
        raise Fail(f'3 rows: cleared {cl}, board:\n{picture(g.settled, rows)}')
    # 4 rows: ten upright I pieces side by side
    g, cl = play(ctx, [('I', 1, c) for c in range(10)])
    if cl[-1] != 4 or g.settled:
        raise Fail(f'4 rows: cleared {cl}, board:\n{picture(g.settled, rows)}')
    # the bot. It plays to the program's own game over and then starts the program again; every landing is judged.
    rng = random.Random(ctx.seed)
    hist, topped = dict.fromkeys(range(5), 0), 0
    g = Game(ctx.com, ctx.ad, byte=ctx.pieces[rng.choice(sorted(ctx.pieces))], seg=ctx.seg, profile=ctx.profile)
    for _ in range(ctx.n):
        oi, col = bot_choice(g.settled, g.cls, rows, rng, explore=0.25)
        g.byte = ctx.pieces[rng.choice(sorted(ctx.pieces))]
        try:
            place(g, orientations(BASE[g.cls])[oi], col)
        except Stopped as e:
            if height(g.settled, rows) < rows - 4 or g.vm.faulted:
                raise Fail(f'{e}, with the stack only {height(g.settled, rows)} rows high') from e
            topped += 1  # the stack reached the top: that is game over, not a failure
            for k in range(5):
                hist[k] += g.cleared.count(k)
            g = Game(ctx.com, ctx.ad, byte=ctx.pieces[rng.choice(sorted(ctx.pieces))], seg=ctx.seg, profile=ctx.profile)
    for k in range(5):
        hist[k] += g.cleared.count(k)
    for k in (1, 2):
        if not hist[k]:
            raise Fail(f'the bot never saw a {k}-row clear in {ctx.n} pieces (histogram {hist}); raise --pieces')
    return (
        f'scripted 1-, 2-, 3- and 4-row clears right; then {sum(hist.values())} bot-played landings matched the rules '
        f'(rows cleared per landing: {hist}; the bot topped out {topped}x and the program was started again)'
    )


def game_over_once(ctx, cls):
    """Fill the well with pieces of one kind (cls None: the machine's own random stream) until play stops."""
    vm = DosVM(ctx.com, seg=ctx.seg, profile=ctx.profile)
    if cls is not None:
        vm.pit_fn = lambda: ctx.pieces[cls]
    tallest, last = 0, None
    for _ in range(60000):
        why = vm.frame()
        if why != 'poll':
            break
        raw = bytes(vm.vram())
        if raw != last:  # decode only when the screen changed
            last = raw
            tallest = max(tallest, height(cells_of(ctx.ad.well(vm)), ctx.ad.rows))
    else:
        raise Fail(f'{cls or "random"} pieces, no keys: the pieces never filled the well (60000 frames)')
    if why == 'fault':
        raise Fail(f'{cls or "random"} pieces: the CPU faulted: {vm.faulted}')
    if tallest < ctx.ad.rows - 4:
        raise Fail(f'{cls or "random"} pieces: the program ended ({why}) with the stack only {tallest} rows high')
    if why == 'exited':
        return 'exits to DOS', tallest
    shots = set()
    for _ in range(40):
        vm.run(1237)
        if vm.faulted:
            raise Fail(f'{cls or "random"} pieces: the CPU faulted after game over: {vm.faulted}')
        shots.add(bytes(vm.vram()))
    return ('freezes' if len(shots) == 1 else f'keeps drawing ({len(shots)} different screens in 40 samples)'), tallest


def check_game_over(ctx):
    """6. Game over: a stack that reaches the top ends play cleanly (freeze, exit or restart); no fault, no garbage."""
    outcomes = {}
    for cls in [None, *sorted(ctx.pieces)]:
        state, tallest = game_over_once(ctx, cls)
        outcomes.setdefault(state, []).append(cls or 'random')
    detail = '; '.join(f'{state}: {" ".join(kinds)}' for state, kinds in outcomes.items())
    return (
        f'filled with each piece kind and with random pieces, the stack reached the top ({tallest} rows) '
        f'and the program {detail}; no CPU fault'
    )


CHECKS = [check_pieces, check_gravity, check_movement, check_rotation, check_line_clearing, check_game_over]


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('com')
    p.add_argument('adapter', choices=sorted(ADAPTERS))
    p.add_argument('--pieces', type=int, default=200, help='bot-played pieces in check 5')
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--seg', type=lambda s: int(s, 0), default=0x1000, help='segment the program is loaded at')
    p.add_argument(
        '--profile',
        default='dos',
        choices=['dos', 'zeroed'],
        help="registers at entry: what DOS gives a .COM, or every general register 0",
    )
    p.add_argument('--only', default='', help='comma separated check numbers, e.g. 1,3')
    a = p.parse_args(argv)
    with open(a.com, 'rb') as f:
        com = f.read()
    ctx = Ctx(com, ADAPTERS[a.adapter], a.seed, a.pieces, a.seg, a.profile)
    print(f'{a.com}: {len(com)} bytes, adapter {a.adapter}, seed {a.seed}, load segment {a.seg:04X}')
    t0 = time.time()
    learn_pieces(ctx)
    only = {int(x) for x in a.only.split(',') if x}
    failed = 0
    for i, check in enumerate(CHECKS, 1):
        if only and i not in only:
            continue
        t = time.time()
        try:
            note = check(ctx)
            print(f'  PASS {i}. {check.__doc__.splitlines()[0][3:]}\n         {note}  [{time.time() - t:.1f}s]')
        except Fail as e:
            failed += 1
            print(f'  FAIL {i}. {check.__doc__.splitlines()[0][3:]}\n         {e}  [{time.time() - t:.1f}s]')
    ran = len(only) if only else len(CHECKS)
    verdict = 'ALL SIX FEATURES VERIFIED' if not failed and not only else 'done'
    print(f'{verdict}: {ran - failed} passed, {failed} failed, {time.time() - t0:.0f}s')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
