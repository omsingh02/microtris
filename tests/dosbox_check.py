#!/usr/bin/python3
"""dosbox_check.py - play the .COM in the real DOSBox and hold it to the same rules as the VM tests.

    python3 -I tests/dosbox_check.py <program.com> <adapter> [--pieces N] [--cycles N]

A cross-check by a different implementation of the PC. Checks: a piece appears; gravity; it reaches both walls; it
rotates (4 presses = back to the start); then a bot plays N pieces and every landing is compared with the reference
rules, including full rows going. Not deterministic (real time, the program's own random pieces)."""
import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
from features import BASE, Fail, Game, W, bot_choice, norm, orientations, picture, place    # noqa: E402
from adapters import ADAPTERS                                                               # noqa: E402
from dosbox_machine import DosboxMachine                                                    # noqa: E402


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('com')
    p.add_argument('adapter', choices=sorted(ADAPTERS))
    p.add_argument('--pieces', type=int, default=30)
    p.add_argument('--cycles', type=int, default=2000)
    p.add_argument('--wait', type=float, default=0.15)
    p.add_argument('--seed', type=int, default=1)
    a = p.parse_args(argv)
    ad = ADAPTERS[a.adapter]
    m = DosboxMachine(a.com, cycles=a.cycles, wait=a.wait)
    t0 = time.time()
    try:
        g = Game(a.com, ad, machine=m)
        print(f'DOSBox: first piece is a {g.cls}, at rows {g.top()}..{g.bottom()}, columns {g.minc()}..{g.maxc()}')
        start = g.top()
        for _ in range(60):
            g.step()
            if g.top() > start or g.landed():
                break
        if g.top() <= start and not g.landed():
            raise Fail('the piece did not fall by itself')
        print(f'DOSBox: gravity ok (piece fell from row {start} to row {g.top()})')
        for key, name, col in ((ad.left, 'left', 0), (ad.right, 'right', W - 1)):
            for _ in range(14):
                g.step(key)
                if g.landed():
                    break
            edge = g.minc() if name == 'left' else g.maxc()
            print(f'DOSBox: after 14 {name} presses the piece is at columns {g.minc()}..{g.maxc()}')
            if not g.landed() and edge != col:
                raise Fail(f'did not reach the {name} wall')
        if not g.landed():
            shapes = [norm(g.piece)]
            for _ in range(4):
                g.step(ad.rotate)
                if g.landed():
                    break
                shapes.append(norm(g.piece))
            if len(shapes) == 5:
                want = len(orientations(BASE[g.cls]))
                print(f'DOSBox: rotation shows {len(set(shapes))} shapes for a {g.cls} (should be {want}); 4 presses back to start: {shapes[0] == shapes[4]}')
                if len(set(shapes)) != want or shapes[0] != shapes[4]:
                    raise Fail('rotation is wrong')
        g.run_until_landing()
        rng = random.Random(a.seed)
        done = 0
        for i in range(a.pieces):
            oi, col = bot_choice(g.settled, g.cls, ad.rows, rng, explore=0.1)
            place(g, orientations(BASE[g.cls])[oi], col)
            done += 1
        hist = {k: g.cleared.count(k) for k in range(5)}
        print(f'DOSBox: {done} bot-placed pieces, every landing matched the rules; rows cleared per landing {hist}')
        print(picture(g.settled | g.piece, ad.rows, g.piece))
        print(f'DOSBox cross-check PASSED in {time.time() - t0:.0f}s')
        return 0
    except Fail as e:
        print(f'DOSBox cross-check FAILED: {e}')
        return 1
    finally:
        m.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
