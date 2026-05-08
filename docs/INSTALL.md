# 安装指南

## 先决条件

- macOS 13.0+（UsageBoard 要求）
- `python3`（系统自带或 Homebrew 均可）
- 已安装并能运行 [UsageBoard](https://github.com/marsmay/UsageBoard)（社区版需自行构建）

## 步骤

### 1. 准备 UsageBoard

如果你**直接用上游 release**：跳到第 2 步。

如果你**自己用 Swift toolchain 构建**：

```bash
git clone https://github.com/marsmay/UsageBoard.git
cd UsageBoard
git apply /path/to/TokenUsed/patches/usageboard-build-and-refresh.patch
bash scripts/build.sh
```

补丁内容：
- `Package.swift`：把 `swift-tools-version: 6.3` 降到 `6.2`（兼容 Swift 6.2.x toolchain）
- `Sources/UsageBoardApp/DashboardView.swift`：在 `.onAppear` 里加 `store.refreshAll()`，每次打开面板自动刷新

### 2. 复制插件

```bash
mkdir -p "$HOME/Library/Application Support/UsageBoard/plugins"
cp plugins/*.py "$HOME/Library/Application Support/UsageBoard/plugins/"
chmod +x "$HOME/Library/Application Support/UsageBoard/plugins/"*.py
```

### 3. 注册插件（两种方式）

**方式 A：直接套用样例配置（最快）**

> ⚠️ 会覆盖你现有的 UsageBoard 配置，先备份。

```bash
cp "$HOME/Library/Application Support/UsageBoard/config.json" "$HOME/Library/Application Support/UsageBoard/config.json.bak"
cp examples/config.example.json "$HOME/Library/Application Support/UsageBoard/config.json"
```

然后重启 UsageBoard：

```bash
pkill -f "UsageBoard.app"
open /path/to/UsageBoard.app
```

**方式 B：在 UsageBoard 设置面板里手动加**

1. 点菜单栏 UsageBoard 图标 → 齿轮图标进设置
2. 「插件」标签页 → 「添加插件」
3. 文件选择器默认就在 `~/Library/Application Support/UsageBoard/plugins/`
4. 依次选 4 个 `.py` 文件加入
5. 启用每个插件（参数可保持默认）

### 4. 验证

打开菜单栏面板应能看到 4 张卡片：

| 卡片 | 期望显示 |
| --- | --- |
| 今日总览 | 上方 hero 条 `今日合计 ▸ XXXMtokens`，下方按模型分条 |
| Claude Code | `7 天: XXXM tokens`，下方 7 天折线图 |
| Gemini CLI | 同上结构（最近用过 Gemini CLI 才有数据） |
| Codex (本地) | 同上结构 |

如果某条显示「JSON 解析失败」，跑一下：

```bash
python3 "$HOME/Library/Application Support/UsageBoard/plugins/daily-overview-plugin.py" \
  --usageboard-param USAGEBOARD_LANGUAGE=zh-Hans
```

正常应输出符合 schema 的 JSON。

## 自定义参数

在 UsageBoard 设置面板里点插件的「设置」可以改：

- **数据目录**：默认值已自适应（`~/.claude/projects` / `~/.gemini/tmp` / `~/.codex`）
- **统计周期**：`7d` 或 `30d`（决定图表显示天数 + 单 CLI 插件的对比基准）

## 卸载

```bash
rm "$HOME/Library/Application Support/UsageBoard/plugins/"{daily-overview,claude-code-usage,gemini-cli-usage,codex-local-usage}-plugin.py
mv "$HOME/Library/Application Support/UsageBoard/config.json.bak" "$HOME/Library/Application Support/UsageBoard/config.json"
pkill -f "UsageBoard.app" && open /path/to/UsageBoard.app
```
