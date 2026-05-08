# TokenUsed

> 为 [UsageBoard](https://github.com/marsmay/UsageBoard) 打造的本地 token 用量插件集——把 **Claude Code / Gemini CLI / Codex CLI** 三家命令行工具的本地会话聚合到 macOS 菜单栏面板。

简体中文 · [English](./README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE) ![Platform](https://img.shields.io/badge/platform-macOS%2013%2B-lightgrey)

<p align="center">
  <img src="images/menubar-panel.png" alt="UsageBoard 菜单栏面板" width="425"><br>
  <sub>今日总览（hero 合计 + 各模型行 + 右列 token 数）与单 CLI 面板</sub>
</p>

<details>
<summary>📊 点开看 7 天图表展开形态</summary>

<p align="center">
  <img src="images/today-overview-expanded.png" alt="今日总览 7 天堆叠柱状图" width="425">
  <img src="images/cli-panels-expanded.png" alt="单 CLI 面板的 7 天图表" width="425"><br>
  <sub>点 panel 底部的箭头展开按模型堆叠的 7 天柱状图</sub>
</p>

</details>

---

## 特性

- **不依赖任何远程 API**——完全离线读本地 JSONL/JSON 会话文件，**不需要 ChatGPT 订阅 token**。
- **三家 CLI 一个面板**——Claude Code / Gemini CLI / Codex CLI 用量按模型聚合。
- **今日总览 + 7/30 天图表**——hero 大数字显示三家今日合计，下方堆叠柱状图按模型分段。
- **空数据自动隐藏**——某 CLI 从没用过（如 Gemini），它的 panel 自动消失。
- **右侧列直接显示 token 数**——通过 `trailingText` 字段把 UsageBoard 原本"重置时间"那一列改用为按行显示模型 token 数。
- **附带原生 macOS WidgetKit 项目**——`widget/` 下代码完整；上桌面 widget gallery 需要付费 Apple Developer Program（详见[原生 widget 状态](#原生-widget-状态)）。

---

## 依赖

| 组件 | 版本 | 说明 |
|---|---|---|
| macOS | 13.0 + | UsageBoard 自身要求 |
| Python 3 | 3.8 + | 系统自带或 Homebrew 都行 |
| [UsageBoard](https://github.com/marsmay/UsageBoard) | 上游 `main` | 会用本仓库 patch 做本地构建 |
| Swift toolchain | 6.2 + | 仅本地构建 UsageBoard 时需要 |
| Xcode 16 + | 可选 | 仅当你也想构建原生 widget app 时需要 |

数据源至少需要其中**一个** CLI 已经产生过会话：

- Claude Code → `~/.claude/projects/**/*.jsonl`
- Gemini CLI → `~/.gemini/tmp/**/session-*.json`
- Codex CLI → `~/.codex/sessions/**/*.jsonl` 及 `~/.codex/archived_sessions/*.jsonl`

没数据的 CLI 自动隐藏——四个插件全装即可，有什么数据就显示什么。

---

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/uniStark/TokenUsed.git
cd TokenUsed

# 2. 拉 UsageBoard，应用补丁，本地构建（一次性）
git clone https://github.com/marsmay/UsageBoard.git ../UsageBoard
cd ../UsageBoard
git apply ../TokenUsed/patches/usageboard-build-and-refresh.patch
bash scripts/build.sh
cd ../TokenUsed

# 3. 部署插件
mkdir -p "$HOME/Library/Application Support/UsageBoard/plugins"
cp plugins/*.py "$HOME/Library/Application Support/UsageBoard/plugins/"
chmod +x "$HOME/Library/Application Support/UsageBoard/plugins/"*.py

# 4. （可选）套用样例配置——把占位符 __HOME__ 替换为当前 $HOME
sed "s|__HOME__|$HOME|g" examples/config.example.json > "$HOME/Library/Application Support/UsageBoard/config.json"

# 5. 打开 UsageBoard，点菜单栏图标，应该看到 4 张 panel
```

遇到问题见下文 [排错](#排错)。

---

## 补丁修改了什么

`patches/usageboard-build-and-refresh.patch` 给上游 UsageBoard 做了三处小改：

| 文件 | 修改 | 原因 |
|---|---|---|
| `Package.swift` | `swift-tools-version: 6.3` → `6.2` | 让 Swift 6.2 toolchain 能构建 |
| `Sources/UsageBoardApp/DashboardView.swift` | `.onAppear` 加 `store.refreshAll()`，并加 `visiblePlugins` 过滤空 panel | 每次开面板自动刷新；空数据 CLI 自动隐藏 |
| `Sources/UsageBoardCore/Models.swift` | `UsageItem` 加可选 `trailingText: String?` 字段 | 让插件给每行右列填"token 数"等自由文本 |

如果你坚持用未打补丁的 UsageBoard，插件依然能跑——只是失去自动隐藏和右列 token 数。

---

## 配置

四个插件的所有参数都从 UsageBoard 设置面板读取，默认值开箱即用。需要时再覆写。

### 今日总览 (`daily-overview-plugin.py`)

| 参数 | 默认 | 说明 |
|---|---|---|
| `CLAUDE_DIR` | `~/.claude/projects` | Claude Code 会话 JSONL 目录 |
| `GEMINI_DIR` | `~/.gemini/tmp` | Gemini CLI `session-*.json` 目录 |
| `CODEX_DIR` | `~/.codex` | Codex CLI 根目录（扫 `sessions/` + `archived_sessions/`） |
| `CHART_PERIOD` | `7d` | `7d` 或 `30d`——图表时间窗 |

### 单 CLI 插件（`claude-code-usage-plugin.py`、`gemini-cli-usage-plugin.py`、`codex-local-usage-plugin.py`）

| 参数 | 默认 | 说明 |
|---|---|---|
| `*_DIR` | 同上 | 覆盖该 CLI 的扫描路径 |
| `STAT_PERIOD` | `7d` | `7d` 或 `30d`——图表 + "今天 vs 期内峰值"进度条都用这个 |

自定义路径：UsageBoard → 菜单栏图标 → 齿轮 → **插件** → 点插件 → 调参数。无需重启。

### 进度条配色含义

四个插件的进度条**颜色规则不一样**，是设计如此：
- **今日总览**：颜色按"该模型占今日总量的百分比"——红≥50%、橙≥25%、蓝<25%
- **单 CLI**：颜色按"今天用量 ÷ 期内峰值日"——红≥100%（破峰）、橙≥80%、蓝<80%

---

## 仓库结构

```
TokenUsed/
├── plugins/                            # UsageBoard Python 插件
│   ├── daily-overview-plugin.py        # ⭐ 今日总览（三家聚合，按模型分行 + 7 天柱状图）
│   ├── claude-code-usage-plugin.py     # Claude Code 单独面板
│   ├── gemini-cli-usage-plugin.py      # Gemini CLI 单独面板
│   └── codex-local-usage-plugin.py     # Codex CLI 单独面板
├── patches/
│   └── usageboard-build-and-refresh.patch  # 三处 UsageBoard 改动
├── examples/
│   └── config.example.json             # 已注册四个插件的 UsageBoard 完整配置
├── widget/                             # 原生 macOS WidgetKit 应用（Xcode 项目，见状态说明）
├── images/                             # README 截图
├── README.md                           # 英文文档
├── README_ZH.md                        # 中文文档（本文件）
└── LICENSE                             # MIT
```

---

## 原生 Widget 状态

`widget/` 下是一个完整的 WidgetKit + SwiftUI Xcode 项目（Small / Medium / Large 三尺寸，Swift Charts 7 天柱状图）。本地能 build 能跑，但 **macOS 15+ Sequoia / Tahoe** 的系统 daemon `chronod` 拒绝把 Personal Team 签的 widget extension 加进桌面 widget gallery——**需要付费 [Apple Developer Program](https://developer.apple.com/programs/)（$99/年）**才能真正用上。

不打算付费的话，菜单栏的 UsageBoard 面板已经覆盖所有数据。widget 代码已就绪，等签名通路打开即可发布。

---

## 数据来源

| 插件 | 读取位置 | 字段 |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | `message.usage.{input,output,cache_*}_tokens` + `message.model` |
| Gemini CLI | `~/.gemini/tmp/**/session-*.json` | `messages[].tokens.total` + `messages[].model` |
| Codex CLI | `~/.codex/sessions/**/*.jsonl` + `archived_sessions/*.jsonl` | `payload.info.total_token_usage.total_tokens`（按相邻 `turn_context` 取 model） |

总览插件并行读取以上三处。

---

## 排错

**Panel 显示 "JSON 解析失败"**：手动跑插件看原始报错：
```bash
python3 "$HOME/Library/Application Support/UsageBoard/plugins/daily-overview-plugin.py" \
  --usageboard-param USAGEBOARD_LANGUAGE=zh-Hans
```

**构建报 `swift-tools-version 6.3 is not supported`**：你忘了打补丁。`cd UsageBoard && git apply ../TokenUsed/patches/usageboard-build-and-refresh.patch`。

**右列显示 `--`**：你跑的是未打补丁的 UsageBoard。`trailingText` 字段需要补丁。

**Gemini 面板还显示 `0 tokens`**：UsageBoard 没打补丁，或者 Gemini 插件还是改前的版本——`cp plugins/gemini-cli-usage-plugin.py ~/Library/Application\ Support/UsageBoard/plugins/` 然后点菜单栏图标刷新。

---

## 贡献

欢迎 PR。可以折腾的方向：

- 新增 CLI 插件（例如 Aider、Cursor CLI、Cline、OpenRouter）——拷一个现有 `*-usage-plugin.py` 当模板，遵循 `# UsageBoardPlugin: ... # /UsageBoardPlugin` 元数据块即可。
- 调整配色/阈值规则——当前规则在 [配置](#配置) 章节。
- 原生 widget 收尾——一旦 Apple Developer Program 问题解决，`widget/` 已经准备好可分发。
- 除 `zh-Hans` / `en` 之外的本地化。

提交前请跑一次 `python3 plugins/<你的插件>.py --usageboard-param USAGEBOARD_LANGUAGE=en` 确认输出符合现有 schema。

---

## 许可

MIT，见 [LICENSE](./LICENSE)。插件脚本可自由修改与再分发。

## 致谢

- [UsageBoard](https://github.com/marsmay/UsageBoard) —— 本项目挂靠的菜单栏宿主。
- [lobe-icons](https://github.com/lobehub/lobe-icons) —— `examples/config.example.json` 引用的插件图标集。
