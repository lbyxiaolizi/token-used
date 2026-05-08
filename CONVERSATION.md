# 会话记录

记录从「问 Bob 翻译社区版」一路演变成「为 UsageBoard 写一套 token 用量插件」的完整过程。日期：**2026-05-08**。

---

## 1. 起因：Bob 翻译

**Q**：「看一下这个翻译的社区版不能用了吗？」

查仓库（`~/opc/codex/Bob`）：

- README 第 9-10 行写明：「Bob 不是开源软件，本仓库曾经用于提供反馈渠道」
- `appcast.xml` 最后一条 `0.10.3` 发布于 2022-07-09，更新说明「Bob 已发布到 Mac App Store」
- 自 v1.0 起仅在 Mac App Store 分发，旧 Gitee 下载链接停止维护

**结论**：社区版**已停更**，需要去 App Store 装 v1.x。

---

## 2. 找替代品：「macOS 翻译 + OCR 有没有类似的开源项目？」

推荐：

- **Easydict**（最接近 Bob 的开源替代品）
- **Pot**（跨平台 + 插件丰富）
- **OpenAI Translator**
- **Raycast 扩展**
- **Selected**（Easydict 同作者）

---

## 3. 转向 UsageBoard：「本地帮我安装并启动 https://github.com/marsmay/UsageBoard」

### 环境检查

- Swift 6.2.4（项目要求 6.3）
- Xcode 26 已装，macOS 26.4.1，python3 在 Homebrew

### 构建踩坑

- 直接 `bash scripts/build.sh` 报 `Swift tools version 6.3.0 but installed 6.2.4`
- 检查 `Package.swift`，发现实际没用到 6.3 特性，把 `// swift-tools-version: 6.3` 改成 `6.2`，构建通过
- 应用启动到菜单栏，PID 73911

**位置**：`~/opc/codex/UsageBoard`，app bundle 在 `dist/UsageBoard.app`。

---

## 4. 加插件：「这个插件我要怎么加？」

回答：

- 内置 5 个插件（智谱 / MiniMax / DeepSeek / Tavily / Codex）已自动 symlink 到用户目录，但**默认未启用**
- 第三方/自定义插件只要把 `.py` 放进 `~/Library/Application Support/UsageBoard/plugins/`，再在设置面板里点「添加插件」

---

## 5. 真正的需求：「帮我加上 codex 和 gemini 和 claude 的」

### 探查数据结构

- `~/.codex/auth.json` 只有 `OPENAI_API_KEY`（不是 ChatGPT 订阅 token），**内置 Codex 插件不适用**
- Claude Code 的 `~/.claude/projects/**/*.jsonl` 里 `"type":"assistant"` 行带 `message.usage.{input,output,cache_*}_tokens` + `message.model`
- Gemini CLI 的 `~/.gemini/tmp/**/session-*.json` 有 `messages[].tokens.total` + `messages[].model`

### 写了 3 个自定义插件

1. `claude-code-usage-plugin.py` — 7 天/30 天 token 总量 + 折线图
2. `gemini-cli-usage-plugin.py` — 同上
3. `codex-local-usage-plugin.py` — 同上（替代内置 Codex 插件）

文件丢到 `~/Library/Application Support/UsageBoard/plugins/`。本地命令行测试 JSON 输出符合预期。

---

## 6. 「为什么显示还是暂无插件」

发现 `config.json` 的 `plugins: []` 是空的——**UsageBoard 不会自动扫插件目录**，必须显式注册。

---

## 7. 「你能帮我操作吗」

### 直接改 config.json

读 Swift 源码弄清 schema：

- `PluginConfiguration` 必填字段：`stateID`（字符串）、`name`、`enabled`、`executablePath`、`refreshIntervalSeconds`、`parameterValues`
- `metadata` 是可选的，应用启动时 `UsageBoardStore.init` 会调 `reloadAllMetadata()` 重新解析脚本头部

→ 写最小 config.json，停掉 app，覆盖文件，重启。app 自动补全 metadata（图标、中英文名、参数表单）。

成功注册 3 个插件，状态：`enabled=True, has_metadata=True`。

---

## 8. 「3 个都报错：JSON 解析失败」

### 排查

读 `Models.swift::UsageItem`：

- `used: Double`（非 nil 非 String）
- `limit: Double`
- `displayStyle: UsageDisplayStyle` 枚举只有 `.percent` / `.ratio`

我之前的输出：

- `"used": "789.84M"` ❌ 字符串
- `"limit": null` ❌ null
- `"displayStyle": "number"` ❌ 不存在的枚举值

### 修

把 `used/limit` 改成 Double，`displayStyle` 改成 `percent`，把格式化字符串塞进 `name` 字段。重启后所有插件正常输出。

---

## 9. 「这个没有总览吗？」

### 发现 DisplayMode

`Models.swift::DisplayMode` 有两个 case：`grouped` / `tabs`。当前 `tabs` 是单插件 tab 切换，`grouped` 是全部插件同屏。

→ 把 `config.json` 的 `overviewDisplayMode` 改成 `"grouped"`，重启。

---

## 10. 「为什么后面的进度条都是 0%？」

### 改成有意义的进度条

之前为了快速过 schema 把 `used=0, limit=100` 设成空进度条。改成「**今天 vs 期内峰值日**」：

```python
ratio = today_total / peak_total
status = "critical" if ratio >= 1.0 else "warning" if ratio >= 0.8 else "normal"
color  = "red"      if ratio >= 1.0 else "orange"  if ratio >= 0.8 else "blue"
items = [{
    "id": ..., "name": f"{period}: {fmt_tokens(total)} tokens",
    "used": today_m, "limit": max(peak_m, 0.01),
    "displayStyle": "ratio", "status": status, "color": color,
}]
```

进度条满 = 今天破峰；橙色 = 接近峰值；蓝色 = 一般日。

---

## 11. 「我要的总览是统计所有模型当天的 token 使用」

### 写第 4 个插件：`daily-overview-plugin.py`

- 并行扫三家本地数据
- `by_model_today` 聚合今日按模型
- `by_bucket` 跨源 7 天/30 天图表
- 每个模型一条 item，`limit = 今日总量`，`displayStyle = percent` → 进度条 = 该模型占今日份额
- `badge` 显示今日合计（如 `392.87M`）

### 注册

停 app，编辑 `config.json` 在 `plugins[]` 数组**头部**插入新条目，重启。app 解析 metadata 后正确显示。

实测：今天合计 392.87M tokens（claude-opus-4-7 76% / gpt-5.5 24%）。

---

## 12. 「总览显示今天用的 tokens 能不能大一点，然后每次打开自动刷新一次」

### 改动 1：大字号

总览插件 `items[0]` 改成 hero 条目：

```python
items.append({
    "id": "overview-today-total",
    "name": f"今日合计  ▸  {fmt_tokens(today_total)} tokens",
    "used": total_m, "limit": max(total_m, 0.01),
    "displayStyle": "ratio", "color": "blue",
})
```

总数同时出现在：item 标题（最大字号）、右侧 ratio 数值、badge（标题旁小标签）。

### 改动 2：打开自动刷新

读 `DashboardView.swift::onAppear`，发现只调 `ensureSelectedTab()`，**没**调 `store.refreshAll()`。

改：

```swift
.onAppear {
    ensureSelectedTab()
    store.refreshAll()   // ← 加这行
}
```

`bash scripts/build.sh` 重新构建启动。每次点菜单栏图标都会立即刷新。

---

## 13. 「这个进度条显示红蓝黄是什么意思」

解释配色（详见 `docs/COLORS.md`）：

- 总览 → 模型占今日份额
- 单 CLI → 今天 vs 峰值日
- 黄色 = UsageBoard 内置 `status: warning` 的渲染色，单 CLI 接近峰值（80-99%）时触发

---

## 14. 「能做一个 mac 的桌面小组件吗？需不需要 fork？」

回答（详见 `docs/WIDGET.md`）：

| 方案 | Fork? | 工时 |
| --- | --- | --- |
| A. Übersicht | 否 | ~15 分钟 |
| B. 独立 WidgetKit | 否 | 半天 |
| C. UsageBoard 加 widget extension | **是** | 1-2 天 |

关键约束：WidgetKit 不能 spawn 子进程，必须读 UsageBoard 已写好的 `states/<stateID>.json` 缓存。

推荐先试 A 验证设计，再决定要不要做 B。

---

## 15. 「整理到 TokenUsed 仓库」

→ 当前文档。

## 最终成果清单

### 代码

- `plugins/daily-overview-plugin.py`（核心，今日跨源总览）
- `plugins/claude-code-usage-plugin.py`
- `plugins/gemini-cli-usage-plugin.py`
- `plugins/codex-local-usage-plugin.py`

### UsageBoard 改动

- `Package.swift`：`tools-version: 6.3 → 6.2`
- `DashboardView.swift::onAppear`：加 `store.refreshAll()`

### 配置

- `examples/config.example.json`：4 个插件 + `grouped` 模式

### 文档

- `README.md`、`docs/INSTALL.md`、`docs/COLORS.md`、`docs/WIDGET.md`、`CONVERSATION.md`

### 验证数据（今天的实际测试结果）

| 范围 | tokens |
| --- | --- |
| Claude Code 7 天 | ~800M |
| Codex 本地 7 天 | ~500M |
| Gemini 7 天 | 0（最近 30 天没用过 Gemini CLI） |
| **今日合计** | **412.62M**（claude-opus-4-7 76% + gpt-5.5 24%） |
