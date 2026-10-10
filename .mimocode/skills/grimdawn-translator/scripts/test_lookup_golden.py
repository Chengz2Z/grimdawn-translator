#!/usr/bin/env python3
"""Golden regression tests for lookup_term ranking.

Run:
  python test_lookup_golden.py
  python test_lookup_golden.py --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lookup_term import (  # noqa: E402
    active_rules,
    load_config,
    load_disambiguation,
    load_index_cached,
    lookup,
    resolve_roots,
)

CASES_PATH = HERE / "golden_cases.json"


def run(verbose: bool = False) -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cfg = load_config()
    disc = load_disambiguation()
    zh_roots, en_roots, _ = resolve_roots(cfg, None, None, None)
    idx, cache_state = load_index_cached(zh_roots, en_roots, use_cache=True)
    if verbose:
        print(f"index: {cache_state} entries={len(idx.by_key)}")

    failed = 0
    for i, case in enumerate(cases, 1):
        q = case["query"]
        use_rules = not case.get("no_rules")
        rules = active_rules(disc, q, case.get("context") or "") if use_rules else []
        hits, notes = lookup(idx, q, limit=12, rules=rules)
        keys = [h.entry.key for h in hits]
        zh_all = " | ".join(h.entry.zh_clean for h in hits)
        top = hits[0] if hits else None
        errors: list[str] = []

        allow_miss = bool(case.get("allow_miss"))
        min_hits = case.get("min_hits", 0 if allow_miss else 1)
        if len(hits) < min_hits:
            errors.append(f"hits={len(hits)} < min_hits={min_hits}")

        forbid = case.get("forbid_keys") or []
        for fk in forbid:
            if fk in keys:
                # forbid only if it is top or ranked above expected
                top_idx = keys.index(fk)
                expect_any = case.get("expect_any_keys") or []
                if not expect_any or top_idx == 0 or (
                    all(e not in keys for e in expect_any)
                ):
                    errors.append(f"forbidden key present: {fk} (at #{top_idx + 1})")

        expect_any = case.get("expect_any_keys") or []
        if expect_any:
            if not any(e in keys for e in expect_any):
                errors.append(f"none of expect_any_keys in results: {expect_any}; got {keys[:5]}")
            else:
                # prefer expected key in top 3
                best = min(keys.index(e) for e in expect_any if e in keys)
                if best > 2:
                    errors.append(f"expected key only at rank {best + 1}: {keys[:5]}")

        for frag in case.get("expect_zh_contains") or []:
            if frag not in zh_all:
                errors.append(f"zh fragment missing: {frag!r}; got {zh_all[:80]!r}")

        if case.get("forbid_top_type"):
            if top and top.entry.tag_type in case["forbid_top_type"]:
                errors.append(f"top type {top.entry.tag_type} forbidden")

        status = "PASS" if not errors else "FAIL"
        if errors:
            failed += 1
        if verbose or errors:
            top_s = f"{top.entry.key} / {top.entry.zh_clean!r} / {top.tier}" if top else "MISS"
            print(f"[{status}] #{i} {q!r} -> {top_s}")
            if notes and (verbose or errors):
                print(f"       rules: {notes}")
            if verbose:
                for h in hits[:5]:
                    print(f"       {h.tier:7} {h.score:5} {h.entry.key:40} {h.entry.zh_clean[:24]}")
            for e in errors:
                print(f"       !! {e}")

    total = len(cases)
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    return run(verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
