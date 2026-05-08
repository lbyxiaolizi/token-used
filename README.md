# TokenUsed

为 [UsageBoard](https://github.com/marsmay/UsageBoard) 打造的一组本地 token 用量插件，把 **Claude Code / Gemini CLI / Codex CLI** 三家命令行工具的本地会话数据聚合到 macOS 菜单栏。

不依赖任何远程配额 API（不需要 ChatGPT 订阅 token），完全离线读取本地 JSONL/JSON 会话文件统计 token 用量。

## 仓库内容

```
TokenUsed/
├── plugins/                                # UsageBoard Python 插件
│   ├── daily-overview-plugin.py            # ⭐ 今日总览（跨三家聚合，按模型分条 + 7 天柱状图）
│   ├── claude-code-usage-plugin.py         # Claude Code 单独面板
│   ├── gemini-cli-usage-plugin.py          # Gemini CLI 单独面板
│   └── codex-local-usage-plugin.py         # Codex CLI 单独面板（OPENAI_API_KEY 模式）
├── patches/
│   └── usageboard-build-and-refresh.patch  # UsageBoard 上游需要的两处改动
├── examples/
│   └── config.example.json                 # 完整 config.json 样例（4 个插件已注册）
├── docs/
│   ├── INSTALL.md                          # 安装步骤
│   ├── COLORS.md                           # 进度条配色规则
│   └── WIDGET.md                           # 桌面小组件方案对比
└── CONVERSATION.md                         # 完整会话记录（中文）
```

## 数据来源

| 插件 | 读取位置 | 字段 |
| --- | --- | --- |
| Claude Code | `~/.claude/projects/**/*.jsonl` | `message.usage.{input,output,cache_*}_tokens` + `message.model` |
| Gemini CLI | `~/.gemini/tmp/**/session-*.json` | `messages[].tokens.total` + `messages[].model` |
| Codex CLI | `~/.codex/sessions/**/*.jsonl` + `archived_sessions/*.jsonl` | `payload.info.total_token_usage.total_tokens`（按 turn_context 取 model） |

总览插件并行读取以上三处。

## 快速安装

详见 [docs/INSTALL.md](docs/INSTALL.md)。简版：

```bash
# 1) 复制插件到 UsageBoard 用户目录
cp plugins/*.py "$HOME/Library/Application Support/UsageBoard/plugins/"

# 2) 应用 UsageBoard 补丁（仅本地构建版需要）
cd /path/to/UsageBoard
git apply /path/to/TokenUsed/patches/usageboard-build-and-refresh.patch
bash scripts/build.sh   # 重新构建并启动

# 3) 用样例配置（或在设置面板里逐个添加）
cp examples/config.example.json "$HOME/Library/Application Support/UsageBoard/config.json"
```

## 设计要点

- **进度条语义**：纯统计场景没有真实配额，所以不同插件的进度条意义不同——总览 = 模型占今日份额；单 CLI = 今天 vs 期内峰值日。详见 [docs/COLORS.md](docs/COLORS.md)。
- **打开自动刷新**：补丁里给 `DashboardView.onAppear` 加了 `store.refreshAll()`，每次点开菜单栏面板都会立即重跑插件。
- **Swift 工具链兼容**：上游 `Package.swift` 写死 `tools-version: 6.3`，但代码本身没用到 6.3 特性。补丁把它降到 `6.2`，解锁本地 Swift 6.2.x 构建。
- **Hero 条目**：今日总览第一条把合计数字放进 `name` 字段（item 标题位字号最大），同时通过 `badge` 和右侧 `ratio` 数值三处冗余展示。

## 路线图

- [ ] 桌面小组件（参见 [docs/WIDGET.md](docs/WIDGET.md)，推荐 Übersicht 路线）
- [ ] 统一三家单 CLI 插件的进度条语义
- [ ] 支持自定义模型分组与别名

## 许可

MIT。插件脚本可自由修改与再分发。
