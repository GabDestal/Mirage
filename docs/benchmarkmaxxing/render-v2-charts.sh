#!/bin/sh
# Reporting only: summary JSON -> stdlib SVG -> 1600x900 PNG via native macOS QuickLook.
# Usage: [OUT=dir] sh docs/benchmarkmaxxing/render-v2-charts.sh [--agentdojo f.json] [--agentrx f.json]
set -eu
cd "$(dirname "$0")/../.."
out=${OUT:-docs/benchmarkmaxxing}
python3 benchmarks/charts_v2.py --output "$out" "$@"
render_dir=$(mktemp -d "${TMPDIR:-/tmp}/mirage-v2-charts.XXXXXX")
trap 'rm -rf "$render_dir"' EXIT
for name in agentdojo-v2-headline agentrx-v3-critical-step; do
  # QuickLook scales to a square: wrap first so content keeps its exact scale, then crop.
  { printf '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1600" viewBox="0 0 1600 1600">'
    cat "$out/$name.svg"; printf '</svg>'; } > "$render_dir/$name.svg"
done
qlmanage -t -s 1600 -o "$render_dir" "$render_dir"/*.svg >/dev/null
cat > "$render_dir/crop.swift" <<'SWIFT'
import Foundation
import ImageIO
import CoreGraphics
import UniformTypeIdentifiers
for name in ["agentdojo-v2-headline", "agentrx-v3-critical-step"] {
    let input = URL(fileURLWithPath: "\(CommandLine.arguments[1])/\(name).svg.png")
    let output = URL(fileURLWithPath: "\(CommandLine.arguments[2])/\(name).png")
    let source = CGImageSourceCreateWithURL(input as CFURL, nil)!
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)!
    precondition(image.width == 1600 && image.height == 1600)
    let cropped = image.cropping(to: CGRect(x: 0, y: 0, width: 1600, height: 900))!
    let destination = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(destination, cropped, nil)
    precondition(CGImageDestinationFinalize(destination))
    print("\(name): \(cropped.width)x\(cropped.height)")
}
SWIFT
swift "$render_dir/crop.swift" "$render_dir" "$out"
