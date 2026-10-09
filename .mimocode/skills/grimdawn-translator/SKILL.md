---
name: grimdawn-translator
description: Translate Grim Dawn (恐怖黎明) content into this project's official Chinese localization terms for items, skills, stats, factions, places, and UI. Use when the user asks to translate Grim Dawn / GD / 恐怖黎明 patch notes, forum posts, item or skill text, or mentions grimdawn-translator / 汉化术语 / 官中译名. Do NOT use for other games or generic EN-ZH translation. Do NOT use for editing Text_ZH source files.
---

# grimdawn-translator

将《恐怖黎明》（Grim Dawn）英文内容译成**本工程正式汉化**用语。专有名词必须来自 Text_EN ↔ Text_ZH 对照，禁止自造译名。

## 原则

1. **术语以工程汉化为准**：装备、技能、属性、专精、地名、势力、UI 词一律反查后使用。
2. **反查路径**：英文 → 在 Text_EN 找 `tagKey` → 在 Text_ZH 用同一 `tagKey` 取中文。
3. 查不到则标〔待定〕或把英文交给用户，**不要音译硬猜**。
4. 译文面向玩家：通顺、简短；保留版本号、数值、格式符（`{%s0}`、`{^g}` 等）。
5. 定名优先级：`lookup_term.py` 命中结果 > 用户当前指示 > 〔待定〕。

## 术语源（可配置）

配置文件：`config.json`（本技能目录下）。

| 字段 | 含义 |
|------|------|
| `active` | 当前源名称 |
| `zh` / `en` | Text_ZH / Text_EN 根目录 |
| `zh_subdirs` / `en_subdirs` | 子目录（本体与资料片） |

默认 `active=local`，指向本工程：

- EN：`out/Text_EN/`（`en/text_en`, `en_gdx1|2|3/text_en`）
- ZH：`out/set_no_desc/Text_ZH/`（含 `aom/fg/foa`）

```powershell
# 列出源
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" --list-sources

# 查词（EN 或中文片段）——取排名第 1 的命中
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "Blade Arc"
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "狼人"

# 调试排序 / 机器可读
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "Armor" --explain
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "Onslaught" --json --limit 5

# 批量（补丁抽词后一次查完）
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" --batch terms.txt --json

# 指定源 / 临时目录
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "Onslaught" --source local
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "Resilience" --zh-root D:/path/Text_ZH --en-root D:/path/Text_EN

# 黄金回归（改检索逻辑后必须跑）
& $env:MIMO_PYTHON ".../scripts/test_lookup_golden.py"
```

用户指定其它本地/远程汉化工程时：改 `config.json` 里对应 `zh`/`en` 路径，或用 `--zh-root` / `--en-root`。

## 工作流

### 1. 抽词

列出待译文本中的专有名：技能、装备、属性、伤害/抗性、专精、地名、NPC、系统名。

### 2. 反查

对每个词跑 `lookup_term.py`，记录 `tagKey` 与正式中文（去掉 `^g<^F士兵^g>^c` 等颜色控制符）。

**匹配优先级（脚本已内置，按此选 Top1）：**

| 层级 | 含义 | 例 |
|------|------|----|
| EXACT | EN/ZH 整句相等 | `Blade Arc` → 刀锋横扫 |
| KEY | tagKey 相等 | `tagClass01SkillName05A` |
| STRIP | 剥掉 Mythical/Awakened/…/Set 再精确 | `Mythical Will of Bysmiel` |
| PHRASE | 整词短语（非裸子串） | `Armor Rating` |
| PREFIX / WORDS | 前缀或整词集合 | 辅助 |

硬约束：

1. **禁止裸子串**：`All Resist` 不得命中 `tagChatAll`；短查询（`L`/`A`）只走 EXACT。
2. **说明文不抢名**：Desc/Lore/Patch 在非 EXACT 层不参与；`All damage` 不得顶掉专有名。
3. **同值多 tag 多数投票**：`Armor` 多数为「护甲」→ 优先，而非唯一衣甲「护身甲」。
4. **类型加权**：技能名 / 套装名 > 装备 > 属性/UI > 说明文。
5. 输出无命中或 Top1 为 `other`/低分时，标〔待定〕或换完整名再查，**不要用第 2、3 名的残句硬译**。

### 3. 成稿

1. 先固定「英文 → 中文」表，再写译文。
2. 技能/装备首次可写「中文（English）」，后文只用中文。
3. 机制句式对齐游戏内说明（如「+15% 火焰伤害」）。

### 4. 自检

- [ ] 专有名均可在 Text_ZH 命中（或已标〔待定〕）
- [ ] 同一英文全文一种中文
- [ ] 数值与格式符完整
- [ ] 无漏段

## 歧义消解表（人工修正）

路径：本技能目录 `disambiguation.json`。**可直接编辑**，查词时自动套用，无需改代码。

```powershell
# 查看当前规则
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" --list-rules

# 调试时忽略规则
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "Armor" --no-rules

# 上下文限定规则（规则里填了 context 时才匹配）
& $env:MIMO_PYTHON ".../scripts/lookup_term.py" "Ascension" --context "技能"
```

| 字段 | 含义 |
|------|------|
| `query` + `match` | `exact` / `prefix` / `contains` / `regex` / `any` |
| `prefer_tags` / `prefer_zh` | 优先（加分；`force_top` 可置顶） |
| `forbid_tags` / `forbid_zh` | 禁止（tag **硬排除**；zh 重罚） |
| `emit_zh` | 库中无合适命中时给出〔规则〕译名 |
| `context` | 仅 `--context` 含该词时套用 |
| `enabled` | `false` 关闭本条 |

复制模板条 `template-copy-me`，改字段后 `enabled: true`。改完跑：

```powershell
& $env:MIMO_PYTHON ".../scripts/test_lookup_golden.py"
```

## 输出

默认直接给译文。需要审校时附：

```markdown
## 译文
...

## 术语表
| English | 中文 | tagKey |

## 〔待定〕
- ...
```

## 示例

**触发**：「翻译这段补丁说明，用汉化术语」  
**动作**：抽词 → lookup → 术语表 → 译文 → 自检  

**触发**：「Resilience 游戏里怎么翻？」  
**动作**：lookup `Resilience` → 返回中文与 tag  

## 故障

| 情况 | 处理 |
|------|------|
| EN/ZH 都无命中 | 标〔待定〕或交用户英文，勿编造 |
| 只在资料片有 | 确认 `en_subdirs` / `zh_subdirs` 含 gdx 对应目录 |
| `MIMO_PYTHON` 不可用 | 改用 `python` |
| 要改 Text_ZH 源文件 | 不属本技能 |

## 参考

- 路径与检索说明：`references/lookup-guide.md`
