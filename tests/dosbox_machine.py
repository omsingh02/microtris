"""dosbox_machine.py - the real DOSBox as a test machine: a second, independent implementation of DOS and the PC.

It starts a private X server (Xvfb) so nothing appears on your desktop, runs DOSBox on it, sends real key presses
with xdotool and reads the screen back from screenshots (ImageMagick `import`, decoded with Pillow). It offers the same
small interface the tests use on the deterministic VM: press(), frame(), screen().

Not deterministic (real time), so it is a cross-check of behaviour, not a replacement for the VM tests."""
import io
import os
import shutil
import subprocess
import tempfile
import time

from PIL import Image

CONF = '''[sdl]
fullscreen=false
output=surface
windowresolution=original
autolock=false
[dosbox]
machine=vgaonly
memsize=16
[render]
scaler=none
frameskip=0
[cpu]
core=normal
cputype=auto
cycles=fixed {cycles}
[mixer]
nosound=true
[speaker]
pcspeaker=false
[sblaster]
sbtype=none
[midi]
mpu401=none
[joystick]
joysticktype=none
[autoexec]
mount c {dir}
c:
'''


def _free_display():
    for n in range(90, 120):
        if not os.path.exists(f'/tmp/.X{n}-lock') and not os.path.exists(f'/tmp/.X11-unix/X{n}'):
            return n
    raise RuntimeError('no free X display number')


class DosboxMachine:
    CELL = (9, 16)                                           # pixels per text cell in 80x25 mode

    def __init__(self, com_path, cycles=2000, wait=0.15):
        self.wait, self.polls = wait, 0
        self.dir = tempfile.mkdtemp(prefix='dosbox-')
        shutil.copy(com_path, os.path.join(self.dir, 'GAME.COM'))
        with open(os.path.join(self.dir, 'db.conf'), 'w') as f:
            f.write(CONF.format(cycles=cycles, dir=self.dir))
        n = _free_display()
        self.env = {k: v for k, v in os.environ.items() if k not in ('WAYLAND_DISPLAY', 'XDG_SESSION_TYPE')}
        self.env.update(DISPLAY=f':{n}', SDL_VIDEODRIVER='x11', SDL_AUDIODRIVER='dummy')
        self.xvfb = subprocess.Popen(['Xvfb', f':{n}', '-screen', '0', '1024x768x24', '-nolisten', 'tcp'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=self.env)
        for _ in range(100):
            if os.path.exists(f'/tmp/.X11-unix/X{n}'):
                break
            time.sleep(0.05)
        self.dosbox = subprocess.Popen(['dosbox', '-conf', os.path.join(self.dir, 'db.conf'), '-c', 'GAME.COM'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=self.env, cwd=self.dir)
        self.wid = self._x(['xdotool', 'search', '--sync', '--onlyvisible', '--name', 'DOSBox']).split()[0]
        time.sleep(1.0)
        self.frame()

    def _x(self, cmd):
        return subprocess.run(cmd, env=self.env, capture_output=True, text=True, check=True).stdout

    def press(self, *names):
        for k in names:
            self._x(['xdotool', 'key', '--window', self.wid, k])      # 'j', 'k', 'l' are the same names in xdotool

    def _grab(self):
        png = subprocess.run(['import', '-window', self.wid, 'png:-'], env=self.env, capture_output=True, check=True).stdout
        self.image = Image.open(io.BytesIO(png)).convert('RGB')
        return self.screen()

    def frame(self):
        """Wait a moment, then take screenshots until two in a row show the same board (the program redraws the whole
        board in a loop, so a screenshot can catch it half drawn)."""
        time.sleep(self.wait)
        last = self._grab()
        for _ in range(8):
            now = self._grab()
            if now == last:
                break
            last = now
        self.polls += 1
        return 'poll'

    def screen(self):
        w, h = self.CELL
        rows = []
        for r in range(25):
            row = []
            for c in range(80):
                px = self.image.getpixel((c * w + 1, r * h + 1))
                bg = (px[0] > 140) << 6 | (px[1] > 140) << 5 | (px[2] > 140) << 4   # the three colour bits, as in an attribute
                attr = bg | bg >> 4                                                  # (solid cells: foreground = background)
                row.append((0, attr))
            rows.append(row)
        return rows

    def close(self):
        for p in (self.dosbox, self.xvfb):
            p.terminate()
        for p in (self.dosbox, self.xvfb):
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        shutil.rmtree(self.dir, ignore_errors=True)
