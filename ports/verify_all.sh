#!/usr/bin/env bash
# Rebuild every port from models/ADOM-4-Beiduofen-2611.adom and re-run every parity test.
# Heavy / slow runs go to the Jetson.  Output is tee'd to ports/RESULTS.txt.
#   ports/verify_all.sh            # everything
#   ports/verify_all.sh --no-jetson
set -uo pipefail
cd "$(dirname "$0")"
HOST=${ADOM_JETSON:-user@arm64-host}
J=1; [[ "${1-}" == "--no-jetson" ]] && J=0
SHA=$(shasum -a 256 ../models/ADOM-4-Beiduofen-2611.adom | cut -d' ' -f1)
if [[ ( $SHA == dacaed8bf3fa* || $SHA == 555ea9730671* ) && -z ${ADOM_ALLOW_OLD_MODEL-} ]]; then
  echo "refusing: models/ still holds the superseded model ($SHA); set ADOM_ALLOW_OLD_MODEL=1 to override" >&2; exit 3
fi
exec > >(tee RESULTS.txt) 2>&1
echo "ADOM ports verification, $(date '+%Y-%m-%d %H:%M %Z')"
echo "model sha256: $(shasum -a 256 ../models/ADOM-4-Beiduofen-2611.adom | cut -d' ' -f1)"
echo "public expected sha256: $(shasum -a 256 ../tests/public/parity_expected.json | cut -d' ' -f1)"
echo "full expected sha256:   $(shasum -a 256 ../tests/parity_expected.json | cut -d' ' -f1)"

echo; echo "######## build"
python3 -B pdf/build.py
python3 -B c/build.py && cc -O2 -std=c99 -pedantic -Wall -Wextra -o c/build_adom c/adom.c
python3 -B bookmarklet/build.py
python3 -B bash/build.py
python3 -B python-oneliner/build.py

echo; echo "######## reference sanity + NFKC gap"
echo -n "reference JS vs Python (tests/parity.mjs): "; REFOK=1; RF=$(mktemp); node ../tests/parity.mjs > "$RF" || REFOK=0; tail -1 "$RF"; rm -f "$RF"
python3 -B common/check_nfkc.py

echo; echo "######## PDF (Acrobat JavaScript)"
if (( J )); then pdf/verify.sh; else pdf/verify.sh --no-jetson; fi

echo; echo "######## C (single file)"
echo -n "macOS arm64 clang, public: "; python3 -B c/verify.py --set public | tail -1
echo -n "macOS arm64 clang, full:   "; python3 -B c/verify.py --set full | tail -1
TMPB=$(mktemp -d)
cc -O1 -g -std=c99 -fsanitize=address,undefined -o "$TMPB/adom_asan" c/adom.c
echo -n "macOS ASan+UBSan, full:     "; python3 -B c/verify.py --bin "$TMPB/adom_asan" --set full 2>&1 | grep -E 'RESULT|MISMATCH|ERROR|runtime error'
MCU="-DADOM_MAX_CP=2048 -DADOM_MAX_LABELS=256 -DADOM_MAX_STARTS=512 -DADOM_SEEN_SLOTS=1024 -DADOM_SEEN_ARENA=8192 -DADOM_MAX_SHORT=24"
cc -O2 -std=c99 $MCU -o "$TMPB/adom_mcu" c/adom.c
echo -n "MCU-sized buffers, public:  "; python3 -B c/verify.py --bin "$TMPB/adom_mcu" --set public | tail -1
echo -n "MCU-sized buffers, full (expected short of 100%: prompts > 2048 code points are truncated): "
python3 -B c/verify.py --bin "$TMPB/adom_mcu" --set full | tail -1 | sed 's/^RESULT/MCU-RESULT/'
rm -rf "$TMPB"
python3 -B c/mcu_size.py
if (( J )); then
  scp -q c/adom.c "$HOST":adom-ports/adom.c && ssh "$HOST" 'cd adom-ports && gcc -O2 -std=c99 -pedantic -Wall -Wextra -o adom_c adom.c'
  echo -n "Jetson aarch64 gcc, public: "; python3 -B c/verify.py --runner "ssh $HOST" --bin adom-ports/adom_c --set public | tail -1
  echo -n "Jetson aarch64 gcc, full:   "; python3 -B c/verify.py --runner "ssh $HOST" --bin adom-ports/adom_c --set full | tail -1
fi

echo; echo "######## bookmarklet"
node bookmarklet/verify.js public; node bookmarklet/verify.js full

echo; echo "######## Python one-liner"
python3 -B python-oneliner/verify.py --set public; python3 -B python-oneliner/verify.py --set full | tail -1
if (( J )); then
  scp -q python-oneliner/adom1.py "$HOST":adom-ports/adom1.py
  RPV=$(ssh "$HOST" python3 --version); echo -n "Jetson $RPV, public: "
  python3 -B python-oneliner/verify.py --runner "ssh $HOST" --script adom-ports/adom1.py --set public | tail -1
fi

echo; echo "######## pure Bash"
LBV=$(/bin/bash -c 'echo $BASH_VERSION'); echo "macOS /bin/bash $LBV, public set:"; python3 -B bash/verify.py --set public --sample 400
if (( J )); then
  scp -q bash/adom.sh "$HOST":adom-ports/adom.sh
  RBV=$(ssh "$HOST" 'echo $BASH_VERSION'); echo "Jetson /bin/bash $RBV, full set, 6,715 prompts incl. long exam text:"
  python3 -B bash/verify.py --runner "ssh $HOST" --script adom-ports/adom.sh --set full --sample 300
fi
echo
echo "######## gate"
FAIL=0
(( REFOK )) || { echo "GATE: reference JS disagrees with expected (files mid-update?)"; FAIL=1; }
grep -E 'identical [0-9]+/[0-9]+' RESULTS.txt | grep -v MCU-RESULT | grep -oE 'identical [0-9]+/[0-9]+' | \
  awk -F'[ /]' '$2 != $3 { bad++ } END { exit bad > 0 }' || { echo "GATE: some parity line is short of 100%"; FAIL=1; }
grep -E 'correctly declined' RESULTS.txt | grep -oE 'declined [0-9]+/[0-9]+' | awk -F'[ /]' '$2 != $3 { bad++ } END { exit bad > 0 }' || { echo "GATE: bash declined count short"; FAIL=1; }
SHA2=$(shasum -a 256 ../models/ADOM-4-Beiduofen-2611.adom | cut -d' ' -f1)
[[ $SHA2 == "$SHA" ]] || { echo "GATE: model changed during the run ($SHA -> $SHA2)"; FAIL=1; }
NEED=$(( J ? 22 : 14 )); HAVE=$(grep -v MCU-RESULT RESULTS.txt | grep -cE 'identical [0-9]+/[0-9]+')
(( HAVE >= NEED )) || { echo "GATE: only $HAVE of $NEED parity lines present (a test did not run)"; FAIL=1; }
grep -E 'MISMATCH|Traceback|ERROR|runtime error|RangeError|SyntaxError|TypeError|ReferenceError|error in executing|command not found' RESULTS.txt | grep -v 'MCU-RESULT' && FAIL=1
(( FAIL )) && echo "GATE: FAILED" || echo "GATE: all parity checks at 100%"
exit $FAIL
