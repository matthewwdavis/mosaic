#!/bin/bash
# Installs (or updates) mosaic on a Mac or on Linux with one line in Terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/matthewwdavis/mosaic/main/install.sh | bash
#
# It downloads the newest release into a temporary folder and runs that release's installer
# (install-mac.command on a Mac, install-linux.sh on Linux), the same one the README's
# step-by-step install uses, then deletes the temporary folder. A file downloaded this way isn't
# marked as coming from the internet, so macOS doesn't show its "could not verify" warning.
#
# The whole script is one function, run at the end, so that bash has read all of it before the
# installer starts: when it arrives through a pipe, the installer could otherwise read the rest
# of this script as its own keyboard input.
main() {
  set -eo pipefail
  local url="https://github.com/matthewwdavis/mosaic/releases/latest/download/mosaic.zip"
  local installer
  case "$(uname -s)" in
    Darwin) installer=install-mac.command ;;
    Linux) installer=install-linux.sh ;;
    *) echo "This installs mosaic on a Mac or on Linux. On Windows, see the README's Install section." >&2
       exit 1 ;;
  esac

  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/mosaic-install.XXXXXX")"
  trap 'rm -rf "$tmp"' EXIT

  printf '\n==> Downloading the newest mosaic\n'
  curl -fL --progress-bar -o "$tmp/mosaic.zip" "$url"
  if command -v unzip >/dev/null 2>&1; then
    unzip -q "$tmp/mosaic.zip" -d "$tmp"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m zipfile -e "$tmp/mosaic.zip" "$tmp"
  else
    echo "Unzipping needs unzip or python3; install one with your package manager and run this again." >&2
    exit 1
  fi
  local dir
  dir="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d -name 'mosaic-*' | head -n 1)"
  if [ -z "$dir" ] || [ ! -f "$dir/$installer" ]; then
    echo "The download didn't contain $installer; please report this (see the README's Feedback section)." >&2
    exit 1
  fi

  # The installer reads the keyboard (its closing "Press Return"), so give it the terminal rather
  # than the pipe this script came through
  if { : </dev/tty; } 2>/dev/null; then
    bash "$dir/$installer" </dev/tty
  else
    bash "$dir/$installer" </dev/null
  fi
}

main "$@"
