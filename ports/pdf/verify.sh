#!/usr/bin/env bash
# Verify the PDF port without opening any viewer window:
#   1. poppler pdfinfo: AcroForm + JavaScript present;  libqpdf (via pikepdf) syntax check
#   2. extract the JavaScript FROM THE PDF with libqpdf (doc-level script + the button's /A action)
#   3. wrap it in a minimal Acrobat object model and press the button once per parity prompt:
#        a) node vm with every post-ES5 global deleted   b) Duktape 2.7 (ES5.1) on the Jetson
# usage: ports/pdf/verify.sh [--no-jetson]
set -euo pipefail
cd "$(dirname "$0")"
HOST=${ADOM_JETSON:-user@arm64-host}
PDF=ADOM-4-Beiduofen-2611.pdf
echo "== pdfinfo"; pdfinfo "$PDF" | grep -E '^(Form|JavaScript|Pages|PDF version|File size)'
pdfinfo "$PDF" | grep -q 'Form: *AcroForm' && pdfinfo "$PDF" | grep -q 'JavaScript: *yes'
echo "== libqpdf structure check + JavaScript extraction"
uv run --quiet --with pikepdf python extract_js.py "$PDF" build/extracted
echo "== Acrobat object-model harness"
# harnesses embed the test prompts; the full set holds exam text that must not land in the repo,
# so they live in a temp dir (and on the Jetson only for the duration of the run)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"; ssh "$HOST" "rm -f ~/adom-ports/harness_*.js" 2>/dev/null || true' EXIT
python3 -B make_harness.py build/extracted "$TMP/harness_public.js" --set public
python3 -B make_harness.py build/extracted "$TMP/harness_public_cr.js" --set public --cr
python3 -B make_harness.py build/extracted "$TMP/harness_full.js" --set full
python3 -B make_harness.py build/extracted "$TMP/harness_full_cr.js" --set full --cr
for h in public public_cr full full_cr; do echo -n "node/ES5 $h: "; node run_node_es5.js "$TMP/harness_$h.js" 2>&1 | grep -E 'RESULT|MISMATCH|Error' || true; done
if [[ "${1-}" != "--no-jetson" ]]; then
  ssh "$HOST" 'bash -s' < tools/build_duktape.sh >/dev/null
  for h in public full full_cr; do
    gzip -c "$TMP/harness_$h.js" | ssh "$HOST" "gunzip > ~/adom-ports/harness_$h.js"
    echo -n "Duktape 2.7 (ES5.1, $HOST) $h: "
    ssh "$HOST" "cd ~/adom-ports && ./duktape-2.7.0/duk harness_$h.js" 2>&1 | grep -E 'RESULT|MISMATCH|Error|error' || true
  done
fi
