#!/bin/sh
# Download the uv binary that the packaged app uses to install and run the Python backend.
set -e
UV_VERSION=0.13.10
DEST="$(dirname "$0")/../vendor"
if [ -x "$DEST/uv" ] && [ "$("$DEST/uv" --version | cut -d' ' -f2)" = "$UV_VERSION" ]; then
  exit 0
fi
mkdir -p "$DEST"
curl -fsSL "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-apple-darwin.tar.gz" \
  | tar -xz -C "$DEST" --strip-components 1 uv-aarch64-apple-darwin/uv
