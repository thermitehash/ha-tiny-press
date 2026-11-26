#!/usr/bin/env bash
# Render custom_components/tiny_press/brand/*.png from the SVG masters in assets/.
# Needs rsvg-convert (librsvg2-bin), ImageMagick and optipng.
# The logo masters already carry the DM Sans Bold wordmark as outlines
# (see script/build_logos.py), so no font install is needed here.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=custom_components/tiny_press/brand
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT"

# icons: square, transparent
for n in icon dark_icon; do
  rsvg-convert -w 256 -h 256 --keep-aspect-ratio assets/$n.svg -o "$TMP/$n.png"
  rsvg-convert -w 512 -h 512 --keep-aspect-ratio assets/$n.svg -o "$TMP/$n@2x.png"
  convert "$TMP/$n.png"    -background none -gravity center -extent 256x256 -strip PNG32:$OUT/$n.png
  convert "$TMP/$n@2x.png" -background none -gravity center -extent 512x512 -strip PNG32:$OUT/$n@2x.png
done
# logos: render large, trim, resize to exact short side
for n in logo dark_logo; do
  rsvg-convert -h 1024 assets/$n.svg -o "$TMP/$n-big.png"
  convert "$TMP/$n-big.png" -trim +repage -bordercolor none -border 8 "$TMP/$n-t.png"
  convert "$TMP/$n-t.png" -resize x256 -strip PNG32:$OUT/$n.png
  convert "$TMP/$n-t.png" -resize x512 -strip PNG32:$OUT/$n@2x.png
done
optipng -quiet -o5 $OUT/*.png
