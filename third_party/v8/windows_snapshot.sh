#!/usr/bin/env bash
set -euo pipefail

snapshot_wine="$PWD/$1"
snapshot_wineserver="$PWD/$2"
snapshot_tool="$PWD/$3"
shift 3

# An action-owned prefix; never use the user's Wine state or install components.
export WINEPREFIX="$(mktemp -d)"
export WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
export WINEARCH=win64
trap '"$snapshot_wineserver" -k' EXIT
"$snapshot_wine" "$snapshot_tool" "$@"
