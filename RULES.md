# The claim, and the rules it is measured by

**Claim to beat:** the smallest *complete* Tetris, as a 16-bit x86 DOS `.COM` program.
**Holder:** [pellsson/tinytris](https://github.com/pellsson/tinytris), **247 bytes** (`tinytris.com`, sha256 `0cbd70be…4bfa`).
The holder's own README calls it "the first complete Tetris implementation in 256 bytes or less" and says smaller
ones exist but alter the game (usually by dropping or changing pieces). That is the line this project draws too.

There is no official body for this. So the claim is only as good as its rules and how easy they are to re-check.
Everything below is checked by `make verify`, not by eye, and the holder's program runs through the same harness
(`make verify` fetches its `tinytris.com` and checks the sha256 first; the file is not kept in this repo).

## 1. What is measured

- One file, `<name>.COM`. Its size in bytes (`stat -c %s`) is the number. No overlays, no second file, no packer
  stub counted separately: a self-extracting COM is measured as the COM.
- Nothing may be read from outside the file or from DOS/BIOS data that the program did not put there (no loading a
  font, no reading a save file, no reaching into another program's memory). BIOS and DOS *services* are allowed.

## 2. The machine, and what the program relies on

- Real-mode x86, run as a DOS `.COM`: CS=DS=ES=SS=PSP segment, IP=0x100, SP=0xFFFE, colour text mode 80x25 already active
  (video memory at B800:0000), BIOS keyboard services (`INT 16h`), the timer counter at port 0x40.
- The registers DOS gives a `.COM` at entry are **not** relied on: `--profile zeroed` runs everything with every general
  register 0 (`make robust`). (The first scan reads from `SI=0x100` when DOS provides it; it works from 0 as well.)
- The program may be loaded at any segment (`--seg`, `make robust`).
- **The first 50 bytes of the PSP are the board.** microtris overwrites the PSP's `INT 20h`, memory size and termination
  vectors (the holder's board also runs into the PSP: its rows start at 0xFFFE and wrap round to 0x0000..0x002D). It
  therefore never returns to DOS: game
  over is a deliberate freeze with the final board on screen, and the machine (or emulator) is reset. Check 6 accepts
  freeze, exit or restart; microtris freezes, on purpose, because a return to DOS would run through the overwritten PSP.
- Instruction set: the highest CPU level used is **checked** by `tools/cpu_level.py` (capstone over the whole code, plus a
  run that watches every basic block and every store into the program's own code, for the self-modified opcode).
  Both the holder and microtris use 80186 instructions (`pusha`, `popa`, `push imm`, `imul r,r,imm`, shifts by immediate)
  and nothing above. Anything above 80186 would be reported as a separate, clearly labelled number.
- Both programs use `aam 7` for the random piece. On Intel and AMD parts the immediate is the base; the NEC V20/V30 ignore
  it and divide by 10. Same as the holder; recorded here so nobody is surprised.

## 3. What "complete" means: six features, each tested

| # | Feature | Test (in `tests/`) |
|---|---------|--------------------|
| 1 | All seven tetrominoes (I, O, T, S, Z, J, L) appear | spawn many pieces; all seven shapes seen, each spawn exactly one tetromino |
| 2 | Gravity: a piece falls by itself | no input, piece row increases one row at a time until it lands |
| 3 | Move left/right, blocked by the walls and by settled blocks | keys against both walls and against a stack |
| 4 | Rotation, blocked when it would overlap | four rotations return the shape; at both walls and beside a stack no cell is lost or moved into a block |
| 5 | Line clearing: 1 to 4 full rows are removed and the rows above drop | scripted 1-, 2-, 3-, 4-row clears; then a bot plays hundreds of pieces and each landing is compared with a reference model |
| 6 | Game over: a stack that reaches the spawn point ends play (stop, freeze or restart) without corrupting the display or running into a CPU fault | fill the well with each piece kind and with random pieces; the program reaches a defined end state |

Landing (a piece that cannot fall settles into the board) is part of 2 and 5: no landing, no stack.
The checks read the **screen**, not the program's memory: a black-box adapter per program (`tests/adapters.py`) says where
the well is and what a block looks like. A reference model (`tools/tetris_model.py`) decides what the board must be.

**Why six and not the archive's seven.** The Tetris4K archive lists tinytris with seven features, one of them
"Pause: pause emulation" (key "F16", "any key: unpause"). That is the emulator being paused, not the program. The
holder's `tinytris.com` has no key that stops its gravity, so the program's own features are the six above. A program
that adds a real pause is stronger than the holder, never weaker, and would be reported separately. The archive also
lists tinytris at 251 B (an older build); the holder's repository ships a 247 B `tinytris.com`, which is the number measured here.

## 4. What is NOT required (same as the holder)

Scoring, next-piece preview, levels, colours per piece, sound, a title screen, speed that is independent of CPU
speed, keys other than left, right and rotate. A timer-based speed is welcome as an extra but is not part of the claim,
and the holder does not have it: gravity is a free-running counter, so the fall speed is whatever the CPU does.
microtris's fall takes 315,265 instructions per row against the holder's 355,481, measured on the VM (the holder spends
most of its time in a draw loop that overruns; see `notes/holder-analysis.md`).

## 5. Extra evidence (not part of the six, run by `make verify`)

| Check | What it proves |
|-------|----------------|
| `tools/reach.py` | breadth-first search over every (shape, column, row) a piece can reach in an empty well: all four cells exist and are inside the well in every position, for all 7 pieces |
| `tests/fuzz.py` | random keys (and idle stretches, and keys the game does not use) on random stacks; after every single frame the screen must be the settled stack plus one whole tetromino, a sideways key moves one column or is really blocked, rotation always turns the same way, other keys change nothing |
| `tests/footprint.py` | every store the CPU makes lies in the program's own segment or the first text page (the VM maps 1 MB as RAM, so this is not implied by passing 1 to 6); at most one byte of the program's own code is ever written (the patched opcode) |
| `tools/cpu_level.py` | nothing above 80186; every basic block that runs starts on an instruction the static listing found |
| `make -j4 -Otarget robust` | checks 1-6, fuzz and footprint again with zeroed registers, other load segments and other seeds |

The holder passes the six checks. It fails two of the extra ones, and `make holder-bug` shows how: it loses a vertical I
at the right wall (fuzz), and it writes about 64 KB over the B800 segment every frame (footprint). microtris passes both.
The six-feature claim is made on the same footing for both programs; the two defects are findings, not part of the claim.

## 6. How a result is reproduced

```
make            # assembles src/microtris.asm with nasm; prints "build/microtris.com: N bytes" (stat -c %s)
make verify     # fetches the holder (sha256 checked); six checks on both; cpu_level; reach; fuzz; footprint
make -j4 -Otarget robust
make dosbox     # the same program under real DOSBox on a private X display: a second, independent DOS
make holder-bug # the holder's two defects
```

The deterministic harness is `tools/dosvm.py` (python-unicorn: fixed BIOS tick, fixed keyboard script, no wall clock);
DOSBox is the independent cross-check, not the judge. Tools needed: `nasm python-unicorn python-capstone`, and for
`make dosbox` also `dosbox xdotool xorg-server-xvfb imagemagick`.

## 7. Limits of the claim

- Speed is CPU-bound, like the holder's. In DOSBox choose a fixed `cycles` setting; `make dosbox` uses 400 for the part
  that needs a slow machine.
- Game over freezes. Look: red well, black walls and blocks, text-mode cells, no title, no score.
- The evidence is simulation plus one emulator, not hardware. The checks cannot prove the absence of every bug; they
  show which behaviours were exercised, and how.
