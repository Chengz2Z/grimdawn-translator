# EN ↔ ZH 反查

## 路径

| 侧 | 默认根目录 | 子目录 |
|----|------------|--------|
| EN | `out/Text_EN/` | `en/text_en`, `en_gdx1/text_en`, `en_gdx2/text_en`, `en_gdx3/text_en` |
| ZH | `out/set_no_desc/Text_ZH/` | `""`, `aom`, `fg`, `foa` |

行格式：`tagKey=value`。颜色控制符如 `^g<^F士兵^g>^c` 写入译文前去掉。

## 步骤

1. `lookup_term.py "<English>"` → 取 **Match=EXACT/STRIP 的第 1 行** 的 `tagKey` 与 ZH。
2. 若 EN 有而 ZH 无：用 `tagKey` 在 ZH 侧再搜一次，或检查 `zh_subdirs`。
3. 若只有中文：搜中文片段，记下 `tagKey`，再对照 EN（支持 CJK 子串，如「狼人」→「狼人形态」）。
4. 批量：`--batch terms.txt`；排查排序：`--explain` / `--json`。
5. 改检索后跑 `scripts/test_lookup_golden.py`（黄金回归，须全绿）。

匹配层级：EXACT > KEY > STRIP（Mythical/…/Set）> PHRASE（整词短语）> PREFIX/WORDS。
**不用裸子串**；说明文（Desc/Lore）不参与非精确匹配。

## 手工 Grep

```powershell
& $env:MIMO_RIPGREP_PATH -n "Blade Arc" "D:\PROJECTS\gdhanhua\out\Text_EN"
& $env:MIMO_RIPGREP_PATH -n "tagClass01SkillName05A=" "D:\PROJECTS\gdhanhua\out\set_no_desc\Text_ZH"
```

## 配置

改 `config.json` 的 `sources.<name>.zh` / `.en`，或运行时 `--zh-root` / `--en-root`。
