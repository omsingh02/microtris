# The claim, and the rules it is measured by

**Claim to beat:** the smallest *complete* Tetris, as a 16-bit x86 DOS `.COM` program.
**Holder:** [pellsson/tinytris](https://github.com/pellsson/tinytris), **247 bytes** (`tinytris.com`, sha256 `0cbd70be…4bfa`).
The holder's own README calls it "the first complete Tetris implementation in 256 bytes or less" and says smaller
ones exist but alter the game (usually by dropping or changing pieces). That is the line this project draws too.

There is no official body for this. So the claim is only as good as its rules and how easy they are to re-check.
Everything below is checked by `make verify`, not by eye. *(DRAFT: finalised once the holder passes every check
under the same harness; a rule the holder cannot meet is a rule stricter than the record I am trying to beat.)*

## 1. What is measured

- One file, `<name>.COM`. Its size in bytes (`stat -c %s`) is the number. No overlays, no second file, no packer
  stub counted separately: a self-extracting COM is measured as the COM.
- Nothing may be read from outside the file or from DOS/BIOS data that the program did not put there (no loading a
  font, no reading a save file, no reaching into another program's memory). BIOS and DOS *services* are allowed.

## 2. The machine

- Real-mode x86, run as a DOS `.COM`: CS=DS=ES=SS=PSP segment, IP=0x100, SP=0xFFFE, text mode 80x25 already active.
- The register values DOS gives a `.COM` at entry (e.g. SI=0x100, DI=0xFFFE, CX=0x00FF, BX=0) may be relied on only
  if the harness sets them identically for the holder and for this program. Each reliance is listed in the source
  header, so nobody has to find it by disassembling.
- Instruction set: the highest CPU level used is declared in the source and **checked** by disassembly
  (`tools/cpu-level.py`). The holder uses 80186 instructions (`pusha`, `imul r,r,imm`, shifts by immediate).
  Anything above 80186 is reported as a separate, clearly labelled number.

## 3. What "complete" means: seven features, each tested

| # | Feature | Test (in `tests/`) |
|---|---------|--------------------|
| 1 | All seven tetrominoes (I, O, T, S, Z, J, L) appear | spawn many pieces; all seven shapes seen |
| 2 | Gravity: a piece falls by itself | no input, piece row increases |
| 3 | Move left/right, blocked by walls and by settled blocks | keys against wall and against a stack |
| 4 | Rotation, blocked when it would overlap | rotate near wall/stack; four rotations return the same shape |
| 5 | Landing: a piece that cannot fall settles into the board | piece stops on the floor and on blocks |
| 6 | Line clearing: 1 to 4 full rows are removed and the rows above drop | build rows by script; board after == expected |
| 7 | Game over: a stack that reaches the spawn point ends the game (restart or stop), without crashing or hanging the machine | fill the board; the program reaches a defined end state |
| 8 | Pause | pause key freezes gravity until pressed again |

*(Rows 1–7 and 8 are the holder's own feature list as the Tetris4K archive records it. Pause and game over will be
re-read against what the holder's binary really does before this table is frozen.)*

## 4. What is NOT required (same as the holder)

Scoring, next-piece preview, levels, colours per piece, sound, a title screen, speed that is independent of CPU
speed. A timer-based speed is welcome as an extra but is not part of the claim, and the holder does not have it.

## 5. How a result is reproduced

`make verify` assembles from source with `nasm`, compares the bytes with the checked-in `.COM`, runs the feature tests
under a deterministic instruction-level harness (python-unicorn: fixed BIOS tick, fixed keyboard script, no wall
clock), runs the same tests against `tinytris.com`, and finally runs the `.COM` under DOSBox as a second, independent
implementation of DOS. The byte count printed is `stat -c %s`.
