#!/bin/bash
# Installs FigAssemble on a Mac. Double-click this file (if macOS won't open it, see the README's
# "Install" section), or run it in Terminal:  bash install-mac.command
#
# It installs conda (Miniforge, in ~/miniforge3) if you don't have conda yet, makes a conda
# environment called "figassemble" with everything FigAssemble needs, and puts FigAssemble in
# your Applications folder. Running it again updates an earlier installation. It needs an
# internet connection and about 2 GB of disk space; the first run takes 5-15 minutes.
#
# For testing: FIGASSEMBLE_ENV (environment name), FIGASSEMBLE_APP_DIR (where the app goes),
# FIGASSEMBLE_NO_OPEN=1 (don't start FigAssemble or wait for Return at the end).
set -eo pipefail
cd "$(dirname "$0")"
ENV_NAME="${FIGASSEMBLE_ENV:-figassemble}"

step() { printf '\n==> %s\n' "$*"; }
finish() {
  [ -n "$FIGASSEMBLE_NO_OPEN" ] && return
  printf '\nPress Return to close this window. '
  read -r _ || true
}
failed() {
  printf '\nThe installation stopped: %s\n' "$1"
  printf 'Nothing else was changed. You can run this installer again after fixing the problem.\n'
  finish
  exit 1
}
trap 'failed "a step failed (the messages above say why)"' ERR

[ "$(uname)" = "Darwin" ] || failed "this installer is for Macs; on Windows use install-windows.bat"
[ -f environment.yml ] || failed "run this file from inside the FigAssemble folder you downloaded"

# 1. Conda: use the one you have, or install Miniforge
find_conda() {
  if command -v conda >/dev/null 2>&1 && [ -x "$(command -v conda)" ]; then command -v conda; return; fi
  for d in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/opt/anaconda3" \
           /opt/homebrew/Caskroom/miniforge/base /usr/local/Caskroom/miniforge/base /opt/miniconda3 /opt/anaconda3; do
    if [ -x "$d/bin/conda" ]; then echo "$d/bin/conda"; return; fi
  done
}
CONDA="$(find_conda || true)"
if [ -z "$CONDA" ]; then
  step "Installing conda (Miniforge) into ~/miniforge3"
  [ -e "$HOME/miniforge3" ] && failed "$HOME/miniforge3 exists but has no conda in it; move it aside and try again"
  arch="$(uname -m)"   # arm64 (Apple silicon) or x86_64 (Intel)
  tmp="$(mktemp -d)"
  curl -fL --progress-bar -o "$tmp/miniforge.sh" \
    "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-${arch}.sh"
  bash "$tmp/miniforge.sh" -b -p "$HOME/miniforge3"
  rm -f "$tmp/miniforge.sh"
  CONDA="$HOME/miniforge3/bin/conda"
fi
step "Using conda at $CONDA"

# 2. The environment: made the first time, brought up to date after that
if "$CONDA" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  step "Updating the \"$ENV_NAME\" environment"
  "$CONDA" env update -n "$ENV_NAME" -f environment.yml --prune
else
  step "Making the \"$ENV_NAME\" environment (this downloads the tools FigAssemble uses)"
  "$CONDA" env create -n "$ENV_NAME" -f environment.yml
fi
PREFIX="$("$CONDA" run -n "$ENV_NAME" python -c 'import sys; print(sys.prefix)')"
PY="$PREFIX/bin/python"

# 3. FigAssemble itself, copied into the environment (this folder can be deleted afterwards)
step "Installing FigAssemble"
"$PY" -m pip install --upgrade --no-warn-script-location .

# 4. The app, in Applications (or your own Applications folder if that one isn't writable)
APP_DIR="${FIGASSEMBLE_APP_DIR:-/Applications}"
if ! mkdir -p "$APP_DIR" 2>/dev/null || [ ! -w "$APP_DIR" ]; then
  APP_DIR="$HOME/Applications"
  mkdir -p "$APP_DIR"
fi
step "Putting FigAssemble in $APP_DIR"
"$PY" packaging/macos/make_app.py --dest "$APP_DIR" >/dev/null

trap - ERR
printf '\nFigAssemble is installed: %s/FigAssemble.app\n' "$APP_DIR"
printf 'To update it later, download the newest version and run this installer again.\n'
if [ -z "$FIGASSEMBLE_NO_OPEN" ]; then
  open "$APP_DIR/FigAssemble.app"
fi
finish
