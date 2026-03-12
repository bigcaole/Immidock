#!/usr/bin/env bash
set -euo pipefail

REPO="bigcaole/Immidock"
ASSET="immidock-linux-amd64"
INSTALL_PATH="/usr/local/bin/immidock"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required"
  exit 1
fi

url=$(curl -sL "https://api.github.com/repos/${REPO}/releases/latest" | \
  grep -Eo "https://[^\"]+${ASSET}" | head -n 1)

if [ -z "$url" ]; then
  echo "Failed to find release asset ${ASSET}"
  exit 1
fi

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

echo "Downloading ${ASSET}..."
curl -L "$url" -o "$tmpfile"
chmod +x "$tmpfile"

echo "Installing to ${INSTALL_PATH}..."
sudo mv "$tmpfile" "$INSTALL_PATH"

trap - EXIT

echo "ImmiDock installed successfully"
