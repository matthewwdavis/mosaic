#!/bin/bash
# Installs mosaic on Linux. Run it in a terminal from the mosaic folder:  bash install-linux.sh
#
# It installs conda (Miniforge, in ~/miniforge3) if you don't have conda yet, makes a conda
# environment called "mosaic" with everything mosaic needs (its window uses Qt, which comes
# with it: nothing is installed system-wide and no administrator password is asked for), and
# puts mosaic in your desktop's applications menu, with mosaic documents opening in it. Running
# it again updates an earlier installation. It needs an internet connection and about 2.5 GB
# of disk space; the first run takes 5-15 minutes.
#
# To copy and paste pictures from other programs, mosaic uses your desktop's clipboard tool:
# wl-clipboard on Wayland, xclip on X11 (most desktops have one; your package manager has both).
#
# mosaic doesn't update itself on Linux yet: download the new version and run this file again.
#
# For testing: MOSAIC_ENV (environment name), MOSAIC_DATA_DIR (where the menu entry goes,
# ~/.local/share), MOSAIC_NO_OPEN=1 (don't start mosaic at the end).
set -eo pipefail
cd "$(dirname "$0")"
ENV_NAME="${MOSAIC_ENV:-mosaic}"

step() { printf '\n==> %s\n' "$*"; }
failed() {
  trap - ERR
  printf '\nThe installation stopped: %s\n' "$1"
  printf 'Nothing else was changed. You can run this installer again after fixing the problem.\n'
  exit 1
}
trap 'failed "a step failed (the messages above say why)"' ERR

[ "$(uname)" = "Linux" ] || failed "this installer is for Linux; on a Mac use install-mac.command, on Windows install-windows.bat"
[ -f environment.yml ] || failed "run this file from inside the mosaic folder you downloaded"

# 1. Conda: use the one you have, or install Miniforge
find_conda() {
  if command -v conda >/dev/null 2>&1 && [ -x "$(command -v conda)" ]; then command -v conda; return; fi
  for d in "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/miniconda3" "$HOME/anaconda3" /opt/miniforge3 /opt/miniconda3 /opt/anaconda3 /opt/conda; do
    if [ -x "$d/bin/conda" ]; then echo "$d/bin/conda"; return; fi
  done
}
CONDA="$(find_conda || true)"
if [ -z "$CONDA" ]; then
  step "Installing conda (Miniforge) into ~/miniforge3"
  [ -e "$HOME/miniforge3" ] && failed "$HOME/miniforge3 exists but has no conda in it; move it aside and try again"
  arch="$(uname -m)"   # x86_64 or aarch64
  tmp="$(mktemp -d)"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --progress-bar -o "$tmp/miniforge.sh" "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-${arch}.sh"
  else
    wget -q --show-progress -O "$tmp/miniforge.sh" "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-${arch}.sh"
  fi
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
PY="$PREFIX/bin/python"

# 3. The window: Qt and its web view, inside the environment with everything they need (Macs
#    and Windows use the system's own web view)
step "Installing the window parts (Qt)"
"$CONDA" install -y -q -n "$ENV_NAME" -c conda-forge "pyside6>=6.6,<7" qt6-webengine "qtpy>=2.4"

# 4. mosaic itself, copied into the environment (this folder can be deleted afterwards)
step "Installing mosaic"
"$PY" -m pip install --upgrade --no-warn-script-location .
mkdir -p "$PREFIX/etc/mosaic"
echo linux > "$PREFIX/etc/mosaic/installer"

# 5. The applications menu, and mosaic documents opening in mosaic
DATA_DIR="${MOSAIC_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}}"
step "Putting mosaic in the applications menu"
"$PY" packaging/linux/make_desktop.py --data "$DATA_DIR" >/dev/null
mkdir -p "$HOME/.local/bin"
ln -sf "$PREFIX/bin/mosaic" "$HOME/.local/bin/mosaic"

trap - ERR
printf '\nmosaic is installed. Find it in your applications menu, or run:  mosaic\n'
if ! command -v wl-paste >/dev/null 2>&1 && ! command -v xclip >/dev/null 2>&1; then
  printf 'To paste pictures copied in other programs, install wl-clipboard (Wayland) or xclip (X11).\n'
fi
if [ -z "$MOSAIC_NO_OPEN" ]; then
  (nohup "$PY" -P -m mosaic >/dev/null 2>&1 &)
fi
