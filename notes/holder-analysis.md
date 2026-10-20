# tinytris (247 B) read from its disassembly

Source: `objdump -D -b binary -m i8086 -M intel --adjust-vma=0x100 tinytris.com` of the downloaded `.COM`
(the repo ships no `.asm`). Everything here is what I read in the bytes; items marked (?) get confirmed under the
harness before they are relied on.

## Data layout

- **The board is the stack.** `mov bx,sp` (BX = 0xFFFE). 24 rows of one 16-bit word each, row *i* at `BX + 2i`
  (mod 64 KB, so the first rows wrap round to the PSP at 0x0000..0x2D). A 25th row of 0xFFFF is the floor.
- **One row = 13 bits.** Row template `0x1003`: bits 0-1 left wall, bit 12 right wall, bits 2-11 the 10 playfield
  cells. A full row is `0x1FFF`.
- **A piece is 16 bits**: a 4x4 mask, one nibble per row. The seven shapes are a 14-byte table at the very end of
  the file (`2222 4460 2260 06C0 0C60 0660 04E0`): there is no table of rotations, rotation is computed.
- **Piece choice** reads PIT counter 0 (`in al,0x40`), `aam 7`, indexes the table.

## Tricks worth knowing

1. **Self-modifying collision/draw routine** (`1ce`/`1d0`): the one-byte opcode of `and [si],ax` is overwritten with
   `0x23` (`and ax,[si]`: test), `0x09` (`or [si],ax`: stamp) or `0x31` (`xor [si],ax`: toggle), so one loop
   does test, settle and draw.
2. **Collision result in ZF.** The routine ORs every overlap into DI, so `or di,di` leaves ZF = "no collision".
3. **Undo by the stack.** A move is applied, tested, and the caller's `push cx / push dx` copies are either
   discarded (`pop ax; pop ax`) or restored (`pop dx; pop cx`). `push 0x138` first makes `ret` jump back to the loop.
4. **Row clear** is a backward `movsw` loop with `std`, no row counting.
5. **Rendering** writes text-mode video memory directly: 13 cells x 2 chars per row, attribute `0x44` or `0x77`
   (solid colour blocks), 24 rows.
6. **Gravity is a free-running counter**: `add ch,0x20; jae` drops the piece every 8th pass of the loop, so the speed
   is whatever the CPU does (the holder's README lists this as a known weakness).
7. **Rotation** (46 bytes, `194..1c1`) transposes the 4x4 mask with a shift/or loop.

## Entry assumptions the holder makes (so the same are allowed here)

`DS=CS=SS`, writable stack, text mode already on, and `SI=0x100` (`cmp [si],0x1fff` reads the program's own first
bytes on the first pass) (?).

## Behaviour confirmed under `tools/dosvm.py` (2026-10-20)

- Keys: `j` left, `l` right, `k` rotate; every other key is read and ignored. (The archive says `k` is counter-clockwise.)
- A frame is one `INT 16h AH=1` peek followed, only if a key is there, by an `AH=0` read (the code passes AX=DI, which is 0).
  Gravity is every 8th frame; one frame is about 44,000 instructions (almost all of it redrawing the screen).
- **Pause: none.** The archive's "pause" is "pause emulation" (an emulator hotkey), not code.
- **Game over: freeze.** When the stack reaches the top, the spawn/land loop (`10f..169`) spins forever without
  calling the keyboard, so keys do nothing and the machine must be reset. The last board stays on screen.
- Screen: the board is drawn from column 0, two characters per cell, attribute `0x44` for filled and `0x77` for empty;
  the left wall (bit 12) is one cell wide and the right wall (bits 1-0) two cells wide, so the well is not centred.

## Defects found in the holder by this project's extra checks (2026-10-20)

Neither changes the claim: the holder still passes the six scripted feature checks. They are recorded because the
harness found them, and because microtris started from the same architecture and had to fix both.
(Nothing has been reported upstream; that is a decision for the owner of this project.)

1. **A vertical I is lost at the right wall.** The collision test shifts a nibble left by CL (`shl ax,cl`). Pressing
   `l` once too often takes CL to 0xFF; the 80186 masks the count to 5 bits, 31 shifts out a whole nibble, and a cell
   that no longer exists can never collide. The piece disappears from the screen (and from the board).
   `make holder-bug` shows it (`tests/fuzz.py`: random keys, every frame judged). microtris moves the well up two bits
   so that CL=0 is never a valid position, and `tools/reach.py` proves by exhaustive search that no reachable
   position loses a cell.
2. **The draw loop never ends where it says it does.** It is `mov cl,24 ... dec cx / jae .row`: `dec` leaves CF alone, so
   the loop ends only when `add di,0x6c` finally carries, i.e. after about 410 rows, when DI wraps. Every frame the
   holder writes about 64 KB over ES=B800: the other seven text pages and, above them, 0xC0000..0xC7FFF (the video
   BIOS ROM area, where a real bus ignores the writes and an emulator may not). It also explains the 44,000
   instructions per frame measured above, and so the holder's gravity speed: it is mostly this wasted drawing.
   `make holder-bug` shows it (`tests/footprint.py`; the VM maps all 1 MB as RAM, which is why the six checks never
   notice). microtris draws 25 rows with `loop` at the same size and compensates in the gravity step
   (`add ch,2`, every 128th pass), so one row of fall takes 315,393 instructions against the holder's 355,481 (VM count).
