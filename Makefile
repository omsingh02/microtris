# make          build build/microtris.com and print its size
# make quick    the checks on microtris only, a few minutes (use while editing)
# make test     quick, plus tinytris (fetched, sha256 checked) through the same checks
# make matrix   the checks again with other registers at entry, load segments and seeds
# make dosbox   cross-check in the real DOSBox (needs dosbox, xdotool, Xvfb, ImageMagick)
# make holder-bug  the two things wrong with tinytris
# make speed    instructions per row of fall, both programs
# make play     play it in DOSBox: j left, l right, k rotate
.POSIX:

NASM = nasm
PY = python3 -I
COM = build/microtris.com
HOLDER = build/tinytris.com
HOLDER_URL = https://raw.githubusercontent.com/pellsson/tinytris/master/tinytris.com
HOLDER_SHA256 = 0cbd70beafbd043a2d47bd7391f0e84f23a9e8ec36e7b51d5cc85a070cda4bfa

all: $(COM)
	@printf '%s: %s bytes\n' $(COM) "$$(wc -c < $(COM) | tr -d ' ')"

$(COM): microtris.asm
	@mkdir -p build
	$(NASM) -f bin -l build/microtris.lst microtris.asm -o $(COM)

# tinytris has no licence, so it is not kept here: fetched, checked against its sha256, only ever run in the VM
$(HOLDER):
	@mkdir -p build
	curl -fsSL -o $(HOLDER) $(HOLDER_URL)
	@echo "$(HOLDER_SHA256)  $(HOLDER)" | sha256sum -c --quiet - || { rm -f $(HOLDER); echo 'tinytris.com: sha256 does not match'; exit 1; }

quick: all
	$(PY) test/features.py $(COM) microtris
	$(PY) test/cpu_level.py $(COM)
	$(PY) test/reach.py $(COM)
	$(PY) test/fuzz.py $(COM) microtris
	$(PY) test/footprint.py $(COM) microtris

test: quick $(HOLDER)
	@echo "$(HOLDER_SHA256)  $(HOLDER)" | sha256sum -c --quiet - && echo '$(HOLDER): sha256 matches'
	$(PY) test/features.py $(HOLDER) tinytris
	$(PY) test/cpu_level.py $(HOLDER) --data 14

matrix: all
	sh test/matrix.sh $(COM)

dosbox: all
	$(PY) test/dosbox_check.py $(COM) microtris

# exit status 1 is the expected result of both
holder-bug: $(HOLDER)
	-$(PY) test/fuzz.py $(HOLDER) tinytris --runs 40 --steps 600 --seed 100 2>&1 | head -12
	-$(PY) test/footprint.py $(HOLDER) tinytris

speed: all $(HOLDER)
	$(PY) test/speed.py $(HOLDER) tinytris
	$(PY) test/speed.py $(COM) microtris

# DOS file names stop at 8 characters, so it is played from a copy called tetris.com
play: all
	@mkdir -p build/play
	cp $(COM) build/play/tetris.com
	dosbox -c 'mount c build/play' -c 'c:' -c 'config -set "cpu cycles=fixed 400"' -c 'cls' -c 'tetris.com'

clean:
	rm -rf build
