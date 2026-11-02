#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -d CodexMeter.app ]; then
  python3 -c 'import tkinter' || { echo 'Install Python 3.12 with Tk from python.org, then retry.'; exit 1; }
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt pyinstaller
  .venv/bin/python scripts/build-macos.py
  source_bundle="$PWD/dist/CodexMeter.app"
else
  source_bundle="$PWD/CodexMeter.app"
fi
mkdir -p "$HOME/Applications"
target="$HOME/Applications/CodexMeter.app"
if /usr/bin/pgrep -f "$target/Contents/MacOS/CodexMeter" >/dev/null 2>&1; then
  echo 'Quit Codex Meter from its menu bar menu before reinstalling.'; exit 1
fi
/usr/bin/codesign --verify --deep --strict "$source_bundle"
staging=$(mktemp -d "$HOME/Applications/.codex-meter-install.XXXXXX")
/usr/bin/ditto "$source_bundle" "$staging/CodexMeter.app"
if [ -e "$target" ]; then mv "$target" "$staging/previous.app"; fi
if ! mv "$staging/CodexMeter.app" "$target"; then
  if [ -d "$staging/previous.app" ]; then mv "$staging/previous.app" "$target"; fi
  exit 1
fi
if [ ! -e "$HOME/Desktop/Codex Meter.app" ]; then ln -s "$target" "$HOME/Desktop/Codex Meter.app"; fi
echo "Installed: $target"
/usr/bin/open "$target"
