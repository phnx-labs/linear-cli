#!/bin/sh
# POSIX sh (not bash): runs under dash too, so `sh install.sh` and
# `curl ... | sh` both work — agents-cli's `cli install` invokes us via `sh`.
set -eu

REPO="phnx-labs/linear-cli"
VERSION="${LINEAR_CLI_VERSION:-v0.13.0}"
EXPECTED_SHA256="${LINEAR_CLI_SHA256:-d62ee380d5565e483f0750ded837b5d453fcc380ffab14fe1d34249d2079a1c2}"
URL="https://raw.githubusercontent.com/${REPO}/${VERSION}/linear"

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

verify_sha256() {
  file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' "$EXPECTED_SHA256" "$file" | sha256sum -c - >/dev/null
  elif command -v shasum >/dev/null 2>&1; then
    actual="$(shasum -a 256 "$file" | awk '{print $1}')"
    [ "$actual" = "$EXPECTED_SHA256" ]
  else
    echo "sha256sum or shasum is required to verify the download." >&2
    exit 1
  fi
}

INSTALL_DIR="$(pick_install_dir)"
TARGET="${INSTALL_DIR}/linear"
TMP="$(mktemp "${TARGET}.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

echo "Downloading linear-cli to ${TARGET}"
curl -fsSL "$URL" -o "$TMP"
if ! verify_sha256 "$TMP"; then
  echo "Checksum verification failed for ${URL}" >&2
  exit 1
fi
mv "$TMP" "$TARGET"
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
