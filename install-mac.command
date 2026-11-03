#!/bin/bash
# Installs mosaic on a Mac. Double-click this file (if macOS won't open it, see the README's
# "Install" section), or run it in Terminal:  bash install-mac.command
#
# It installs conda (Miniforge, in ~/miniforge3) if you don't have conda yet, makes a conda
# environment called "mosaic" with everything mosaic needs, and puts mosaic in
# your Applications folder. Running it again updates an earlier installation. It needs an
# internet connection and about 2 GB of disk space; the first run takes 5-15 minutes.
#
# mosaic's own updates run this file from the new version (mosaic/updates.py), with
# MOSAIC_UPDATE=1 (no questions), MOSAIC_PREFIX (the environment to update; conda is
# needed only if environment.yml changed), MOSAIC_WAIT_PID (wait for mosaic to close),
# MOSAIC_RESULT (a file to write "ok" or "failed: why" to) and MOSAIC_LOCK (a file to
# remove at the end).
#
# For testing: MOSAIC_ENV (environment name), MOSAIC_APP_DIR (where the app goes),
# MOSAIC_NO_OPEN=1 (don't start mosaic or wait for Return at the end).
set -eo pipefail
cd "$(dirname "$0")"
ENV_NAME="${MOSAIC_ENV:-mosaic}"
UPDATING="${MOSAIC_UPDATE:-}"

step() { printf '\n==> %s\n' "$*"; }
finish() {
  [ -n "$MOSAIC_NO_OPEN" ] || [ -n "$UPDATING" ] && return
  printf '\nPress Return to close this window. '
  read -r _ || true
}
report() {
  if [ -n "$MOSAIC_RESULT" ]; then printf '%s\n' "$1" > "$MOSAIC_RESULT"; fi
  if [ -n "$MOSAIC_LOCK" ]; then rm -f "$MOSAIC_LOCK"; fi
  return 0
}
failed() {
  trap - ERR
  printf '\nThe installation stopped: %s\n' "$1"
  printf 'Nothing else was changed. You can run this installer again after fixing the problem.\n'
  report "failed: $1"
  # An update that didn't go in: open the version there is, which says what happened
  if [ -n "$UPDATING" ] && [ -z "$MOSAIC_NO_OPEN" ] && [ -d "${APP_DIR:-/Applications}/mosaic.app" ]; then
    open "${APP_DIR:-/Applications}/mosaic.app" || true
  fi
  finish
  exit 1
}
trap 'failed "a step failed (the messages above say why)"' ERR
env_hash() { shasum -a 256 environment.yml | cut -d' ' -f1; }

[ "$(uname)" = "Darwin" ] || failed "this installer is for Macs; on Windows use install-windows.bat"
[ -f environment.yml ] || failed "run this file from inside the mosaic folder you downloaded"
APP_DIR="${MOSAIC_APP_DIR:-/Applications}"

# 0. An update from mosaic itself: it closes first
if [ -n "$MOSAIC_WAIT_PID" ]; then
  step "Waiting for mosaic to close"
  for _ in $(seq 1 600); do
    kill -0 "$MOSAIC_WAIT_PID" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$MOSAIC_WAIT_PID" 2>/dev/null; then failed "mosaic didn't close"; fi
fi

# 1. Conda: use the one you have, or install Miniforge
find_conda() {
  if command -v conda >/dev/null 2>&1 && [ -x "$(command -v conda)" ]; then command -v conda; return; fi
  for d in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/opt/anaconda3" \
           /opt/homebrew/Caskroom/miniforge/base /usr/local/Caskroom/miniforge/base /opt/miniconda3 /opt/anaconda3; do
    if [ -x "$d/bin/conda" ]; then echo "$d/bin/conda"; return; fi
  done
  # The base installation the environment is in (envs/<name> inside it)
  if [ -n "$MOSAIC_PREFIX" ] && [ -x "$MOSAIC_PREFIX/../../bin/conda" ]; then
    echo "$MOSAIC_PREFIX/../../bin/conda"
  fi
}

if [ -n "$MOSAIC_PREFIX" ]; then
  # 2. An update: the environment mosaic runs in, brought up to date only if what it needs changed
  PREFIX="$MOSAIC_PREFIX"
  [ -x "$PREFIX/bin/python" ] || failed "mosaic's environment isn't at $PREFIX any more"
  if [ "$(cat "$PREFIX/etc/mosaic/environment.sha256" 2>/dev/null || true)" = "$(env_hash)" ]; then
    step "The tools mosaic uses are up to date"
  else
    CONDA="$(find_conda || true)"
    [ -n "$CONDA" ] || failed "this update needs conda, and conda wasn't found"
    step "Updating the tools mosaic uses (this can take a few minutes)"
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
    step "Making the \"$ENV_NAME\" environment (this downloads the tools mosaic uses)"
    "$CONDA" env create -n "$ENV_NAME" -f environment.yml
  fi
  PREFIX="$("$CONDA" run -n "$ENV_NAME" python -c 'import sys; print(sys.prefix)')"
fi
PY="$PREFIX/bin/python"
# What the environment was made from, so an update knows whether it needs conda
mkdir -p "$PREFIX/etc/mosaic"
env_hash > "$PREFIX/etc/mosaic/environment.sha256"

# 3. mosaic itself, copied into the environment (this folder can be deleted afterwards)
step "Installing mosaic"
"$PY" -m pip install --upgrade --no-warn-script-location .

# 4. The app, in Applications (or your own Applications folder if that one isn't writable)
if ! mkdir -p "$APP_DIR" 2>/dev/null || [ ! -w "$APP_DIR" ]; then
  APP_DIR="$HOME/Applications"
  mkdir -p "$APP_DIR"
fi
step "Putting mosaic in $APP_DIR"
"$PY" packaging/macos/make_app.py --dest "$APP_DIR" >/dev/null
# Notes for mosaic's updates: installed by this installer, and where the app is
echo mac > "$PREFIX/etc/mosaic/installer"
printf '%s\n' "$APP_DIR" > "$PREFIX/etc/mosaic/app_dir"

trap - ERR
report ok
printf '\nmosaic is installed: %s/mosaic.app\n' "$APP_DIR"
if [ -z "$UPDATING" ]; then
  printf 'From now on it updates itself (Settings > Updates).\n'
fi
if [ -z "$MOSAIC_NO_OPEN" ]; then
  open "$APP_DIR/mosaic.app"
fi
finish
