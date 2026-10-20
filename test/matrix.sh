#!/bin/sh
# the checks under other entry conditions: registers at entry, load segment, seed. The four run side by side.
# usage: sh test/matrix.sh build/microtris.com

com=$1
dir=$(dirname "$0")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

run() {
	echo "== registers at entry: $1, load segment $2, seed $3"
	python3 -I "$dir/features.py" "$com" microtris --profile "$1" --seg "$2" --seed "$3" &&
	python3 -I "$dir/fuzz.py" "$com" microtris --profile "$1" --seg "$2" --seed "$3" &&
	python3 -I "$dir/footprint.py" "$com" microtris --profile "$1" --seg "$2"
}

n=0
for cfg in "zeroed 0x1000 11" "dos 0x0900 12" "dos 0x5555 13" "zeroed 0xA000 14"; do
	n=$((n + 1))
	(run $cfg) >"$tmp/$n.log" 2>&1 &
	pids="$pids $!"
done

fail=0
n=0
for pid in $pids; do
	n=$((n + 1))
	wait "$pid" || fail=1
	cat "$tmp/$n.log"
done
exit $fail
