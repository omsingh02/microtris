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

## Open questions to settle under the harness

- Where exactly is pause? (I see no blocking key wait; `int 16h` is called with AH taken from DI.)
- What does game over do (hang, restart, overwrite)?
- Is the left/right mapping j/l, rotation k?
