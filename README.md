# microtris

A complete Tetris in a **209-byte** DOS `.COM` file. The program I measured it against, [pellsson/tinytris](https://github.com/pellsson/tinytris),
is 247 bytes.

| program | bytes | seven pieces | gravity | move | rotate | line clear | game over |
|---|---:|:-:|:-:|:-:|:-:|:-:|:-:|
| tinytris (pellsson) | 247 | yes | yes | yes | yes | yes | freeze |
| **microtris** | **209** | yes | yes | yes | yes | yes | freeze |

"Complete" means those six things, each tested black-box from the screen against a reference model, on both programs
with the same harness. The rules, and why the line is drawn there, are in [RULES.md](RULES.md). There is no official
record body for this; the claim is "209 bytes, all six features, `make verify` says so", and the rules are written so that
you can disagree with them precisely.

```
$ make
build/microtris.com: 209 bytes
```

Keys: `j` left, `l` right, `k` rotate. Nothing else does anything. The fall speed is the CPU's speed, as in the original,
because there is no timer in it; in DOSBox use a fixed cycle count (the tests use `cycles=fixed 400`, which is about a row
a second; I have not play-tested it for feel). When the stack reaches the top the program freezes with the final board
on screen; reset the emulator.

## How it got smaller

It is pellsson's design: one 16-bit word per row for the board, a piece as a 4x4 bit mask, one routine that tests, stamps
and erases by patching its own opcode, a collision result carried in the zero flag, undo through the stack. The changes:

- **Rotation by multiplication.** A column of the 4x4 mask is gathered into a nibble with one `and` and one `imul 0x1248`
  (the partial products never meet), four times round: 27 bytes instead of 46.
- **One byte per piece.** Every tetromino fits in two rows of its box, so the table is 7 bytes read with `xlat`, not 14.
- **The colour comes from the flags.** After `test [bx],dx`, `lahf` already holds an attribute byte whose bit 6 is "was
  empty". Red well, black blocks and walls, no compare, no jump.
- **The board starts at offset 0** (the first 50 bytes of the PSP), so the row-shift loop ends when `si` hits 0 and a
  negative `si` can mean game over.
- Smaller things: `xor` for both stamp and erase, `jmp` instead of a pushed return address, the shared routine zeroes
  its own accumulator, the board is walked with `lodsw`, a full restart of the scan after a clear.

The well is laid out so that a shifted-out piece can never look free; see below, because that is where the holder is wrong.

## What the harness found in the holder

The holder passes all six checks. Two further checks found real defects in it ([notes](notes/holder-analysis.md)); the
first is shared by my first layouts and the second was in my own build until the footprint check caught it:

1. **A vertical I vanishes at the right wall.** `l` once too often takes the column shift to 0xFF; the CPU masks the count
   and every cell shifts out, and a cell that is not there can never collide. `tests/fuzz.py` (random keys, every frame
   judged) shows it, `make holder-bug` reproduces it. microtris moves the well so that shift 0 is never a legal position,
   and `tools/reach.py` proves by exhaustive search that no reachable position loses a cell.
2. **The draw loop overruns.** `dec cx / jae` never ends the loop (`dec` leaves the carry flag alone); it ends when the
   screen pointer wraps, about 410 rows later. The holder writes roughly 64 KB over the B800 segment every frame, the
   unused text pages and the video ROM area above them. The emulator I check with maps all of memory as RAM, so the six
   feature checks cannot see it; `tests/footprint.py` can. The overrun is also most of the holder's time per frame, so it
   sets the holder's fall speed. microtris draws 25 rows and spends the time in the gravity counter instead (315,265 instructions per row of fall,
   the holder: 355,481).

I have not reported either upstream.

## Verify it yourself

Needs `nasm`, `python-unicorn`, `python-capstone`; `make dosbox` also needs `dosbox`, `xdotool`, `xorg-server-xvfb`, `imagemagick`.

```
make verify              # fetches tinytris.com (sha256 checked), then on both programs:
                         #   the six feature checks, an 80186 check on the code, and for microtris also
                         #   exhaustive piece-position search, random-key fuzzing, a memory-footprint check
make -j4 -Otarget robust # the same with zeroed registers, other load segments, other seeds
make dosbox              # microtris under real DOSBox on a private X display, a second implementation of DOS
make holder-bug          # the holder's two defects
make lint                # ruff, pylint, vulture, bandit, codespell, typos on the Python and the docs
```

The deterministic harness is a small real-mode x86 machine on [Unicorn](https://www.unicorn-engine.org/) (`tools/dosvm.py`):
no wall clock, a scripted keyboard, a scripted timer port. DOSBox is the cross-check, not the judge.

## What this does not claim

- Not a record held by anyone's authority. It is a number, a rule set and a harness you can run.
- Not hardware-tested: simulation plus one emulator.
- 80186 instructions (`pusha`, `imul r,r,imm`, shifts by immediate), like the holder; `aam 7` does not mean base 7 on a
  NEC V20/V30, also like the holder.
- The program never returns to DOS (its board sits on top of the PSP), and the screen is not cleared first.
- Prior art I know: tinytris (247), 4is256 (256, with scoring and colours), the Hugi Compo #22 winner (363), TetrOS (446).
  If you know of a complete Tetris below 209 bytes, I would like to hear of it.

## Credit and provenance

The design is [pellsson](https://github.com/pellsson)'s; 62 of the 112 instruction lines in `src/microtris.asm` are
his, in the same order (difflib over the instruction text, comments ignored). His `tinytris.com` is not in this repo: the upstream repo has no licence, so `make verify` fetches
it and checks the sha256.

This project was written with Claude Code (Anthropic's coding assistant). The design choices, the rules and the numbers
are in the repo, and everything it claims is checked by `make verify`, which is the part that does not depend on who wrote what.
