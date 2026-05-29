#!/usr/bin/env python3
"""Replace the `flutter.fonts` block of pubspec.yaml from tool/fonts.generated.yaml.

Preserves all other keys, comments, and ordering. Idempotent.

Usage:
    python3 scripts/merge_fonts_into_pubspec.py
    python3 scripts/merge_fonts_into_pubspec.py --pubspec custom.yaml --fonts custom.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBSPEC = REPO_ROOT / "pubspec.yaml"
DEFAULT_FONTS = REPO_ROOT / "tool" / "fonts.generated.yaml"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pubspec", type=Path, default=DEFAULT_PUBSPEC)
    p.add_argument("--fonts", type=Path, default=DEFAULT_FONTS)
    args = p.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    if not args.pubspec.exists():
        print(f"error: {args.pubspec} not found", file=sys.stderr)
        return 1
    if not args.fonts.exists():
        print(f"error: {args.fonts} not found", file=sys.stderr)
        return 1

    pubspec = yaml.load(args.pubspec)
    fonts = yaml.load(args.fonts)

    flutter_block = pubspec.get("flutter")
    if flutter_block is None:
        pubspec["flutter"] = {}
        flutter_block = pubspec["flutter"]

    new_fonts = fonts["flutter"]["fonts"]
    flutter_block["fonts"] = new_fonts

    with args.pubspec.open("w") as f:
        yaml.dump(pubspec, f)
    print(f"merged {args.fonts} → {args.pubspec}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
