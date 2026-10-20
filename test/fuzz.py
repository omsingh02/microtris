#!/usr/bin/python3
"""fuzz.py - random keys against a running program, every frame judged from the screen.

    python3 -I test/fuzz.py <program.com> <adapter> [--runs N] [--steps N] [--seed N] [--profile dos|zeroed]
                             [--seg 0xNNNN]

Extra evidence, not one of the six features. After every frame the screen must be the settled stack plus one whole
tetromino; a sideways key moves one column or is really blocked; rotation always turns the same way; other keys change
nothing; a landing agrees with the reference rules. A run ends when the stack gets high, then it starts again."""

import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from adapters import ADAPTERS  # noqa: E402
from features import Fail, Game, height, picture  # noqa: E402
from tetris_model import W, norm, rotate_cw  # noqa: E402

OTHER_KEYS = ['x', 'a', 'space', 'J', 'm', 'left', 'right', 'up', 'down', 'enter', 'esc', '1']


def shifted(cells, dr, dc):
    return {(r + dr, c + dc) for r, c in cells}


def blocked(cells, settled, rows):
    return any(not (0 <= c < W and r < rows) or (r, c) in settled for r, c in cells)


def one_run(com, ad, seed, steps, profile, seg, spin):
    rng = random.Random(seed)
    g = Game(com, ad, seed=seed, profile=profile, seg=seg)
    counts = {
        'left': 0,
        'right': 0,
        'left blocked': 0,
        'right blocked': 0,
        'rotate': 0,
        'rotate blocked': 0,
        'other': 0,
        'landings': 0,
        'frames': 0,
    }

    def judge(key, press):
        """One frame with `press` (or none); True when the stack has got high. Raises Fail on a rule violation."""
        nonlocal spin
        prev, settled = g.piece, g.settled
        ev = g.step(*([press] if press else []))
        counts['frames'] += 1
        if isinstance(ev, tuple):
            counts['landings'] += 1
            return height(g.settled, ad.rows) >= 17
        new = g.piece
        for dr in (0, 1):  # gravity may have dropped it one row in the same frame
            if key in ('left', 'right'):
                dc = 1 if key == 'right' else -1
                if new == shifted(prev, dr, dc):
                    counts[key] += 1
                    return False
                if new == shifted(prev, dr, 0):
                    if not blocked(shifted(prev, dr, dc), settled, ad.rows):
                        raise Fail(
                            f'seed {seed}: {key} was refused with room to move\n'
                            f'{picture(settled | prev, ad.rows, prev)}'
                        )
                    counts[key + ' blocked'] += 1
                    return False
            elif key == 'rotate':
                if new == shifted(prev, dr, 0) or norm(new) == norm(prev):
                    counts['rotate blocked'] += 1
                    return False
                turns = {
                    t
                    for t in ('cw', 'ccw')
                    if norm(new)
                    == (rotate_cw(norm(prev)) if t == 'cw' else rotate_cw(rotate_cw(rotate_cw(norm(prev)))))
                }
                if turns:
                    spin &= turns
                    if not spin:
                        raise Fail(f'seed {seed}: rotation changed direction\n{picture(settled | prev, ad.rows, prev)}')
                    counts['rotate'] += 1
                    return False
            else:
                if new == shifted(prev, dr, 0):
                    counts['other'] += key == 'other'
                    return False
        raise Fail(
            f'seed {seed}: after {key!r} ({press!r}) the piece went from\n'
            f'{picture(settled | prev, ad.rows, prev)}\nto\n{picture(g.settled | new, ad.rows, new)}'
        )

    for _ in range(steps):
        key = rng.choices(['left', 'right', 'rotate', None, 'other'], weights=[4, 4, 3, 3, 1])[0]
        press = {'left': ad.left, 'right': ad.right, 'rotate': ad.rotate, None: None, 'other': rng.choice(OTHER_KEYS)}[
            key
        ]
        if judge(key, press):
            break
        for _ in range(
            rng.choice([0, 0, 0, 0, 8, 32, 128])
        ):  # the piece falls once per ~128 frames: let time pass between keys
            if judge(None, None):
                return counts, spin
    return counts, spin


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('com')
    p.add_argument('adapter', choices=sorted(ADAPTERS))
    p.add_argument('--runs', type=int, default=8)
    p.add_argument('--steps', type=int, default=600)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--profile', default='dos', choices=['dos', 'zeroed'])
    p.add_argument('--seg', type=lambda s: int(s, 0), default=0x1000)
    a = p.parse_args(argv)
    with open(a.com, 'rb') as f:
        com = f.read()
    size = len(com)
    ad = ADAPTERS[a.adapter]
    t0 = time.time()
    total, spin = {}, {'cw', 'ccw'}
    try:
        for i in range(a.runs):
            counts, spin = one_run(com, ad, a.seed + i, a.steps, a.profile, a.seg, spin)
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
    except Fail as e:
        print(f'{a.com}: FUZZ FAILED ({a.profile} registers, segment {a.seg:04X})\n{e}')
        return 1
    print(
        f'{a.com}: {size} bytes, {a.runs} runs x up to {a.steps} key events, {a.profile} registers, '
        f'segment {a.seg:04X}: every frame was one whole piece on the stack; {total}; '
        f'rotation direction {sorted(spin)}  [{time.time() - t0:.0f}s]'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
