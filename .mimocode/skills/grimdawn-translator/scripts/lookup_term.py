#!/usr/bin/env python3
"""Grim Dawn EN/ZH term lookup with exact-first, type-aware ranking.

Workflow: English -> tagKey in Text_EN -> Chinese in Text_ZH for the same tagKey.

Match tiers (high → low):
  EXACT      full EN value equals query
  KEY        tagKey equals query
  PHRASE     contiguous whole-word phrase in EN value
  STRIP      rarity/set prefix stripped, then EXACT/PHRASE
  PREFIX     EN value starts with query as complete words
  WORDS      all query tokens appear as whole words (name-like tags only)

Bare substring matching is never used (it caused false hits like
"All Resist" -> tagChatAll / "L").

Usage:
  python lookup_term.py "Blade Arc"
  python lookup_term.py "狼人"
  python lookup_term.py "Armor" --explain
  python lookup_term.py --batch terms.txt
  python lookup_term.py --list-sources
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"
DISC_PATH = SKILL_DIR / "disambiguation.json"
TAG_RE = re.compile(r"^([A-Za-z0-9_]+)=(.*)$")

# Rarity / set decoration that is usually not part of the tag value itself.
STRIP_TOKENS = (
    "Mythical",
    "Empowered",
    "Awakened",
    "Legendary",
    "Double Rare",
    "Monster Infrequent",
    "Infrequent",
    "Epic",
    "Rare",
    "Common",
    "Magical",
    "Faction",
)

# "Bloodmane Set" -> "Bloodmane"
SET_SUFFIX_RE = re.compile(r"\s+Set$", re.I)

CONTROL_RE = re.compile(r"\^[a-zA-Z0-9]")
BRACE_FMT_RE = re.compile(r"\{[^}]*\}")
WORD_RE = re.compile(r"[A-Za-z0-9']+")

# Multi-word non-exact matches must look like names, not prose.
NAME_TYPES = {
    "skill_name",
    "item_set_name",
    "item",
    "affix",
    "enemy",
    "map",
    "devotion",
    "quest_title",
    "achievement",
    "stat",
}
DESC_TYPES = {"desc", "lore", "patch"}

TYPE_BONUS = {
    "skill_name": 80,
    "item_set_name": 80,
    "item": 60,
    "enemy": 70,
    "map": 65,
    "devotion": 55,
    "quest_title": 50,
    "achievement": 50,
    "stat": 55,
    "affix": 40,
    "class_name": 50,
    "ui": 35,
    "other": 0,
    "desc": -80,
    "lore": -120,
    "patch": -120,
}

TIER_BONUS = {
    "EXACT": 1000,
    "KEY": 900,
    "STRIP": 820,
    "PHRASE": 700,
    "PREFIX": 620,
    "WORDS": 540,
}

# Prefer these when several exact hits share one EN value (e.g. Armor).
CANONICAL_KEY_RE = re.compile(
    r"(Stats|Stat|Craft|Vendor|LootFilter|CharAttr|CharHeader|Resistance|Damage|"
    r"HUD|Menu|UI|Conversion|Defense|Offense|Attribute)",
    re.I,
)
ITEM_BODY_KEY_RE = re.compile(
    r"(Torso|Head|Hands|Feet|Legs|Shoulder|Ring|Necklace|Medal|Waist|Shield|"
    r"Weapon|Relic|Focus|Belt|Helm|Hood|Chest|Boots|Gloves)",
    re.I,
)


def strip_controls(s: str) -> str:
    s = re.sub(r"\^g<[^>]*>\^c", "", s)
    s = CONTROL_RE.sub("", s)
    s = s.replace("<", "").replace(">", "")
    return s.strip()


def normalize(s: str) -> str:
    """Matching form: controls/format tokens removed, whitespace collapsed, casefolded."""
    s = strip_controls(s)
    s = BRACE_FMT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    return s


def tokens(s: str) -> list[str]:
    return WORD_RE.findall(normalize(s))


def classify_tag(key: str) -> str:
    k = key.lower()
    if (
        "lore" in k
        or "journal" in k
        or k.endswith("text")
        or "_text" in k
        or ("tip" in k and "text" in k)
        or ("note" in k and "text" in k)
    ):
        return "lore"
    if "patch" in k or k.startswith("tagpatch"):
        return "patch"
    if any(x in k for x in ("desc", "description", "tooltip", "tiptext", "info")):
        return "desc"
    if "itemset" in k:
        return "item_set_name" if ("name" in k or k.endswith("set")) else "desc"
    if "skillname" in k or re.search(r"skill.*name", k):
        return "skill_name"
    if re.search(r"skillclassname|class.*name|master.*name", k):
        return "class_name"
    if re.search(r"crafttab|lootfilter|vendortab|hud|console|button|chat|menu", k):
        return "ui"
    if re.search(
        r"weapon|head|torso|hands|feet|legs|shoulder|ring|necklace|medal|waist|"
        r"shield|relic|focus|quiver|belt|helm|hood|chest|gloves|boots|pants|"
        r"armor[a-z]?[0-9]|potion|scroll|charm|augment|enchant|component|crafttab",
        k,
    ):
        if "blueprint" in k:
            return "desc"
        return "item"
    if re.search(r"prefix|suffix|affix|mutator", k):
        return "affix"
    if re.search(
        r"stats|resistance|damage|conversion|defense|offense|attribute|"
        r"health|mana|energy|regen|speed|crit|ability|duration",
        k,
    ):
        return "stat"
    if re.search(r"hud|console|button|chat|lootfilter|vendortab|menu|uipanel|options", k):
        return "ui"
    if re.search(r"enemy|boss|hero|monster|nemesis|npc|creature|race", k):
        return "enemy"
    if re.search(r"map|area|region|location|level|poi|door|waypoint|altar|rift|gate", k):
        return "map"
    if re.search(r"devotion|affinity|constellation|celestial", k):
        return "devotion"
    if re.search(r"^ach|quest|bq_|task|challenge|difficulty", k):
        return "quest_title" if "title" in k or "name" in k else "quest_title"
    return "other"


def is_name_like(tag_type: str) -> bool:
    return tag_type in NAME_TYPES


@dataclass
class Entry:
    key: str
    en: str
    zh: str
    en_src: str = ""
    zh_src: str = ""
    tag_type: str = "other"

    @property
    def en_norm(self) -> str:
        return normalize(self.en)

    @property
    def zh_clean(self) -> str:
        return strip_controls(self.zh)


@dataclass
class Hit:
    entry: Entry
    tier: str
    score: int
    why: str = ""
    matched_on: str = ""  # "en" | "zh" | "key"


@dataclass
class Index:
    by_key: dict[str, Entry] = field(default_factory=dict)
    en_exact: dict[str, list[str]] = field(default_factory=dict)  # norm -> [keys]
    zh_exact: dict[str, list[str]] = field(default_factory=dict)
    en_token: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    roots_zh: list[str] = field(default_factory=list)
    roots_en: list[str] = field(default_factory=list)


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {"active": "local", "sources": {}}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_disambiguation(path: Path | None = None) -> dict:
    """Load user-editable ambiguity rules. Missing file => no rules."""
    p = path or DISC_PATH
    if not p.is_file():
        return {"enabled": True, "rules": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"disambiguation.json parse error: {e}")
    if not isinstance(data, dict):
        raise SystemExit("disambiguation.json must be an object with a 'rules' array")
    data.setdefault("rules", [])
    return data


def rule_applies(query: str, rule: dict, context: str = "") -> bool:
    if not rule.get("enabled", True):
        return False
    ctx = rule.get("context") or ""
    if ctx and ctx.casefold() not in (context or "").casefold():
        return False
    q = query.strip()
    qn = normalize(q)
    pattern = (rule.get("query") or "").strip()
    if not pattern:
        return False
    mode = (rule.get("match") or "exact").lower()
    pn = normalize(pattern)
    if mode == "any":
        return True
    if mode == "exact":
        return qn == pn or q.casefold() == pattern.casefold()
    if mode == "prefix":
        return qn.startswith(pn) or q.casefold().startswith(pattern.casefold())
    if mode == "contains":
        return pn in qn or pattern.casefold() in q.casefold()
    if mode == "regex":
        try:
            return re.search(pattern, q, re.I) is not None
        except re.error:
            return False
    return False


def active_rules(disc: dict, query: str, context: str = "") -> list[dict]:
    return [r for r in (disc.get("rules") or []) if rule_applies(query, r, context)]


def apply_disambiguation(
    hits: list[Hit],
    query: str,
    rules: list[dict],
    idx: Index,
) -> tuple[list[Hit], list[str], list[Hit]]:
    """Adjust ranking by user rules. Returns (hits, applied_notes, emit_hits)."""
    if not rules:
        return hits, [], []

    prefer_tags: set[str] = set()
    prefer_zh: set[str] = set()
    forbid_tags: set[str] = set()
    forbid_zh: set[str] = set()
    force_top = False
    boost = 200
    penalty = 400
    notes: list[str] = []
    emit_zhs: list[str] = []

    for rule in rules:
        boost = int(rule.get("boost", 200))
        penalty = int(rule.get("penalty", 400))
        if rule.get("force_top"):
            force_top = True
        for t in rule.get("prefer_tags") or []:
            prefer_tags.add(t)
        for z in rule.get("prefer_zh") or []:
            prefer_zh.add(normalize(z))
        for t in rule.get("forbid_tags") or []:
            forbid_tags.add(t)
        for z in rule.get("forbid_zh") or []:
            forbid_zh.add(normalize(z))
        if rule.get("emit_zh"):
            emit_zhs.append(str(rule["emit_zh"]).strip())
        label = rule.get("id") or rule.get("query") or "?"
        note = rule.get("note") or ""
        notes.append(f"{label}: {note}" if note else label)

    out: list[Hit] = []
    for h in hits:
        zh_n = normalize(h.entry.zh_clean)
        if h.entry.key in forbid_tags:
            continue  # hard exclude forbidden tags
        if zh_n and zh_n in forbid_zh:
            h.score -= penalty
            h.why += f"+rule-pen{penalty}"
            if h.score < -200:
                continue
        if h.entry.key in prefer_tags or (zh_n and zh_n in prefer_zh):
            h.score += boost
            h.why += f"+rule+{boost}"
            if force_top and h.entry.key in prefer_tags:
                h.score += 5000
                h.why += "+force"
        out.append(h)

    out.sort(key=lambda h: (-h.score, h.entry.key))

    # emit synthetic rule hits when nothing acceptable and rule says so
    emit_hits: list[Hit] = []
    if emit_zhs:
        top_ok = False
        if out:
            t = out[0]
            zn = normalize(t.entry.zh_clean)
            top_ok = (
                t.entry.key in prefer_tags
                or (zn and zn in prefer_zh)
                or (t.score >= 800 and t.entry.tag_type not in DESC_TYPES)
            )
        if not top_ok:
            seen = set()
            for z in emit_zhs:
                zn = normalize(z)
                if zn in seen:
                    continue
                seen.add(zn)
                # do not emit if an existing hit already has this zh at top area
                fake = Entry(
                    key=f"(rule:{normalize(query)[:24]})",
                    en=query,
                    zh=z,
                    tag_type="other",
                )
                hit = Hit(
                    entry=fake,
                    tier="RULE",
                    score=9000,
                    why="disambiguation.emit_zh",
                    matched_on="rule",
                )
                emit_hits.append(hit)
    return out, notes, emit_hits


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
        return (
            expand_roots(zh, ["", "aom", "fg", "foa"]),
            expand_roots(en, ["en/text_en", "en_gdx1/text_en", "en_gdx2/text_en", "en_gdx3/text_en"]),
            (zh_root or en_root),
        )

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


def build_index(zh_roots: list[Path], en_roots: list[Path]) -> Index:
    idx = Index()
    idx.roots_zh = [str(r) for r in zh_roots]
    idx.roots_en = [str(r) for r in en_roots]

    en_vals: dict[str, str] = {}
    en_src: dict[str, str] = {}
    for rel, lineno, key, value in iter_tags(en_roots):
        if key not in en_vals:
            en_vals[key] = value
            en_src[key] = f"{rel}:{lineno}"

    zh_vals: dict[str, str] = {}
    zh_src: dict[str, str] = {}
    for rel, lineno, key, value in iter_tags(zh_roots):
        if key not in zh_vals:
            zh_vals[key] = value
            zh_src[key] = f"{rel}:{lineno}"

    for key, en in en_vals.items():
        zh = zh_vals.get(key, "")
        entry = Entry(
            key=key,
            en=en,
            zh=zh,
            en_src=en_src.get(key, ""),
            zh_src=zh_src.get(key, ""),
            tag_type=classify_tag(key),
        )
        idx.by_key[key] = entry
        ne = entry.en_norm
        if ne:
            idx.en_exact.setdefault(ne, []).append(key)
            for t in set(tokens(ne)):
                idx.en_token[t].add(key)

    for key, zh in zh_vals.items():
        if key not in idx.by_key:
            entry = Entry(
                key=key,
                en="",
                zh=zh,
                zh_src=zh_src.get(key, ""),
                tag_type=classify_tag(key),
            )
            idx.by_key[key] = entry
        nz = normalize(zh)
        if nz:
            idx.zh_exact.setdefault(nz, []).append(key)
            for t in set(tokens(nz)):
                idx.en_token[t].add(key)  # reuse inverted index for ZH tokens

    return idx


def strip_query_decorations(q: str) -> list[str]:
    """Return candidate core phrases after peeling rarity/set decorations."""
    out = [q]
    s = q
    changed = True
    while changed:
        changed = False
        for tok in STRIP_TOKENS:
            pattern = re.compile(rf"^{re.escape(tok)}\s+", re.I)
            ns = pattern.sub("", s).strip()
            if ns and ns != s:
                out.append(ns)
                s = ns
                changed = True
    ns = SET_SUFFIX_RE.sub("", s).strip()
    if ns and ns != s:
        out.append(ns)
    # unique, keep order
    seen = set()
    uniq = []
    for x in out:
        k = normalize(x)
        if k and k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def phrase_pattern(phrase: str) -> re.Pattern:
    # whole-word-ish: don't match inside longer alnum tokens
    return re.compile(rf"(?<![a-z0-9]){re.escape(normalize(phrase))}(?![a-z0-9])")


def has_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


def score_entry(
    entry: Entry,
    tier: str,
    query: str,
    matched_on: str = "en",
    zh_vote_bonus: int = 0,
) -> Hit:
    base = TIER_BONUS.get(tier, 0)
    tbonus = TYPE_BONUS.get(entry.tag_type, 0)
    both = 10 if (entry.en and entry.zh) else 0
    # shorter name-like values slightly preferred inside same tier/type
    length_pen = 0
    ref_len = len(entry.en) if entry.en else len(entry.zh_clean)
    if entry.tag_type in NAME_TYPES and ref_len:
        length_pen = -min(20, max(0, ref_len - len(query)) // 2)
    # desc only allowed to win on EXACT/KEY
    if entry.tag_type in DESC_TYPES and tier not in ("EXACT", "KEY"):
        base -= 400
    # generic short EN words: prefer canonical UI/stat over unique item instance
    qn = normalize(query)
    if tier == "EXACT" and len(qn.split()) <= 2 and len(qn) <= 16:
        if CANONICAL_KEY_RE.search(entry.key):
            base += 40
        elif ITEM_BODY_KEY_RE.search(entry.key) and entry.tag_type == "item":
            base -= 30
    score = base + tbonus + both + length_pen + zh_vote_bonus
    # literal (no format-pad) values beat "{%+.0f0} Armor" style EXACT ties
    if tier == "EXACT" and entry.en:
        raw = strip_controls(entry.en).strip().casefold()
        if raw == query.strip().casefold():
            score += 30
            why_extra = "+lit"
        else:
            why_extra = ""
    else:
        why_extra = ""
    why = f"{tier}+{entry.tag_type}+{tbonus}+{both}"
    if zh_vote_bonus:
        why += f"+vote{zh_vote_bonus}"
    why += why_extra
    return Hit(entry=entry, tier=tier, score=score, why=why, matched_on=matched_on)


def lookup(
    idx: Index,
    query: str,
    limit: int = 12,
    rules: list[dict] | None = None,
) -> tuple[list[Hit], list[str]]:
    q = query.strip()
    if not q:
        return [], []
    qn = normalize(q)
    qtoks = tokens(q)
    hits: dict[str, Hit] = {}

    def add(entry: Entry, tier: str, matched_on: str = "en", vote: int = 0) -> None:
        hit = score_entry(entry, tier, q, matched_on=matched_on, zh_vote_bonus=vote)
        # "Mythical X" / "Awakened X" almost always means the item, not the same-named skill
        if tier == "STRIP" and entry.tag_type == "skill_name":
            hit.score -= 50
        if tier == "STRIP" and entry.tag_type in ("item", "item_set_name"):
            hit.score += 30
        prev = hits.get(entry.key)
        if prev is None or hit.score > prev.score:
            hits[entry.key] = hit

    # --- EXACT EN ---
    exact_keys = list(idx.en_exact.get(qn, []))
    # majority ZH vote among exact EN hits
    zh_counter: Counter[str] = Counter()
    for k in exact_keys:
        e = idx.by_key[k]
        if e.zh_clean:
            zh_counter[normalize(e.zh_clean)] += 1
    top_zh_norm = zh_counter.most_common(1)[0][0] if zh_counter else None
    for k in exact_keys:
        e = idx.by_key[k]
        vote = 25 if (top_zh_norm and normalize(e.zh_clean) == top_zh_norm) else 0
        add(e, "EXACT", "en", vote=vote)

    # --- EXACT ZH ---
    for k in idx.zh_exact.get(qn, []):
        e = idx.by_key[k]
        add(e, "EXACT", "zh")

    # --- CJK substring on ZH values (狼人 -> 狼人形态) ---
    if has_cjk(q) and len(qn) >= 2:
        for key, entry in idx.by_key.items():
            if not entry.zh:
                continue
            if entry.tag_type in DESC_TYPES:
                continue
            zn = normalize(entry.zh)
            if not zn or qn not in zn:
                continue
            if zn == qn:
                add(entry, "EXACT", "zh")
            elif zn.startswith(qn) or zn.endswith(qn):
                add(entry, "PHRASE", "zh")
            else:
                add(entry, "WORDS", "zh")

    # --- KEY ---
    if q in idx.by_key:
        add(idx.by_key[q], "KEY")

    # further tiers only if query is long enough (block "L" / "A" junk)
    if len(qn) >= 3 and qtols(qtoks):
        for core in strip_query_decorations(q):
            cn = normalize(core)
            if not cn or cn == qn:
                continue
            # STRIP exact
            for k in idx.en_exact.get(cn, []):
                add(idx.by_key[k], "STRIP", "en")

        # PHRASE / PREFIX / WORDS on EN values (and ZH only for PHRASE when query looks CJK)
        cores = strip_query_decorations(q)
        # prefer the longest core for phrase search
        cores_sorted = sorted(cores, key=lambda x: -len(normalize(x)))
        primary = cores_sorted[0]
        pn = normalize(primary)
        ptoks = tokens(primary)
        multi = len(ptoks) >= 2

        if pn:
            pat = phrase_pattern(primary)
            for key, entry in idx.by_key.items():
                if not entry.en:
                    continue
                # prose never competes for non-exact term resolution
                if entry.tag_type in DESC_TYPES:
                    continue
                # multi-word queries resolve to names/stats/UI, not random 'other'
                if multi and entry.tag_type not in NAME_TYPES and entry.tag_type not in {
                    "ui",
                    "class_name",
                    "stat",
                }:
                    continue
                en_n = entry.en_norm
                if not en_n:
                    continue
                if pat.search(en_n):
                    add(entry, "PHRASE", "en")
                elif en_n.startswith(pn) and (len(en_n) == len(pn) or en_n[len(pn) : len(pn) + 1] in (" ", "-")):
                    add(entry, "PREFIX", "en")

            # WORDS: all tokens as whole words — name-like only
            if ptoks and not multi:
                tok_sets = [idx.en_token.get(t, set()) for t in ptoks]
                if tok_sets and all(tok_sets):
                    cand = set.intersection(*tok_sets)
                    for key in cand:
                        entry = idx.by_key[key]
                        if not is_name_like(entry.tag_type) and entry.tag_type != "ui":
                            continue
                        add(entry, "WORDS", "en")

    ranked = sorted(hits.values(), key=lambda h: (-h.score, h.entry.key))
    applied_notes: list[str] = []
    if rules:
        ranked, applied_notes, emit_hits = apply_disambiguation(ranked, q, rules, idx)
        if emit_hits:
            ranked = emit_hits + [h for h in ranked if h.tier != "RULE"]
    return ranked[:limit], applied_notes


def qtols(qtoks: list[str]) -> bool:
    """Require meaningful token length before fuzzy tiers."""
    if not qtoks:
        return False
    total = sum(len(t) for t in qtoks)
    return total >= 4 and (len(qtoks) >= 2 or len(qtoks[0]) >= 3)


def format_hits(
    query: str,
    hits: list[Hit],
    src_name: str,
    idx: Index,
    explain: bool,
    notes: list[str] | None = None,
) -> str:
    lines = []
    lines.append(f"Query: {query}")
    lines.append(f"Source: {src_name}")
    for r in idx.roots_zh:
        lines.append(f"  ZH: {r}")
    for r in idx.roots_en:
        lines.append(f"  EN: {r}")
    lines.append("")
    if not hits:
        lines.append("No hits.")
        return "\n".join(lines)
    if notes:
        lines.append("Disambiguation:")
        for n in notes:
            lines.append(f"  - {n}")
        lines.append("")

    lines.append(f"{'#':<3} {'tagKey':<42} {'Type':<14} {'Match':<7} {'English':<36} Chinese")
    lines.append("-" * 130)
    for i, h in enumerate(hits, 1):
        ev = strip_controls(h.entry.en)[:36] or "—"
        zv = h.entry.zh_clean[:36] or "—"
        extra = f"  {h.why}" if explain else ""
        lines.append(
            f"{i:<3} {h.entry.key:<42} {h.entry.tag_type:<14} {h.tier:<7} {ev:<36} {zv}{extra}"
        )
    lines.append("")
    lines.append("Sources:")
    for h in hits[:8]:
        e = h.entry
        if e.en_src:
            lines.append(f"  EN {e.en_src}  {e.key}={e.en[:90]}")
        if e.zh_src:
            lines.append(f"  ZH {e.zh_src}  {e.key}={e.zh[:90]}")
    return "\n".join(lines)


def run_batch(
    idx: Index,
    terms: list[str],
    as_json: bool,
    disc: dict | None = None,
    context: str = "",
) -> int:
    rows = []
    for term in terms:
        rules = active_rules(disc or {"rules": []}, term, context) if disc else []
        hits, notes = lookup(idx, term, limit=5, rules=rules)
        top = hits[0] if hits else None
        if top:
            rows.append(
                {
                    "query": term,
                    "zh": top.entry.zh_clean,
                    "tagKey": top.entry.key,
                    "type": top.entry.tag_type,
                    "match": top.tier,
                    "score": top.score,
                    "en": top.entry.en,
                    "rules": notes,
                }
            )
        else:
            rows.append(
                {
                    "query": term,
                    "zh": "",
                    "tagKey": "",
                    "type": "",
                    "match": "MISS",
                    "score": 0,
                    "en": "",
                    "rules": notes,
                }
            )
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("English\tChinese\ttagKey\tType\tMatch\tScore\tRules")
        for r in rows:
            rule_s = ";".join(r.get("rules") or []) if r.get("rules") else ""
            print(f"{r['query']}\t{r['zh']}\t{r['tagKey']}\t{r['type']}\t{r['match']}\t{r['score']}\t{rule_s}")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Grim Dawn EN/ZH term lookup (exact-first, type-aware)")
    p.add_argument("query", nargs="?", help="English or Chinese term / tag key fragment")
    p.add_argument("--source", help="config source name")
    p.add_argument("--zh-root", help="override Text_ZH root")
    p.add_argument("--en-root", help="override Text_EN root")
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--explain", action="store_true", help="show score breakdown")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--batch", help="file with one term per line")
    p.add_argument("--top", type=int, default=5, help="batch: hits to keep (default 5)")
    p.add_argument("--en-only", action="store_true")
    p.add_argument("--zh-only", action="store_true")
    p.add_argument("--list-sources", action="store_true")
    p.add_argument("--list-rules", action="store_true", help="show disambiguation rules")
    p.add_argument("--no-rules", action="store_true", help="ignore disambiguation.json")
    p.add_argument("--context", default="", help="hint for context-scoped rules (e.g. 装备|技能)")
    p.add_argument("--case-sensitive", action="store_true", help="reserved; matching is case-insensitive")
    args = p.parse_args(argv)

    cfg = load_config()

    if args.list_sources:
        active = cfg.get("active")
        for name, src in (cfg.get("sources") or {}).items():
            mark = "*" if name == active else " "
            print(f"{mark} {name}  zh={src.get('zh')}  en={src.get('en')}")
        return 0

    disc = {"enabled": True, "rules": []}
    if not args.no_rules:
        disc = load_disambiguation()

    if args.list_rules:
        rules = disc.get("rules") or []
        print(f"Disambiguation: {DISC_PATH}")
        print(f"enabled={disc.get('enabled', True)}  rules={len(rules)}")
        print()
        for r in rules:
            on = "on " if r.get("enabled", True) else "off"
            mode = r.get("match") or "exact"
            q = r.get("query") or ""
            pref = ",".join(r.get("prefer_tags") or []) or "-"
            pz = ",".join(r.get("prefer_zh") or []) or "-"
            fb = ",".join(r.get("forbid_tags") or []) or "-"
            print(f"[{on}] {r.get('id','?'):<28} {mode:<8} {q!r}")
            print(f"       prefer_tags={pref}")
            print(f"       prefer_zh={pz}  forbid_tags={fb}")
            if r.get("emit_zh"):
                print(f"       emit_zh={r['emit_zh']!r}")
            if r.get("note"):
                print(f"       note: {r['note']}")
        return 0

    if not args.query and not args.batch:
        p.print_help()
        return 2

    zh_roots, en_roots, src_name = resolve_roots(cfg, args.source, args.zh_root, args.en_root)
    idx = build_index(zh_roots, en_roots)
    disc_for_batch = disc if disc.get("enabled", True) and not args.no_rules else {"rules": []}

    if args.batch:
        path = Path(args.batch)
        terms = [
            ln.strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        return run_batch(idx, terms, args.json, disc=disc_for_batch, context=args.context)

    query = args.query.strip()
    q_rules = (
        []
        if args.no_rules or not disc.get("enabled", True)
        else active_rules(disc, query, args.context)
    )
    hits, notes = lookup(idx, query, limit=args.limit, rules=q_rules)

    if args.en_only:
        hits = [h for h in hits if h.entry.en]
    if args.zh_only:
        hits = [h for h in hits if h.entry.zh]

    if args.json:
        payload = [
            {
                "tagKey": h.entry.key,
                "english": h.entry.en,
                "chinese": h.entry.zh_clean,
                "type": h.entry.tag_type,
                "match": h.tier,
                "score": h.score,
                "why": h.why,
            }
            for h in hits
        ]
        print(
            json.dumps(
                {"query": query, "source": src_name, "rules": notes, "hits": payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if hits else 1

    print(format_hits(query, hits, src_name, idx, args.explain, notes=notes))
    return 0 if hits else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
