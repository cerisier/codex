#!/usr/bin/env bash
set -euo pipefail

probe_root="$PWD"
probe_clang="$probe_root/$1"
probe_overlay="$probe_root/$2"
probe_include="$probe_root/$3"
probe_output="$probe_root/$4"
probe_tmp="$(mktemp -d)"

exec >"$probe_output" 2>&1
"$probe_clang" --version
test -f "$probe_include/wlantypes.h"

probe() {
    printf '#if !__has_include(<WlanTypes.h>)\n#error CASE_OVERLAY_LOOKUP_FAILED\n#endif\n' |
        "$probe_clang" --target=x86_64-pc-windows-msvc -E -x c - -nostdinc \
            -isystem "$probe_include" -ivfsoverlay "$probe_overlay"
}

printf 'execroot working directory:\n'
probe
printf 'execroot result: PASS\n'

cd "$probe_tmp"
printf 'different working directory, identical absolute arguments:\n'
if probe; then
    printf 'changed-directory result: PASS (bug not reproduced)\n'
    exit 1
else
    printf 'changed-directory result: FAIL (bug reproduced)\n'
fi
