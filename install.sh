#!/bin/sh
# POSIX sh (not bash): runs under dash too, so `sh install.sh` and
# `curl ... | sh` both work — agents-cli's `cli install` invokes us via `sh`.
set -eu

REPO="phnx-labs/linear-cli"
BRANCH="${LINEAR_CLI_BRANCH:-main}"
URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}/linear"

pick_install_dir() {
  if [ -w "/usr/local/bin" ]; then
    echo "/usr/local/bin"
  elif [ -w "/opt/homebrew/bin" ]; then
    echo "/opt/homebrew/bin"
  else
    mkdir -p "$HOME/.local/bin"
    echo "$HOME/.local/bin"
  fi
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (3.9+)." >&2
  exit 1
fi

INSTALL_DIR="$(pick_install_dir)"
TARGET="${INSTALL_DIR}/linear"

echo "Downloading linear-cli to ${TARGET}"
curl -fsSL "$URL" -o "$TARGET"
chmod +x "$TARGET"

echo ""
echo "Installed: $TARGET"
if ! echo ":$PATH:" | grep -q ":${INSTALL_DIR}:"; then
  echo ""
  echo "Note: ${INSTALL_DIR} is not on your PATH. Add this to your shell rc:"
  echo "  export PATH=\"${INSTALL_DIR}:\$PATH\""
fi

echo ""
echo "Next: linear setup --api-key <lin_api_...> --agent <your-agent-name>"
