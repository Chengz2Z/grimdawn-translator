#!/usr/bin/env python3
"""Verify translation output against source: segment count + number tokens.

Usage:
  python verify_output.py --source en.md --output zh.md
  python verify_output.py --source en.md --output zh.md --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# numbers with optional % / + / . / :
# unsigned + signed-at-boundary; avoid treating range hyphens (1-16) as signs
NUM_TOKEN_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s(\[{,;:，。、：；（【]))[+-]?\d+(?:\.\d+)*%?|\d+(?:\.\d+)*%?"
)
SEG_SPLIT_RE = re.compile(r"\n\s*\n")


def segments(text: str) -> list[str]:
    parts = [p.strip() for p in SEG_SPLIT_RE.split(text) if p.strip()]
    return parts


def number_tokens(text: str) -> list[str]:
    return NUM_TOKEN_RE.findall(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    src = Path(args.source).read_text(encoding="utf-8-sig")
    out = Path(args.output).read_text(encoding="utf-8-sig")

    s_segs, o_segs = segments(src), segments(out)
    s_nums, o_nums = number_tokens(src), number_tokens(out)
    # multiset diff of numbers
    from collections import Counter

    sc, oc = Counter(s_nums), Counter(o_nums)
    missing_nums = sorted((sc - oc).elements())
    extra_nums = sorted((oc - sc).elements())

    report = {
        "segments_source": len(s_segs),
        "segments_output": len(o_segs),
        "segments_match": len(s_segs) == len(o_segs),
        "numbers_source": len(s_nums),
        "numbers_output": len(o_nums),
        "numbers_missing": missing_nums,
        "numbers_extra": extra_nums,
        "numbers_match": not missing_nums and not extra_nums,
        "ok": len(s_segs) == len(o_segs) and not missing_nums and not extra_nums,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"segments {report['segments_source']}→{report['segments_output']} "
            f"{'OK' if report['segments_match'] else 'MISMATCH'}"
        )
        print(
            f"numbers  {report['numbers_source']}→{report['numbers_output']} "
            f"{'OK' if report['numbers_match'] else 'MISMATCH'}"
        )
        if missing_nums:
            print("missing in output:", " ".join(missing_nums[:30]))
        if extra_nums:
            print("extra in output:  ", " ".join(extra_nums[:30]))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
