# make        build build/microtris.com and print its size
# make verify build, rebuild the holder from reference/, run the six feature checks on both on the VM
# make holder-bug  show what the holder's program does wrong (random keys; stores outside the text page)
# make dosbox cross-check in the real DOSBox (needs dosbox, xdotool, Xvfb, ImageMagick)
NASM ?= nasm
PY   ?= python3 -I
COM    = build/microtris.com
HOLDER = build/tinytris.com
HOLDER_SHA256 = 0cbd70beafbd043a2d47bd7391f0e84f23a9e8ec36e7b51d5cc85a070cda4bfa

all: $(COM)
	@printf '%s: %s bytes\n' $(COM) "$$(stat -c %s $(COM))"

$(COM): src/microtris.asm
	@mkdir -p build
	$(NASM) -f bin -l build/microtris.lst src/microtris.asm -o $(COM)

# the holder's 247 bytes, rebuilt from the annotated source and checked against the hash of pellsson's tinytris.com
$(HOLDER): reference/tinytris-reconstructed.asm
	@mkdir -p build
	$(NASM) -f bin reference/tinytris-reconstructed.asm -o $(HOLDER)
	@echo "$(HOLDER_SHA256)  $(HOLDER)" | sha256sum -c --quiet - && printf '%s: %s bytes, sha256 matches the holder\n' $(HOLDER) "$$(stat -c %s $(HOLDER))"

verify: all $(HOLDER)
	$(PY) tests/features.py $(HOLDER) tinytris
	$(PY) tests/features.py $(COM) microtris
	$(PY) tools/cpu-level.py $(HOLDER) --data 14
	$(PY) tools/cpu-level.py $(COM)
	$(PY) tools/reach.py $(COM)
	$(PY) tests/fuzz.py $(COM) microtris
	$(PY) tests/footprint.py $(COM) microtris

# not part of verify: random keys make the holder lose a vertical I at the right wall, and its draw loop writes over the
# whole 64 KB of the B800 segment every frame (exit status 1 is the expected result for both)
holder-bug: $(HOLDER)
	-$(PY) tests/fuzz.py $(HOLDER) tinytris --runs 40 --steps 600 --seed 100 2>&1 | head -12
	-$(PY) tests/footprint.py $(HOLDER) tinytris

dosbox: all
	$(PY) tests/dosbox_check.py $(COM) microtris

clean:
	rm -rf build
