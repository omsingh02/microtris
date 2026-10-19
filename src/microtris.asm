; microtris.asm - Tetris in a DOS .COM file, smaller than the 247-byte tinytris.
;
; Built on the architecture of pellsson's tinytris (https://github.com/pellsson/tinytris): the board lives in the
; stack segment as one word per row, a piece is a 4x4 bit mask, one routine tests/stamps/erases by patching its own
; opcode, and the screen is redrawn from the board. See reference/tinytris-reconstructed.asm for the original,
; byte for byte. What is different here:
;   * rotation is a column gather done with one multiply per column (27 bytes instead of 46)
;   * the piece table holds each piece as ONE byte (two rows of the 4x4 box), not a word: 7 bytes instead of 14
;
; Entry state relied on (same as the holder's, see RULES.md): CS=DS=ES=SS, SP=0xFFFE, SI=0x100, DI=0, text mode,
; BIOS keyboard (INT 16h) and the timer counter at port 0x40 for the random piece.
        bits 16
        org 0x100
BOARD_ROWS equ 0x18

start:
        mov bx, sp                  ; bx = board base 0xFFFE
        mov ax, 0x400f              ; an empty row: walls only (bit 14 on the left, bits 3..0 on the right)
        mov cx, BOARD_ROWS
        mov di, sp
        repne stosw                 ; 24 rows (the first ones wrap round into the PSP); cx = 0 afterwards
        dec cx                      ; cx = 0xFFFF
        or [di], cx                 ; the row after the last one = 0xFFFF: the floor

next_piece:                         ; ---- remove full rows (si = row pointer; first pass reads from the program itself)
        push ds
        pop es
scan:   cmp word [si], 0x7fff
        ja pick                     ; reached the floor (0xFFFF > 0x7FFF): done
        jne advance
        mov di, si                  ; a full row: copy every row above it down by one (backwards)
        std
        lodsw
.shift: movsw
        cmp si, bx
        jne .shift                  ; (si is back at the top row now, so the scan carries on from there)
        cld
advance:
        lodsw                       ; next row
        jmp scan

pick:   in al, 0x40                 ; random piece from the timer: 0..6
        aam 7
        cbw                         ; ah = 0 (aam leaves the quotient there)
        xchg bp, ax
        mov al, [bp + pieces]       ; one byte = rows 0 and 1 of the piece's 4x4 box
        cbw                         ; (no piece byte has bit 7 set)
        xchg dx, ax                 ; dx = the 4x4 mask
        mov cl, 7                   ; column shift: start in the middle
        mov si, bx                  ; si = the piece's top row = the top row of the board

frame:  xor di, di
        call test_piece             ; ZF=1 if the piece fits at si, cl
        pushf
        je .fits
        dec si                      ; (a collision: step back up a row)
        dec si
.fits:  mov al, 0x31                ; opcode 'xor [si],ax': stamp the piece into the board (the cells are empty: xor = or)
        call set_op
        push 0xb800
        pop es
        pusha                       ; ---- draw the whole board: 25 rows x 15 cells x 2 columns
        xor al, al                  ; a blank character: only the background colour shows
        mov cl, BOARD_ROWS
.row:   mov dx, 0x4000
.cell:  test [bx], dx
        lahf                        ; the attribute comes from the flags: ZF (bit 6) = empty = red background, else black
        stosw
        stosw
        shr dx, 1
        jne .cell
        add di, 0x64                ; down a screen row (160 - 60 bytes)
        inc bx
        inc bx
        dec cx
        jae .row
        popa
        popf
        jne next_piece              ; the piece collided: it has landed. next piece (and full rows go)
        call set_op                 ; (al is still 0x31) xor the piece out of the board again
        add ch, 0x20                ; gravity: every 8th pass the piece moves down a row
        jae .nodrop
        lodsw
.nodrop:
        mov ah, 1
        int 0x16
        jz frame                    ; no key: next pass
        push frame                  ; a key: handle it; whatever happens, return to 'frame'
        push cx
        push dx
        mov ax, di
        int 0x16
        sub al, 'j'                 ; j, k, l -> 0, 1, 2
        cmp al, 3
        jae undo                    ; any other key: nothing happens
        dec al                      ; j, k, l -> -1, 0, +1
        jne sideways
rotate:                             ; dx = mask -> dx = mask turned 90 degrees (di is 0 now, and 0 again at the end)
        mov bp, 4                   ; four columns
.col:   mov ax, dx
        and ax, 0x1111              ; this column: bits 0, 4, 8, 12
        imul ax, ax, 0x1248         ; the multiply gathers them, in order, into bits 12..15 (no carries meet)
        shr ax, 12
        shl di, 4                   ; (the first column ends up in the top nibble)
        or di, ax
        shr dx, 1                   ; next column
        dec bp
        jnz .col
        mov dx, di
        xor di, di
move:   call test_piece
        jne undo
        pop ax                      ; it fits: throw away the saved cx/dx
        pop ax
        ret
undo:   pop dx
        pop cx
        ret
sideways:
        sub cl, al                  ; j (-1): one column left (shift up), l (+1): one column right
        jmp move

test_piece:
        mov al, 0x23                ; opcode 'and ax,[si]'
set_op: mov [op], al                ; (self-modifying: the opcode byte below is patched)
        pusha
nib:    mov ax, dx
        and ax, 0xf
        shl ax, cl
op:     and [si], ax
        or di, ax
        lodsw
        shr dx, 4
        jne nib
        or di, di
        popa
        ret

pieces: db 0x0f, 0x66, 0x72, 0x36, 0x63, 0x74, 0x71   ; I O T S Z L J: row 0 in the low nibble, row 1 in the high
