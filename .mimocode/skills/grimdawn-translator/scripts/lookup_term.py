#!/usr/bin/env python3
"""Grim Dawn EN/ZH term lookup via configurable Text_EN / Text_ZH roots.

Workflow: English -> tagKey in Text_EN -> Chinese in Text_ZH for the same tagKey.

Usage:
  python lookup_term.py "Blade Arc"
  python lookup_term.py "狼人"
  python lookup_term.py "Resilience" --zh-root D:/path/Text_ZH --en-root D:/path/Text_EN
  python lookup_term.py --list-sources
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"
TAG_RE = re.compile(r"^([A-Za-z0-9_]+)=(.*)$")


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {"active": "local", "sources": {}}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def has_tags(p: Path) -> bool:
    return p.is_dir() and any(p.glob("tags*.txt"))


def expand_roots(base: Path | None, subdirs: list[str] | None) -> list[Path]:
    if not base:
        return []
    roots: list[Path] = []
    if base.is_dir():
        if has_tags(base):
            roots.append(base)
        for sub in subdirs or []:
            p = base / sub if sub else base
            if p.is_dir() and p not in roots and has_tags(p):
                roots.append(p)
        if not roots:
            roots.append(base)
    return roots


def resolve_roots(cfg: dict, source: str | None, zh_root: str | None, en_root: str | None):
    if zh_root or en_root:
        zh = Path(zh_root) if zh_root else None
        en = Path(en_root) if en_root else None
        return expand_roots(zh, ["", "aom", "fg", "foa"]), expand_roots(
            en, ["en/text_en", "en_gdx1/text_en", "en_gdx2/text_en", "en_gdx3/text_en"]
        ), (zh_root or en_root)

    sources = cfg.get("sources") or {}
    name = source or cfg.get("active")
    if name not in sources:
        raise SystemExit(f"unknown source: {name!r}. Try --list-sources")
    src = sources[name]

    def p(raw: str | None) -> Path | None:
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            # resolve relative to skill dir so the package is portable
            path = (SKILL_DIR / path).resolve()
        return path

    zh = p(src.get("zh"))
    en = p(src.get("en"))
    zh_roots = expand_roots(zh, src.get("zh_subdirs"))
    en_roots = expand_roots(en, src.get("en_subdirs"))
    return zh_roots, en_roots, name


def iter_tags(roots: list[Path]):
    seen = set()
    for root in roots:
        if not root or not root.is_dir():
            continue
        for path in sorted(root.rglob("*.txt")):
            key = path.resolve()
            if key in seen:
                continue
            seen.add(key)
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = path.name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                m = TAG_RE.match(line.strip())
                if m:
                    yield rel, lineno, m.group(1), m.group(2)


def search(roots: list[Path], query: str, ignore_case: bool, limit: int):
    hits = []
    q = query.lower() if ignore_case else query
    for rel, lineno, key, value in iter_tags(roots):
        hay_key = key.lower() if ignore_case else key
        hay_val = value.lower() if ignore_case else value
        if q in hay_val or q in hay_key:
            hits.append((rel, lineno, key, value))
            if len(hits) >= limit:
                break
    return hits


def by_keys(roots: list[Path], keys: set[str]):
    out = {}
    if not keys:
        return out
    want = set(keys)
    for rel, lineno, key, value in iter_tags(roots):
        if key in want and key not in out:
            out[key] = (rel, lineno, value)
            if len(out) == len(want):
                break
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Grim Dawn EN/ZH term lookup")
    p.add_argument("query", nargs="?", help="English or Chinese term / tag key fragment")
    p.add_argument("--source", help="config source name")
    p.add_argument("--zh-root", help="override Text_ZH root")
    p.add_argument("--en-root", help="override Text_EN root")
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--case-sensitive", action="store_true")
    p.add_argument("--en-only", action="store_true")
    p.add_argument("--zh-only", action="store_true")
    p.add_argument("--list-sources", action="store_true")
    args = p.parse_args(argv)

    cfg = load_config()

    if args.list_sources:
        active = cfg.get("active")
        for name, src in (cfg.get("sources") or {}).items():
            mark = "*" if name == active else " "
            print(f"{mark} {name}  zh={src.get('zh')}  en={src.get('en')}")
        return 0

    if not args.query:
        p.print_help()
        return 2

    zh_roots, en_roots, src_name = resolve_roots(cfg, args.source, args.zh_root, args.en_root)
    query = args.query.strip()
    ignore_case = not args.case_sensitive

    en_hits = [] if args.zh_only else search(en_roots, query, ignore_case, args.limit)
    zh_hits = [] if args.en_only else search(zh_roots, query, ignore_case, args.limit)
    keys = {h[2] for h in en_hits} | {h[2] for h in zh_hits}
    en_map = by_keys(en_roots, keys)
    zh_map = by_keys(zh_roots, keys)

    print(f"Query: {query}")
    print(f"Source: {src_name}")
    for r in zh_roots:
        print(f"  ZH: {r}")
    for r in en_roots:
        print(f"  EN: {r}")
    print()

    if not keys:
        print("No hits.")
        return 1

    if args.zh_only:
        for rel, lineno, key, value in zh_hits:
            print(f"ZH  {rel}:{lineno}  {key}={value}")
        return 0
    if args.en_only:
        for rel, lineno, key, value in en_hits:
            print(f"EN  {rel}:{lineno}  {key}={value}")
        return 0

    order = list(dict.fromkeys([h[2] for h in en_hits] + [h[2] for h in zh_hits]))
    print(f"{'tagKey':<42} {'English':<40} Chinese")
    print("-" * 120)
    for key in order:
        en = en_map.get(key)
        zh = zh_map.get(key)
        ev = (en[2] if en else "—")[:40]
        zv = (zh[2] if zh else "—")[:40]
        print(f"{key:<42} {ev:<40} {zv}")

    print()
    print("Sources:")
    for key in order:
        en = en_map.get(key)
        zh = zh_map.get(key)
        if en:
            print(f"  EN {en[0]}:{en[1]}  {key}={en[2][:90]}")
        if zh:
            print(f"  ZH {zh[0]}:{zh[1]}  {key}={zh[2][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
