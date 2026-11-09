#!/bin/sh
# Reproducible installation of the frozen engine kernel (lot E1).
#   install.sh <target-dir> [--online]
# Installs exactly kernel/package-lock.json into <target-dir> from the offline npm cache (online only to refill the
# cache), drops the optional native packages built for musl (this host is glibc; the reference installation has
# none), then checks every installed package against kernel/installed.json. Never touches a running installation:
# the target must not exist or be empty. Cache location: WALTER_KERNEL_NPM_CACHE (default /services/dsh/npm-cache).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
TARGET=${1:?usage: install.sh <target-dir> [--online]}
MODE=--offline; [ "${2:-}" = "--online" ] && MODE=--prefer-offline
CACHE=${WALTER_KERNEL_NPM_CACHE:-/services/dsh/npm-cache}
if [ -e "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then echo "target not empty: $TARGET" >&2; exit 2; fi
mkdir -p "$TARGET"
cp "$HERE/package.json" "$HERE/package-lock.json" "$TARGET/"
(cd "$TARGET" && npm ci --cache "$CACHE" $MODE --no-audit --no-fund --loglevel=error)
python3 - "$TARGET" <<'EOF'
import json, shutil, sys
from pathlib import Path
t = Path(sys.argv[1]); lock = json.loads((t / 'package-lock.json').read_text())['packages']
for key, meta in lock.items():
    name = key.rsplit('node_modules/', 1)[-1]
    if key.startswith('node_modules/') and meta.get('optional') and 'musl' in name and 'glibc' not in meta.get('libc', []):
        p = t / key
        if p.exists():
            shutil.rmtree(p); print('removed optional musl package', name)
EOF
python3 "$HERE/verify.py" check "$TARGET"
