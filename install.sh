#!/usr/bin/env bash
set -euo pipefail

REPO="bigcaole/Immidock"
INSTALL_PATH="/usr/local/bin/immidock"

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

if [ "$OS" != "linux" ]; then
  echo "Only Linux is supported by the install script."
  exit 1
fi

case "$ARCH" in
  x86_64|amd64)
    ASSET="immidock-linux-amd64"
    ;;
  *)
    echo "Unsupported architecture: $ARCH"
    exit 1
    ;;
esac

if command -v curl >/dev/null 2>&1; then
  META_CMD="curl -sL"
  FILE_CMD="curl -L -o"
elif command -v wget >/dev/null 2>&1; then
  META_CMD="wget -qO-"
  FILE_CMD="wget -qO"
else
  echo "curl or wget is required"
  exit 1
fi

url=$($META_CMD "https://api.github.com/repos/${REPO}/releases/latest" | \
  grep -Eo "https://[^\"]+${ASSET}" | head -n 1)

if [ -z "$url" ]; then
  echo "Failed to find release asset ${ASSET}"
  exit 1
fi

tmpfile=$(mktemp)
trap 'rm -f "$tmpfile"' EXIT

echo "Downloading ${ASSET}..."
$FILE_CMD "$tmpfile" "$url"
chmod +x "$tmpfile"

echo "Installing to ${INSTALL_PATH}..."
sudo mv "$tmpfile" "$INSTALL_PATH"

trap - EXIT

echo "ImmiDock installed successfully"
