#!/usr/bin/env python3
"""Coverage check: terms extracted from source vs batch lookup results.

Usage:
  python check_coverage.py --terms terms.txt --results results.tsv
  python check_coverage.py --terms terms.txt --results results.json --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NUM_RE = re.compile(r"^\d+$")


def load_terms(path: Path) -> list[str]:
    out = []
    for ln in path.read_text(encoding="utf-8-sig").splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def load_results(path: Path) -> dict[str, dict]:
    text = path.read_text(encoding="utf-8-sig")
    rows: dict[str, dict] = {}
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        for r in data:
            rows[str(r.get("query", "")).casefold()] = r
        return rows
    # TSV with header
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return rows
    header = lines[0].split("\t")
    # allow headerless: assume English Chinese tagKey ...
    if header[0].lower() not in ("english", "query", "term"):
        header = ["English", "Chinese", "tagKey", "Type", "Match", "Score", "MissKind", "Retried"]
        body = lines
    else:
        body = lines[1:]
    for ln in body:
        cols = ln.split("\t")
        row = {header[i]: (cols[i] if i < len(cols) else "") for i in range(len(header))}
        q = row.get("English") or row.get("query") or row.get("term") or ""
        rows[q.casefold()] = {
            "query": q,
            "zh": row.get("Chinese") or row.get("zh") or "",
            "tagKey": row.get("tagKey") or row.get("tagkey") or "",
            "match": row.get("Match") or row.get("match") or "",
        }
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    terms = load_terms(Path(args.terms))
    results = load_results(Path(args.results))

    missing = []
    weak = []
    ok = 0
    for t in terms:
        r = results.get(t.casefold())
        if not r or r.get("match") in ("MISS", "", None):
            missing.append(t)
            continue
        if r.get("match") in ("RULE", "WORDS", "PREFIX") or not r.get("zh"):
            weak.append({"query": t, **r})
        else:
            ok += 1

    report = {
        "total": len(terms),
        "ok": ok,
        "weak": weak,
        "missing": missing,
        "coverage": round(ok / len(terms), 4) if terms else 0,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"total={report['total']} ok={ok} weak={len(weak)} missing={len(missing)}")
        if missing:
            print("MISSING:")
            for t in missing:
                print(f"  - {t}")
        if weak:
            print("WEAK:")
            for w in weak:
                print(f"  - {w.get('query')} -> {w.get('zh')} ({w.get('match')})")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
