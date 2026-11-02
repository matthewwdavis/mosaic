#!/bin/bash
# Installs FigAssemble on a Mac. Double-click this file (if macOS won't open it, see the README's
# "Install" section), or run it in Terminal:  bash install-mac.command
#
# It installs conda (Miniforge, in ~/miniforge3) if you don't have conda yet, makes a conda
# environment called "figassemble" with everything FigAssemble needs, and puts FigAssemble in
# your Applications folder. Running it again updates an earlier installation. It needs an
# internet connection and about 2 GB of disk space; the first run takes 5-15 minutes.
#
# FigAssemble's own updates run this file from the new version (figassemble/updates.py), with
# FIGASSEMBLE_UPDATE=1 (no questions), FIGASSEMBLE_PREFIX (the environment to update; conda is
# needed only if environment.yml changed), FIGASSEMBLE_WAIT_PID (wait for FigAssemble to close),
# FIGASSEMBLE_RESULT (a file to write "ok" or "failed: why" to) and FIGASSEMBLE_LOCK (a file to
# remove at the end).
#
# For testing: FIGASSEMBLE_ENV (environment name), FIGASSEMBLE_APP_DIR (where the app goes),
# FIGASSEMBLE_NO_OPEN=1 (don't start FigAssemble or wait for Return at the end).
set -eo pipefail
cd "$(dirname "$0")"
ENV_NAME="${FIGASSEMBLE_ENV:-figassemble}"
UPDATING="${FIGASSEMBLE_UPDATE:-}"

step() { printf '\n==> %s\n' "$*"; }
finish() {
  [ -n "$FIGASSEMBLE_NO_OPEN" ] || [ -n "$UPDATING" ] && return
  printf '\nPress Return to close this window. '
  read -r _ || true
}
report() {
  if [ -n "$FIGASSEMBLE_RESULT" ]; then printf '%s\n' "$1" > "$FIGASSEMBLE_RESULT"; fi
  if [ -n "$FIGASSEMBLE_LOCK" ]; then rm -f "$FIGASSEMBLE_LOCK"; fi
  return 0
}
failed() {
  trap - ERR
  printf '\nThe installation stopped: %s\n' "$1"
  printf 'Nothing else was changed. You can run this installer again after fixing the problem.\n'
  report "failed: $1"
  # An update that didn't go in: open the version there is, which says what happened
  if [ -n "$UPDATING" ] && [ -z "$FIGASSEMBLE_NO_OPEN" ] && [ -d "${APP_DIR:-/Applications}/FigAssemble.app" ]; then
    open "${APP_DIR:-/Applications}/FigAssemble.app" || true
  fi
  finish
  exit 1
}
trap 'failed "a step failed (the messages above say why)"' ERR
env_hash() { shasum -a 256 environment.yml | cut -d' ' -f1; }

[ "$(uname)" = "Darwin" ] || failed "this installer is for Macs; on Windows use install-windows.bat"
[ -f environment.yml ] || failed "run this file from inside the FigAssemble folder you downloaded"
APP_DIR="${FIGASSEMBLE_APP_DIR:-/Applications}"

# 0. An update from FigAssemble itself: it closes first
if [ -n "$FIGASSEMBLE_WAIT_PID" ]; then
  step "Waiting for FigAssemble to close"
  for _ in $(seq 1 600); do
    kill -0 "$FIGASSEMBLE_WAIT_PID" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$FIGASSEMBLE_WAIT_PID" 2>/dev/null; then failed "FigAssemble didn't close"; fi
fi

# 1. Conda: use the one you have, or install Miniforge
find_conda() {
  if command -v conda >/dev/null 2>&1 && [ -x "$(command -v conda)" ]; then command -v conda; return; fi
  for d in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/opt/anaconda3" \
           /opt/homebrew/Caskroom/miniforge/base /usr/local/Caskroom/miniforge/base /opt/miniconda3 /opt/anaconda3; do
    if [ -x "$d/bin/conda" ]; then echo "$d/bin/conda"; return; fi
  done
  # The base installation the environment is in (envs/<name> inside it)
  if [ -n "$FIGASSEMBLE_PREFIX" ] && [ -x "$FIGASSEMBLE_PREFIX/../../bin/conda" ]; then
    echo "$FIGASSEMBLE_PREFIX/../../bin/conda"
  fi
}

if [ -n "$FIGASSEMBLE_PREFIX" ]; then
  # 2. An update: the environment FigAssemble runs in, brought up to date only if what it needs changed
  PREFIX="$FIGASSEMBLE_PREFIX"
  [ -x "$PREFIX/bin/python" ] || failed "FigAssemble's environment isn't at $PREFIX any more"
  if [ "$(cat "$PREFIX/etc/figassemble/environment.sha256" 2>/dev/null || true)" = "$(env_hash)" ]; then
    step "The tools FigAssemble uses are up to date"
  else
    CONDA="$(find_conda || true)"
    [ -n "$CONDA" ] || failed "this update needs conda, and conda wasn't found"
    step "Updating the tools FigAssemble uses (this can take a few minutes)"
    "$CONDA" env update -p "$PREFIX" -f environment.yml --prune
  fi
else
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
fi
PY="$PREFIX/bin/python"
# What the environment was made from, so an update knows whether it needs conda
mkdir -p "$PREFIX/etc/figassemble"
env_hash > "$PREFIX/etc/figassemble/environment.sha256"

# 3. FigAssemble itself, copied into the environment (this folder can be deleted afterwards)
step "Installing FigAssemble"
"$PY" -m pip install --upgrade --no-warn-script-location .

# 4. The app, in Applications (or your own Applications folder if that one isn't writable)
if ! mkdir -p "$APP_DIR" 2>/dev/null || [ ! -w "$APP_DIR" ]; then
  APP_DIR="$HOME/Applications"
  mkdir -p "$APP_DIR"
fi
step "Putting FigAssemble in $APP_DIR"
"$PY" packaging/macos/make_app.py --dest "$APP_DIR" >/dev/null
# Notes for FigAssemble's updates: installed by this installer, and where the app is
echo mac > "$PREFIX/etc/figassemble/installer"
printf '%s\n' "$APP_DIR" > "$PREFIX/etc/figassemble/app_dir"

trap - ERR
report ok
printf '\nFigAssemble is installed: %s/FigAssemble.app\n' "$APP_DIR"
if [ -z "$UPDATING" ]; then
  printf 'From now on it updates itself (Settings > Updates).\n'
fi
if [ -z "$FIGASSEMBLE_NO_OPEN" ]; then
  open "$APP_DIR/FigAssemble.app"
fi
finish
