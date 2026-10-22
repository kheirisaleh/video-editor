#!/bin/sh
# Download the Apple style emoji images (64px PNG) used for text overlays.
# The images come from the emoji-datasource-apple npm package; the artwork belongs
# to Apple, so it is fetched at build time instead of being stored in this repository.
set -eu

VERSION="${EMOJI_DATASOURCE_VERSION:-16.0.0}"
TARGET="${1:-$(dirname "$0")/../backend/studio/assets/emoji/apple}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
npm pack --silent "emoji-datasource-apple@${VERSION}" >/dev/null
tar -xzf "emoji-datasource-apple-${VERSION}.tgz" package/img/apple/64
cd - >/dev/null
mkdir -p "$TARGET"
cp "$tmp"/package/img/apple/64/*.png "$TARGET"/
echo "installed $(ls "$TARGET" | wc -l) emoji images into $TARGET"
