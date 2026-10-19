#!/usr/bin/python3
"""chain_search.py - can the seven piece masks share bytes?

A piece is a 4x4 mask in a 16-bit word (nibble r = row r, bit c = column c). If the table is read with an unaligned
word load at offset i (0..6), consecutive pieces share a byte: a table of N+1 bytes instead of 2N. The rotation turns the
mask inside its 4x4 box, so ANY orientation and position of a piece inside the box is a valid way to store it.
This finds byte strings b0..b7 such that the 7 overlapping words b[i] | b[i+1] << 8 are the 7 different tetrominoes."""
import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from tetris_model import classify                                           # noqa: E402

masks = {}                                                                  # 16-bit mask -> piece class
for m in range(1 << 16):
    if bin(m).count('1') == 4:
        cells = {(b // 4, b % 4) for b in range(16) if m >> b & 1}
        cls = classify(cells)
        if cls:
            masks[m] = cls
print(len(masks), 'tetromino masks in a 4x4 box')

by_first = {}                                                               # low byte -> [(high byte, class)]
for m, cls in masks.items():
    by_first.setdefault(m & 255, []).append((m >> 8, cls))

solutions = []


def dfs(chain, used):
    if len(used) == 7:
        solutions.append(tuple(chain))
        return
    for hi, cls in by_first.get(chain[-1], []):
        if cls not in used:
            chain.append(hi)
            used.append(cls)
            dfs(chain, used)
            used.pop()
            chain.pop()


for first in sorted(by_first):
    dfs([first], [])
print(len(solutions), 'chains of 8 bytes')
for s in solutions[:12]:
    words = [s[i] | s[i + 1] << 8 for i in range(7)]
    print(' '.join(f'{b:02x}' for b in s), ' pieces:', ''.join(masks[w] for w in words))


# ---- relaxation: windows may repeat a piece (a longer chain, some pieces more likely) -------------------------------
def shortest_covering():
    """Fewest bytes such that the overlapping words (stride 1) include all 7 tetrominoes. BFS over (last byte, pieces seen)."""
    from collections import deque
    start = [((b,), frozenset()) for b in range(256)]
    seen = {}
    q = deque()
    for chain, cov in start:
        seen[(chain[-1], cov)] = chain
        q.append((chain, cov))
    while q:
        chain, cov = q.popleft()
        if len(cov) == 7:
            return chain
        for hi, cls in by_first.get(chain[-1], []):
            ncov = cov | {cls}
            key = (hi, ncov)
            if key not in seen:
                seen[key] = chain + (hi,)
                q.append((chain + (hi,), ncov))
    return None


best = shortest_covering()
if best:
    words = [best[i] | best[i + 1] << 8 for i in range(len(best) - 1)]
    print('shortest covering chain:', len(best), 'bytes:', ' '.join(f'{b:02x}' for b in best), ''.join(masks.get(w, '?') for w in words))
