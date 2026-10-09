# AGENTS.md — grimdawn-translator

本仓库是《恐怖黎明》汉化术语对照库 + 翻译工作流，供 **任意编码/对话 agent**（Codex、DeepSeek、Claude Code、MiMo 等）使用。

## 你要做的事

用户要求翻译 Grim Dawn / 恐怖黎明 相关英文（补丁、公告、装备、技能、属性）时：

1. 先读 `.mimocode/skills/grimdawn-translator/SKILL.md`（完整流程）。
2. **专有名必须反查**，禁止自造译名。
3. 反查命令（仓库根目录下执行）：

```bash
python .mimocode/skills/grimdawn-translator/scripts/lookup_term.py "Blade Arc"
python .mimocode/skills/grimdawn-translator/scripts/lookup_term.py "狼人"
python .mimocode/skills/grimdawn-translator/scripts/lookup_term.py --list-sources
```

原理：在 `data/Text_EN` 找英文 `tagKey`，再到 `data/Text_ZH` 用同一 key 取汉化。

4. 输出：译文 + 术语表(English | 中文 | tagKey)；查不到标〔待定〕。
5. 保留版本号、数值、格式符；同一英文全文只用一种中文。

## 路径

| 内容 | 路径 |
|------|------|
| 技能说明 | `.mimocode/skills/grimdawn-translator/SKILL.md` |
| 查词脚本 | `.mimocode/skills/grimdawn-translator/scripts/lookup_term.py` |
| 配置 | `.mimocode/skills/grimdawn-translator/config.json` |
| 英文术语库 | `data/Text_EN/` |
| 中文术语库 | `data/Text_ZH/` |

术语库路径在 `config.json` 的 `local` 源中为相对路径，可整包拷贝到任意机器。

## 不要做的事

- 不要凭英文结构直译技能/装备名。
- 不要修改 `data/` 下的 tag 源文件（只读对照）。
- 其它游戏的翻译不要套用本流程。
