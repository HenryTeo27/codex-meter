#!/bin/sh
set -eu
parent=$1; target=$2; stage=$3; version=$4; mode=$5
expected="$HOME/Applications/CodexMeter.app"
updates="$HOME/Library/Application Support/CodexMeter/updates"
[ "$target" = "$expected" ] && [ "$(dirname "$stage")" = "$updates" ]
case "$(basename "$stage")" in update-????????????????????????????????) ;; *) exit 1;; esac
case "$mode" in 0|1|2) ;; *) exit 1;; esac
[ ! -L "$stage" ] && [ ! -L "$target" ] && [ -d "$stage/CodexMeter.app" ]
count=0
while kill -0 "$parent" 2>/dev/null; do
  count=$((count+1)); [ "$count" -lt 60 ] || exit 1; sleep 1
done
backup="$stage/previous.app"
mv "$target" "$backup"
if ! mv "$stage/CodexMeter.app" "$target"; then mv "$backup" "$target"; exit 1; fi
ready="$stage/ready.json"
if [ "$mode" != 0 ]; then
  if [ "$mode" = 1 ]; then
    "$target/Contents/MacOS/CodexMeter" --start-hidden --update-ready "$ready" &
  else
    "$target/Contents/MacOS/CodexMeter" --update-ready "$ready" &
  fi
  child=$!
  count=0
  while [ "$count" -lt 30 ]; do
    if [ -f "$ready" ] && [ "$(/usr/bin/plutil -extract version raw -o - "$ready" 2>/dev/null)" = "$version" ] && [ "$(/usr/bin/plutil -extract pid raw -o - "$ready" 2>/dev/null)" = "$child" ]; then break; fi
    count=$((count+1)); sleep 1
  done
  if [ "$count" -eq 30 ]; then
    kill "$child" 2>/dev/null || true
    wait "$child" 2>/dev/null || true
    # Keep the failed payload for recovery; restore the previously working bundle.
    mv "$target" "$stage/failed.app"; mv "$backup" "$target"
    rm -f "$updates/ready-update.json"
    printf '{"version":"%s","checked_at":%s}' "$version" "$(date +%s)" > "$updates/last-failure.json"
    /usr/bin/open -g -a "$target" --args --start-hidden
    exit 1
  fi
fi
# Only these exact updater-owned paths are removed after an acknowledged start.
rm -rf "$backup"
rm -f "$updates/ready-update.json"
rm -rf "$stage"
