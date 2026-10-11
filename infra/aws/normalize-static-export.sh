#!/usr/bin/env sh
set -eu
PATH="/usr/bin:$PATH"
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
OUT="$ROOT/web/out"
[ -d "$OUT" ] || { printf 'static export not found: %s\n' "$OUT" >&2; exit 1; }

# Next 16 writes nested route payload folders, while its client requests the flat
# `__next.<route>.__PAGE__.txt` path. Copy those immutable payloads to the requested
# path so static hosts can serve client-side navigation without 404s.
find "$OUT" -type f -path '*/__next.*/__PAGE__.txt' -print |
  while IFS= read -r PAGE; do
    ROUTE_DIR="$(dirname -- "$(dirname -- "$PAGE")")"
    PAYLOAD_DIR="$(basename -- "$(dirname -- "$PAGE")")"
    cp "$PAGE" "$ROUTE_DIR/$PAYLOAD_DIR.__PAGE__.txt"
  done
