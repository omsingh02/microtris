#!/usr/bin/python3
"""speed.py - instructions executed per row of fall. The programs have no timer, so this is their speed.

    python3 -I test/speed.py <program.com> <adapter> [--rows N]"""

import argparse
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from adapters import ADAPTERS  # noqa: E402
from dosvm import DosVM  # noqa: E402
from features import cells_of  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('com')
    p.add_argument('adapter', choices=sorted(ADAPTERS))
    p.add_argument('--rows', type=int, default=4, help='rows of fall to time')
    a = p.parse_args(argv)
    with open(a.com, 'rb') as f:
        vm = DosVM(f.read(), seed=5)
    ad = ADAPTERS[a.adapter]
    executed = [0]

    def count(uc, addr, size, _):
        executed[0] += 1

    vm.uc.hook_add(UC_HOOK_CODE, count)
    gaps, top, mark = [], None, 0
    for _ in range(20000):
        vm.frame()
        now = min(r for r, _ in cells_of(ad.well(vm)))
        if top is not None and now != top:
            gaps.append(executed[0] - mark)
            mark = executed[0]
            if len(gaps) > a.rows:
                break
        top = now
    gaps = gaps[1:]  # the first gap starts somewhere inside a row
    if not gaps:
        print(f'{a.com}: the piece never moved')
        return 1
    print(f'{a.com}: {statistics.median(gaps):,.0f} instructions per row of fall (rows timed: {gaps})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
