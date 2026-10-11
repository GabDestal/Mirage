#!/bin/sh
# Reporting only: frozen sanitized JSON, stdlib SVG, and native macOS export.
set -eu
cd "$(dirname "$0")/../.."
python3 benchmarks/benchmarkmaxxing_charts.py --frozen-source docs/benchmarkmaxxing/chart-source.json
render_dir=$(mktemp -d "${TMPDIR:-/tmp}/mirage-release-charts.XXXXXX")
trap 'rm -rf "$render_dir"' EXIT
python3 - "$render_dir" <<'PY'
from pathlib import Path
import sys
paths = list(Path('docs/benchmarkmaxxing').glob('*-release.svg'))
assert len(paths) == 3
for path in paths:
    # QuickLook scales to a square: wrap first so content retains its exact scale.
    Path(sys.argv[1], path.name).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1320" height="1320" viewBox="0 0 1320 1320">'
        + path.read_text() + '</svg>')
PY
qlmanage -t -s 1320 -o "$render_dir" "$render_dir"/*-release.svg
cat > "$render_dir/crop.swift" <<'SWIFT'
import Foundation
import ImageIO
import CoreGraphics
import UniformTypeIdentifiers
for name in ["agentrx-critical-step-release", "agentrx-coverage-release", "harnessrisk-safe-completion-release"] {
    let input = URL(fileURLWithPath: "\(CommandLine.arguments[1])/\(name).svg.png")
    let output = URL(fileURLWithPath: "docs/benchmarkmaxxing/\(name).png")
    let source = CGImageSourceCreateWithURL(input as CFURL, nil)!
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)!
    precondition(image.width == 1320 && image.height == 1320)
    let cropped = image.cropping(to: CGRect(x: 0, y: 0, width: 1320, height: 940))!
    let destination = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(destination, cropped, nil)
    precondition(CGImageDestinationFinalize(destination))
    print("\(name): \(cropped.width)x\(cropped.height)")
}
SWIFT
swift "$render_dir/crop.swift" "$render_dir"
