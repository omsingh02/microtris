# make        build build/microtris.com and print its size
# make verify build, prove the bytes are reproducible, run the six feature checks on the VM
# make dosbox cross-check in the real DOSBox (needs dosbox, xdotool, Xvfb, ImageMagick)
NASM ?= nasm
PY   ?= python3 -I
COM   = build/microtris.com

all: $(COM)
	@printf '%s: %s bytes\n' $(COM) "$$(stat -c %s $(COM))"

$(COM): src/microtris.asm
	@mkdir -p build
	$(NASM) -f bin -l build/microtris.lst src/microtris.asm -o $(COM)

verify: all
	$(PY) tests/features.py $(COM) tinytris

dosbox: all
	$(PY) tests/dosbox_check.py $(COM) tinytris

clean:
	rm -rf build
