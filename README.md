# grimdawn-translator

《恐怖黎明》（Grim Dawn）汉化术语翻译技能。将补丁说明、论坛公告、装备/技能等英文内容，译成 **Text_EN ↔ Text_ZH** 反查得到的正式汉化用语。

可作为 MiMo Desktop / MiMoCode 技能安装，也可在任意电脑上用脚本直接查词。

## 功能

- **EN → tag → ZH** 反查：在 `Text_EN` 找 `tagKey`，再到 `Text_ZH` 取中文
- 可配置多套术语源（本仓库 `data/`，或本机汉化工程）
- 输出译文 + 术语表，便于审校

## 目录结构

```
grimdawn-translator/
├─ AGENTS.md                              # Codex / DeepSeek / 通用 agent 入口
├─ .mimocode/skills/grimdawn-translator/   # 技能本体
│  ├─ SKILL.md
│  ├─ config.json
│  ├─ scripts/lookup_term.py
│  ├─ references/
│  └─ locales/
├─ data/
│  ├─ Text_EN/    # 英文 tag（base + gdx1/2/3）
│  └─ Text_ZH/    # 中文汉化 tag（含 aom/fg/foa）
└─ README.md
```

## 在其他电脑 / 其它 Agent 中使用

### Codex / DeepSeek / Claude Code 等

本仓库根目录有 **`AGENTS.md`**，主流编码 agent 会自动读取其中约定。若不会自动读，在对话里说：

> 请阅读本仓库的 AGENTS.md 与 .mimocode/skills/grimdawn-translator/SKILL.md，按其中流程翻译：……

查词用标准 Python 脚本（无需 MiMo）：

```bash
python .mimocode/skills/grimdawn-translator/scripts/lookup_term.py "Blade Arc"
```

| 环境 | 做法 |
|------|------|
| **OpenAI Codex** | 克隆仓库后打开；`AGENTS.md` 为入口；技能也可放到用户级 `~/.codex/skills/`（若你的 Codex 版本支持） |
| **DeepSeek（网页/API/IDE）** | 把 `AGENTS.md` + `SKILL.md` 贴进系统提示，或让其「读取这两个文件后再翻译」；用工具/终端跑 `lookup_term.py` |
| **Claude Code** | 同 Codex；或把技能目录拷到 `~/.claude/skills/grimdawn-translator/` |
| **MiMo Desktop** | 保留 `.mimocode/skills/grimdawn-translator/`，作为项目技能自动发现 |

### 方式 A：作为 MiMo 项目技能

1. 克隆本仓库到任意工程：

```bash
git clone https://github.com/<you>/grimdawn-translator.git
# 将 .mimocode/skills/grimdawn-translator 与 data/ 拷入你的工程
# 或直接把本仓库根目录当作工程打开
```

2. 打开 MiMo Desktop → 添加该项目 → 新会话中触发「翻译恐怖黎明 / grimdawn-translator」。

### 方式 B：命令行查词

```bash
python .mimocode/skills/grimdawn-translator/scripts/lookup_term.py "Blade Arc"
python .mimocode/skills/grimdawn-translator/scripts/lookup_term.py "狼人"
python .mimocode/skills/grimdawn-translator/scripts/lookup_term.py --list-sources
```

`config.json` 中 `local` 默认使用仓库内 `data/`（相对技能目录为 `../../../data/...`）。若术语库在别处，把 `external` 改成你的绝对路径，或：

```bash
python lookup_term.py "Resilience" --zh-root /path/to/Text_ZH --en-root /path/to/Text_EN
```

## 配置（config.json）

| 字段 | 说明 |
|------|------|
| `active` | 当前源名称（`local` / `external`） |
| `zh` / `en` | Text_ZH、Text_EN 根目录（相对技能目录或绝对路径） |
| `zh_subdirs` / `en_subdirs` | 本体与资料片子目录 |

## 翻译约定

1. 专有名必须反查后使用，禁止自造译名。
2. 查不到标〔待定〕或把英文交给用户。
3. 保留版本号、数值与格式符（`{%s0}`、`{^g}` 等）。
4. 同一英文全文只用一种中文。

## 依赖

- Python 3.9+（仅标准库）
- 可选：ripgrep，便于手工核对

## 数据说明

`data/Text_EN`、`data/Text_ZH` 来自 Grim Dawn 文本资源，仅供汉化对照与学习交流；游戏版权归 Crate Entertainment 所有。
