#!/usr/bin/env python3
"""V-7 RESOLVED — @JsonKey coverage audit (inverted RULE 18 carry-over).

Dart `json_serializable` does NOT auto-convert snake_case → camelCase the way Swift's
`.convertFromSnakeCase` does. A freezed response field that maps to a snake_case Flask key
without an explicit `@JsonKey(name: 'snake_case')` annotation will deserialize to `null`
silently (exact I-17 reproduction). This script scans freezed source files for response
classes (heuristic: filename ends with `_response.dart`, `_dto.dart`, or `_model.dart`,
or class name ends with `Response`/`Dto`) and reports any field that lacks `@JsonKey`.

Exit 0 if every field is annotated; exit non-zero with a list of offenders otherwise.

Usage: scripts/check_jsonkey_coverage.py lib/features lib/core/models
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CLASS_RE = re.compile(r"class\s+(\w+)\s+with\s+_\$\1")
FACTORY_RE = re.compile(r"factory\s+(\w+)\s*\(\s*\{([^}]*)\}\s*\)\s*=\s*_\1;", re.DOTALL)
FIELD_RE = re.compile(r"(?:@JsonKey\([^)]*\)\s+)?(?:required\s+)?(?:final\s+)?[\w<>?,\s]+\s+(\w+)\s*[,}]")
JSONKEY_BEFORE_FIELD_RE = re.compile(r"@JsonKey\([^)]*\)\s+(?:required\s+)?(?:final\s+)?[\w<>?,\s]+\s+(\w+)\s*[,}]")


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    offenders: list[str] = []

    for m in FACTORY_RE.finditer(text):
        cls = m.group(1)
        body = m.group(2)
        # Find every parameter and check if it had a @JsonKey immediately before
        # Walk the body collecting (start, end) of @JsonKey-annotated fields.
        annotated_names: set[str] = set()
        for am in JSONKEY_BEFORE_FIELD_RE.finditer(body):
            annotated_names.add(am.group(1))
        # All field names
        all_names: list[str] = []
        # Split on commas at top-level (naive — works for typical freezed factories)
        depth = 0
        buf = ""
        params: list[str] = []
        for ch in body:
            if ch in "<({[":
                depth += 1
            elif ch in ">)}]":
                depth -= 1
            if ch == "," and depth == 0:
                params.append(buf)
                buf = ""
            else:
                buf += ch
        if buf.strip():
            params.append(buf)
        for p in params:
            p = p.strip()
            if not p:
                continue
            # Drop leading @JsonKey(...) if present
            stripped = re.sub(r"@JsonKey\([^)]*\)\s*", "", p)
            tail = stripped.split()
            if not tail:
                continue
            name = tail[-1].rstrip(",;")
            all_names.append(name)
        # Heuristic: only flag classes that look like API responses.
        if not (path.name.endswith(("_response.dart", "_dto.dart", "_model.dart"))
                or cls.endswith(("Response", "Dto", "Model"))):
            continue
        for name in all_names:
            if name not in annotated_names:
                offenders.append(f"{path}: {cls}.{name} missing @JsonKey")
    return offenders


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_jsonkey_coverage.py <dir> [<dir> ...]", file=sys.stderr)
        return 2
    all_offenders: list[str] = []
    for root in argv[1:]:
        p = Path(root)
        if not p.exists():
            continue
        for f in p.rglob("*.dart"):
            if f.name.endswith((".g.dart", ".freezed.dart")):
                continue
            all_offenders.extend(scan_file(f))
    if all_offenders:
        for line in all_offenders:
            print(line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
