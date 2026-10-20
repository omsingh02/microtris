#!/usr/bin/python3
"""dosvm.py - run a DOS .COM deterministically, one instruction at a time (python-unicorn).

No clock anywhere: time is the instruction count, and the tick counter, the PIT and the keyboard are functions of it and
of a script. Emulated: the .COM entry state, INT 10h, 16h, 1Ah, 20h and 21h as far as a tiny program uses them, text
video memory at B800:0000, the BIOS data area, ports 0x40 (scripted), 0x60, 0x61 and 0x3DA. Interrupts are not
delivered, so a program may poll but cannot install a handler.

    vm = DosVM(com_bytes); vm.frame(); vm.press('j'); vm.frame(); print(vm.screen_text())

frame() runs until the program next asks the keyboard whether a key is waiting."""

import sys
from collections import deque

from unicorn import UC_ARCH_X86, UC_HOOK_INSN, UC_HOOK_INTR, UC_MODE_16, Uc, UcError
from unicorn.x86_const import (
    UC_X86_INS_IN,
    UC_X86_INS_OUT,
    UC_X86_REG_AX,
    UC_X86_REG_BP,
    UC_X86_REG_BX,
    UC_X86_REG_CS,
    UC_X86_REG_CX,
    UC_X86_REG_DI,
    UC_X86_REG_DS,
    UC_X86_REG_DX,
    UC_X86_REG_EFLAGS,
    UC_X86_REG_ES,
    UC_X86_REG_IP,
    UC_X86_REG_SI,
    UC_X86_REG_SP,
    UC_X86_REG_SS,
)

# ---- keys: name -> BIOS keystroke word (scan code << 8 | ascii) ----------------------------------------------
_SCAN = dict(zip("1234567890", range(0x02, 0x0C), strict=True))
_SCAN.update(zip("qwertyuiop", range(0x10, 0x1A), strict=True))
_SCAN.update(zip("asdfghjkl", range(0x1E, 0x27), strict=True))
_SCAN.update(zip("zxcvbnm", range(0x2C, 0x33), strict=True))
KEYS = {
    'left': 0x4B00,
    'right': 0x4D00,
    'up': 0x4800,
    'down': 0x5000,
    'space': 0x3920,
    'esc': 0x011B,
    'enter': 0x1C0D,
    'tab': 0x0F09,
    'backspace': 0x0E08,
}
for _c, _s in _SCAN.items():
    KEYS[_c] = (_s << 8) | ord(_c)
for _c in "abcdefghijklmnopqrstuvwxyz":
    KEYS[_c.upper()] = (_SCAN[_c] << 8) | ord(_c.upper())


def key_word(k):
    return k if isinstance(k, int) else KEYS[k]


class DosVM:
    POLL_COST = 100  # instructions charged when a run is cut short at a poll (see run())
    CHUNK = 5000  # instructions between clock updates
    INSNS_PER_TICK = 5000  # nominal: 18.2 Hz tick, ~90 K instructions/s machine. Tunable by tests.

    def __init__(self, com, seg=0x1000, seed=1, profile='dos', insns_per_tick=None):
        if len(com) > 0xFF00:
            raise ValueError('a .COM program must fit in 64 KB minus PSP and stack')
        self.seg = seg
        self.com = bytes(com)
        self.insns = 0  # instructions executed so far ("time")
        self.insns_per_tick = insns_per_tick or self.INSNS_PER_TICK
        self.keys = deque()
        self.exited = None  # exit code once the program has ended
        self.faulted = None  # unicorn error text if the CPU faulted
        self.polls = 0  # how many times the program has asked "is a key waiting?"
        self.blocked = False  # waiting in a blocking key read with an empty queue
        self.video_mode = 3
        self.cursor = [0, 0]
        self.last_scancode = 0
        self.out_log = []
        self._stop_at_poll = False
        self._parked = False  # stopped in front of an INT that has not been served yet
        self._resume_poll = False  # the next INT 16h is the one we parked at: serve it, do not stop again
        self._pit = seed & 0xFFFF or 1  # xorshift state for port 0x40
        self.pit_fn = None  # optional callable returning the byte IN 0x40 gives (tests use this to pick pieces)

        uc = self.uc = Uc(UC_ARCH_X86, UC_MODE_16)
        uc.mem_map(0, 0x100000)
        self.base = seg << 4
        self._build_bda()
        self._build_psp(seg)
        uc.mem_write(self.base + 0x100, self.com)
        for r in (UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS):
            uc.reg_write(r, seg)
        if profile == 'dos':  # what MS-DOS 5/6 and DOSBox hand to a .COM
            regs = {
                UC_X86_REG_AX: 0,
                UC_X86_REG_BX: 0,
                UC_X86_REG_CX: 0x00FF,
                UC_X86_REG_DX: seg,
                UC_X86_REG_SI: 0x100,
                UC_X86_REG_DI: 0xFFFE,
                UC_X86_REG_BP: 0x091C,
            }
        elif profile == 'zeroed':  # nothing may be relied on: every general register is 0 (SP is still 0xFFFE)
            regs = dict.fromkeys(
                (
                    UC_X86_REG_AX,
                    UC_X86_REG_BX,
                    UC_X86_REG_CX,
                    UC_X86_REG_DX,
                    UC_X86_REG_SI,
                    UC_X86_REG_DI,
                    UC_X86_REG_BP,
                ),
                0,
            )
        else:
            raise ValueError(profile)
        for r, v in regs.items():
            uc.reg_write(r, v)
        uc.reg_write(UC_X86_REG_SP, 0xFFFE)
        uc.reg_write(UC_X86_REG_IP, 0x100)
        uc.reg_write(UC_X86_REG_EFLAGS, 0x0202)
        uc.hook_add(UC_HOOK_INTR, self._intr_hook)
        uc.hook_add(UC_HOOK_INSN, self._in_hook, None, 1, 0, UC_X86_INS_IN)
        uc.hook_add(UC_HOOK_INSN, self._out_hook, None, 1, 0, UC_X86_INS_OUT)
        self._write_tick()

    # ---- memory image ----------------------------------------------------------------------------------------
    def _build_bda(self):
        uc = self.uc
        bda = 0x400
        uc.mem_write(bda + 0x10, (0x0021).to_bytes(2, 'little'))  # equipment: colour adapter
        uc.mem_write(bda + 0x13, (640).to_bytes(2, 'little'))
        uc.mem_write(bda + 0x49, bytes([3]))  # video mode 3
        uc.mem_write(bda + 0x4A, (80).to_bytes(2, 'little'))
        uc.mem_write(bda + 0x84, bytes([24]))
        # text screen starts as the BIOS leaves it: spaces, light grey on black
        uc.mem_write(0xB8000, b' \x07' * (80 * 25))

    def _build_psp(self, seg):
        psp = bytearray(0x100)
        psp[0:2] = b'\xcd\x20'
        psp[2:4] = (0x9FFF).to_bytes(2, 'little')
        psp[0x2C:0x2E] = (seg - 0x20 & 0xFFFF).to_bytes(2, 'little')
        psp[0x80] = 0
        psp[0x81] = 0x0D
        self.uc.mem_write(self.base, bytes(psp))

    # ---- registers / memory convenience ----------------------------------------------------------------------
    def r(self, reg):
        return self.uc.reg_read(reg)

    def w(self, reg, value):
        self.uc.reg_write(reg, value)

    @property
    def cs_ip(self):
        return self.r(UC_X86_REG_CS), self.r(UC_X86_REG_IP)

    def read(self, off, n, seg=None):
        return bytes(self.uc.mem_read(((self.seg if seg is None else seg) << 4) + off, n))

    def vram(self):
        return bytes(self.uc.mem_read(0xB8000, 80 * 25 * 2))

    def screen(self):
        """25 rows of 80 (char, attribute) pairs."""
        v = self.vram()
        return [[(v[(y * 80 + x) * 2], v[(y * 80 + x) * 2 + 1]) for x in range(80)] for y in range(25)]

    def screen_text(self, blocks=None):
        """The screen as text. `blocks` maps an attribute byte to a character for solid cells (e.g. {0x44:'#'})."""
        blocks = blocks or {}
        lines = []
        for row in self.screen():
            s = ''
            for ch, at in row:
                if at in blocks:
                    s += blocks[at]
                elif 32 <= ch < 127:
                    s += chr(ch)
                else:
                    s += ' ' if ch == 0 else '·'
            lines.append(s.rstrip())
        while lines and not lines[-1]:
            lines.pop()
        return '\n'.join(lines)

    # ---- keyboard --------------------------------------------------------------------------------------------
    def press(self, *names):
        for n in names:
            self.keys.append(key_word(n))

    # ---- time ------------------------------------------------------------------------------------------------
    @property
    def ticks(self):
        return self.insns // self.insns_per_tick

    def _write_tick(self):
        self.uc.mem_write(0x46C, (self.ticks & 0xFFFFFFFF).to_bytes(4, 'little'))

    # ---- ports -----------------------------------------------------------------------------------------------
    def _next_pit(self):
        if self.pit_fn is not None:
            return self.pit_fn() & 0xFF
        x = self._pit
        x ^= (x << 7) & 0xFFFF
        x ^= x >> 9
        x ^= (x << 8) & 0xFFFF
        self._pit = x or 1
        return self._pit & 0xFF

    def _in_hook(self, uc, port, size, _):
        if port == 0x40:
            return self._next_pit()
        if port == 0x60:
            return self.last_scancode
        if port == 0x61:
            return self.ticks & 0x10 | 0x20  # bit 4 toggles with time (refresh), bit 5 = timer 2 output
        if port == 0x3DA:
            return (self.insns // 50) & 0x09  # retrace/display-enable bits wobble with time
        return 0

    def _out_hook(self, uc, port, size, value, _):
        self.out_log.append((port, value))

    # ---- BIOS / DOS services ---------------------------------------------------------------------------------
    def _intr_hook(self, uc, intno, _):
        """Unicorn calls this for every INT n and every CPU exception; it does not run the interrupt table afterwards,
        so the services below ARE the BIOS and DOS."""
        ip = self.r(UC_X86_REG_IP)
        before = self.read(ip - 2, 2, self.r(UC_X86_REG_CS)) if ip >= 2 else b''
        if before[:1] != b'\xcd' or before[1:2] != bytes([intno]):  # not a software INT: a real CPU exception
            self.faulted = f'CPU exception {intno} at {self.r(UC_X86_REG_CS):04X}:{ip:04X}'
            uc.emu_stop()
            return
        if (
            intno == 0x16
            and self._stop_at_poll
            and not self._resume_poll
            and (self.r(UC_X86_REG_AX) >> 8) in (0x01, 0x11)
        ):
            self.w(UC_X86_REG_IP, ip - 2)  # park in front of the INT; it is served when the run resumes
            self._parked = True
            uc.emu_stop()
            return
        self._resume_poll = False
        self._service(intno)

    def _set_zf(self, zero):
        fl = self.r(UC_X86_REG_EFLAGS)
        self.w(UC_X86_REG_EFLAGS, (fl | 0x40) if zero else (fl & ~0x40))

    def _block(self, ip_len=2):
        """A blocking read with nothing to read: stay in front of the INT and stop until the test provides a key."""
        self.w(UC_X86_REG_IP, self.r(UC_X86_REG_IP) - ip_len)
        self.blocked = True
        self._parked = True
        self.uc.emu_stop()

    def _service(self, intno):
        ax = self.r(UC_X86_REG_AX)
        ah, al = ax >> 8, ax & 0xFF
        if intno == 0x16:
            self.polls += 1
            if ah in (0x00, 0x10):  # wait for a key
                if self.keys:
                    k = self.keys.popleft()
                    self.last_scancode = k >> 8
                    self.w(UC_X86_REG_AX, k)
                else:
                    self.polls -= 1
                    self._block()
            elif ah in (0x01, 0x11):  # is a key waiting?
                if self.keys:
                    self.w(UC_X86_REG_AX, self.keys[0])
                    self._set_zf(False)
                else:
                    self._set_zf(True)
            elif ah in (0x02, 0x12):
                self.w(UC_X86_REG_AX, 0)
        elif intno == 0x10:
            self._int10(ah, al)
        elif intno == 0x1A:
            if ah == 0:
                t = self.ticks
                self.w(UC_X86_REG_CX, t >> 16 & 0xFFFF)
                self.w(UC_X86_REG_DX, t & 0xFFFF)
                self.w(UC_X86_REG_AX, 0)
        elif intno == 0x20:
            self._exit(0)
        elif intno == 0x21:
            self._int21(ah, al)

    def _exit(self, code):
        self.exited = code & 0xFF
        self.uc.emu_stop()

    def _int10(self, ah, al):
        uc = self.uc
        if ah == 0x00:
            self.video_mode = al & 0x7F
            uc.mem_write(0xB8000, b' \x07' * (80 * 25))
            self.cursor = [0, 0]
        elif ah == 0x02:
            self.cursor = [self.r(UC_X86_REG_DX) & 0xFF, self.r(UC_X86_REG_DX) >> 8]  # col, row
        elif ah == 0x03:
            self.w(UC_X86_REG_DX, self.cursor[1] << 8 | self.cursor[0])
            self.w(UC_X86_REG_CX, 0x0607)
        elif ah == 0x0F:
            self.w(UC_X86_REG_AX, 80 << 8 | self.video_mode)
            self.w(UC_X86_REG_BX, self.r(UC_X86_REG_BX) & 0x00FF)
        elif ah in (0x09, 0x0A):
            bl = self.r(UC_X86_REG_BX) & 0xFF
            n = self.r(UC_X86_REG_CX)
            x, y = self.cursor
            for i in range(n):
                p = 0xB8000 + ((y * 80 + x + i) % 2000) * 2
                uc.mem_write(p, bytes([al]) if ah == 0x0A else bytes([al, bl]))
        elif ah == 0x0E:
            self._teletype(al)
        elif ah == 0x06 and al == 0:  # scroll up whole window = clear (the common use)
            bh = self.r(UC_X86_REG_BX) >> 8
            uc.mem_write(0xB8000, bytes([0x20, bh]) * 2000)

    def _teletype(self, ch):
        x, y = self.cursor
        if ch == 0x0D:
            x = 0
        elif ch == 0x0A:
            y += 1
        elif ch == 0x08:
            x = max(0, x - 1)
        else:
            self.uc.mem_write(0xB8000 + (y * 80 + x) * 2, bytes([ch]))
            x += 1
            if x == 80:
                x, y = 0, y + 1
        if y >= 25:
            v = bytes(self.uc.mem_read(0xB8000 + 160, 160 * 24))
            self.uc.mem_write(0xB8000, v + b' \x07' * 80)
            y = 24
        self.cursor = [x, y]

    def _int21(self, ah, al):
        if ah == 0x4C:
            self._exit(al)
        elif ah == 0x00:
            self._exit(0)
        elif ah == 0x02:
            self._teletype(self.r(UC_X86_REG_DX) & 0xFF)
        elif ah == 0x09:
            dx = self.r(UC_X86_REG_DX)
            ds = self.r(UC_X86_REG_DS)
            i = 0
            while i < 4096:
                c = self.uc.mem_read((ds << 4) + ((dx + i) & 0xFFFF), 1)[0]
                if c == 0x24:
                    break
                self._teletype(c)
                i += 1
        elif ah in (0x01, 0x07, 0x08):
            if self.keys:
                k = self.keys.popleft()
                self.w(UC_X86_REG_AX, (ah << 8) | (k & 0xFF))
            else:
                self._block()
        elif ah == 0x0B:
            self.w(UC_X86_REG_AX, (0x0B << 8) | (0xFF if self.keys else 0))
        elif ah == 0x2C:
            t = self.ticks * 55 // 1000  # milliseconds since "midnight"
            cs = t // 10 % 100
            s = t // 1000 % 60
            m = t // 60000 % 60
            h = t // 3600000 % 24
            self.w(UC_X86_REG_CX, h << 8 | m)
            self.w(UC_X86_REG_DX, s << 8 | cs)

    # ---- running ---------------------------------------------------------------------------------------------
    def _linear_ip(self):
        cs, ip = self.cs_ip
        return (cs << 4) + ip

    def run(self, max_insns=1_000_000, stop_at_poll=False):
        """Run until `max_insns` have executed, the program exits, blocks on a key read, faults, or (if
        `stop_at_poll`) asks the keyboard a question. Returns a reason string."""
        if self.exited is not None:
            return 'exited'
        self._stop_at_poll = stop_at_poll
        target = self.insns + max_insns
        if self._parked:  # resuming in front of an INT: the test has had its chance to press keys
            self._parked = False
            self.blocked = False
            self._resume_poll = True
        while self.insns < target:
            n = min(self.CHUNK, target - self.insns)
            try:
                self.uc.emu_start(self._linear_ip(), 0, count=n)
            except UcError as e:
                self.faulted = str(e)
                return 'fault'
            if self.exited is not None:
                return 'exited'
            if self.faulted:
                return 'fault'
            if self._parked:  # cut short: the exact count is unknown, charge a nominal cost
                self.insns += self.POLL_COST
                self._write_tick()
                return 'blocked' if self.blocked else 'poll'
            self.insns += n
            self._write_tick()
        return 'limit'

    def frame(self, max_insns=2_000_000):
        """Run to the program's next keyboard poll (one game frame). Returns the stop reason."""
        return self.run(max_insns, stop_at_poll=True)

    def frames(self, n, max_insns=2_000_000):
        why = 'poll'
        for _ in range(n):
            why = self.frame(max_insns)
            if why != 'poll':
                break
        return why


def main(argv):
    import argparse

    p = argparse.ArgumentParser(description='run a .COM and show its screen')
    p.add_argument('com')
    p.add_argument('--frames', type=int, default=10, help='run this many frames (keyboard polls)')
    p.add_argument('--keys', default='', help='space separated key names pressed before frame 1 (e.g. "j j k")')
    p.add_argument('--blocks', default='', help='attribute:char pairs for solid cells, e.g. 0x44:# 0x77:.')
    p.add_argument('--seed', type=int, default=1)
    a = p.parse_args(argv)
    with open(a.com, 'rb') as f:
        vm = DosVM(f.read(), seed=a.seed)
    vm.press(*a.keys.split())
    why = vm.frames(a.frames)
    blocks = {int(k, 0): v for k, v in (kv.split(':') for kv in a.blocks.split())}
    print(vm.screen_text(blocks))
    print(f'-- stopped: {why}, polls {vm.polls}, instructions {vm.insns}, exited {vm.exited}, fault {vm.faulted}')


if __name__ == '__main__':
    main(sys.argv[1:])
