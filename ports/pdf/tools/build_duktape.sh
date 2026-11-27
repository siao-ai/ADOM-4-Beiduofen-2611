#!/usr/bin/env bash
# Build the Duktape 2.7.0 command-line interpreter (an ES5.1 engine: no BigInt, no normalize, no Map)
# in ~/adom-ports on the target machine.  No sudo, no package manager: curl + make + cc.
#   ssh user@arm64-host 'bash -s' < ports/pdf/tools/build_duktape.sh
set -euo pipefail
mkdir -p ~/adom-ports && cd ~/adom-ports
[[ -x duktape-2.7.0/duk ]] && { echo "duk already built: $(pwd)/duktape-2.7.0/duk"; exit 0; }
curl -sSL -o duktape-2.7.0.tar.xz https://github.com/svaarala/duktape/releases/download/v2.7.0/duktape-2.7.0.tar.xz
tar xf duktape-2.7.0.tar.xz
make -C duktape-2.7.0 -f Makefile.cmdline >/dev/null
echo "built $(pwd)/duktape-2.7.0/duk"
