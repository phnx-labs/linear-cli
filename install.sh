#!/bin/sh
# POSIX sh (not bash): runs under dash too, so `sh install.sh` and
# `curl ... | sh` both work — agents-cli's `cli install` invokes us via `sh`.
set -eu

REPO="phnx-labs/linear-cli"
# Pin a release tag (not floating main). Override with LINEAR_CLI_VERSION /
# LINEAR_CLI_SHA256 only when you deliberately install a different revision.
VERSION="${LINEAR_CLI_VERSION:-v0.21.1}"
# SHA-256 of the `linear` file at VERSION. Recomputed whenever VERSION bumps.
EXPECTED_SHA256="${LINEAR_CLI_SHA256:-4055001dcdef84f21b30760a1a1e922dd4d0d7b4b9c936d3a6e5c4c143e7b465}"
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
TMP="$(mktemp "${TMPDIR:-/tmp}/linear-cli.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

echo "Downloading linear-cli ${VERSION} to ${TARGET}"
curl -fsSL "$URL" -o "$TMP"
if ! verify_sha256 "$TMP"; then
  echo "Checksum verification failed for ${URL}" >&2
  echo "Expected SHA-256: ${EXPECTED_SHA256}" >&2
  if command -v sha256sum >/dev/null 2>&1; then
    echo "Actual:   $(sha256sum "$TMP" | awk '{print $1}')" >&2
  elif command -v shasum >/dev/null 2>&1; then
    echo "Actual:   $(shasum -a 256 "$TMP" | awk '{print $1}')" >&2
  fi
  exit 1
fi
# Install only after checksum passes (fail closed).
mkdir -p "$(dirname "$TARGET")"
mv "$TMP" "$TARGET"
trap - EXIT
chmod +x "$TARGET"

echo ""
echo "Installed: $TARGET (${VERSION})"
if ! echo ":$PATH:" | grep -q ":${INSTALL_DIR}:"; then
  echo ""
  echo "Note: ${INSTALL_DIR} is not on your PATH. Add this to your shell rc:"
  echo "  export PATH=\"${INSTALL_DIR}:\$PATH\""
fi

echo ""
echo "Next: linear setup --api-key <lin_api_...> --agent <your-agent-name>"
