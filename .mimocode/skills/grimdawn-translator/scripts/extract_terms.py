#!/usr/bin/env python3
"""Extract candidate EN terms from Grim Dawn patch / forum text.

Usage:
  python extract_terms.py source.md
  python extract_terms.py source.md --out terms.txt
  python extract_terms.py source.md --min-len 3
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# "Name: change" / "Name – change" patch bullets
ROW_RE = re.compile(
    r"^\s*[-*+]?\s*([A-Z][A-Za-z0-9'’\-\. ]{2,60}?)\s*(?::|–|—|-)\s+"
)
# fenced code / placeholders to skip
SKIP_LINE_RE = re.compile(r"^(\s*```|\s*\||\s*#{1,6}\s|\s*!\[)")

# common non-term tails in parenthetical notes
STRIP_TAIL_RE = re.compile(r"\s*\([^)]*\)\s*$")

# bare labels that are not game terms when alone
STOPWORDS = {
    "component",
    "note",
    "essence",
    "item",
    "skill",
    "set",
    "quest",
    "boss",
    "misc",
    "fix",
    "fixed",
    "known issues",
    "general",
    "ui",
    "audio",
    "multiplayer",
}


def extract(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        if SKIP_LINE_RE.match(raw):
            continue
        m = ROW_RE.match(raw)
        if not m:
            continue
        t = STRIP_TAIL_RE.sub("", m.group(1)).strip(" .:;-–—")
        if len(t) < 3:
            continue
        # drop pure numbers / version-ish
        if re.fullmatch(r"[\d\.\s%+]+", t):
            continue
        key = t.casefold()
        if key in STOPWORDS:
            continue
        if key not in seen:
            seen.add(key)
            terms.append(t)
    return terms


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract EN terms from patch text")
    ap.add_argument("source", help="markdown/text file")
    ap.add_argument("--out", help="write terms (one per line)")
    ap.add_argument("--min-len", type=int, default=3)
    args = ap.parse_args()
    path = Path(args.source)
    text = path.read_text(encoding="utf-8", errors="replace")
    terms = [t for t in extract(text) if len(t) >= args.min_len]
    body = "\n".join(terms) + "\n"
    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        print(f"Wrote {args.out} ({len(terms)} terms)", file=sys.stderr)
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
