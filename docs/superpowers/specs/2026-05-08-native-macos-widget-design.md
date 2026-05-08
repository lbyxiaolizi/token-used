# 原生 macOS 桌面 Widget 设计

**日期**: 2026-05-08
**状态**: 设计待审

## 目标

为 TokenUsed 仓库新增一个原生 macOS 桌面小组件，常驻桌面展示**今日 token 总用量**和**各模型/各类的使用占比**。三种系统尺寸（Small / Medium / Large）全部支持。

数据来源是已经在跑的 UsageBoard 状态缓存 `~/Library/Application Support/UsageBoard/states/daily-overview.json`，由 `plugins/daily-overview-plugin.py` 写入，已聚合 Claude Code / Gemini CLI / Codex CLI 三家。

## 关键决策（已确认）

| 决策 | 选定 | 理由 |
|---|---|---|
| 数据来源 | 读 UsageBoard 缓存 JSON | WidgetKit extension 沙箱禁止 spawn 子进程，不能调 Python；零数据逻辑、最快上线 |
| 支持尺寸 | Small + Medium + Large | 全家族支持，覆盖桌面/通知中心多场景 |
| 容器 app 形态 | 极简占位 + "重载时间线" 按钮 | WidgetKit 强制要求 host app；不需要镜像内容也不需要设置面板 |
| Large 内容 | Medium 全量 + 7 天堆叠柱状图 | `chart.buckets` 字段已就绪，Swift Charts 渲染成本低 |
| 项目结构 | TokenUsed/widget/ 子目录，标准 Xcode 项目，`.xcodeproj` 进 git | 符合现 README 路线图，单仓库单人维护 |

## 架构

```
TokenUsed/widget/
├── TokenUsedWidget.xcodeproj/
├── App/                                  极简 host app
│   ├── TokenUsedApp.swift                @main
│   └── ContentView.swift                 说明 + reloadAllTimelines() 按钮
├── Widget/                               WidgetKit extension
│   ├── TokenUsedWidget.swift             @main，supportedFamilies = small/medium/large
│   ├── Provider.swift                    TimelineProvider，5 分钟一帧
│   ├── Models/
│   │   └── DailyOverview.swift           Codable
│   └── Views/
│       ├── SmallView.swift
│       ├── MediumView.swift
│       └── LargeView.swift
└── Shared/
    └── StateLoader.swift                 路径定位 + 解码 + 错误归一化
```

进程关系：
- UsageBoard 后台运行 → 按其 `refreshIntervalSeconds` 重写 `daily-overview.json`
- Widget Provider 每 5 分钟读该文件 → WidgetKit 渲染
- Host app 运行时不参与数据流，仅作为 widget 分发载体

约束兑现：
- 不 spawn 子进程：仅文件 I/O
- 文件可达性：`~/Library/Application Support/UsageBoard/states/daily-overview.json` 在 user-domain Application Support 下，widget extension 默认有读权限，无需 entitlement
- 无需 App Group：数据生产者是 UsageBoard 而非 host app

## 组件

| 组件 | 职责 | 关键 API |
|---|---|---|
| `TokenUsedApp` | host app `@main`，承载 `ContentView` | SwiftUI `App` |
| `ContentView` | 中文说明 + "重载小组件"按钮 | `WidgetCenter.shared.reloadAllTimelines()` |
| `StateLoader` | 拼路径 / 读文件 / 解码 / 错误归一化 | `FileManager.url(for:.applicationSupportDirectory)` + `JSONDecoder` |
| `DailyOverview` | Codable，字段：`updatedAt: Date`、`badge: String?`、`items: [Item]`、`chart: Chart` | `dateDecodingStrategy = .iso8601` |
| `Item` | `id`、`name`、`used: Double`、`limit: Double`、`color: ColorTag`、`displayStyle` | hero 用 `id == "overview-today-total"` 区分 |
| `Chart.Bucket` | `id`、`label`、`segments: [{model, tokens}]` | 喂给 Swift Charts 的 `BarMark` |
| `Provider` | `TimelineProvider`，`placeholder` / `snapshot` / `timeline` | `Timeline(entries:, policy:.after(now+5min))` |
| `SmallView` | `badge` 大字 + 第一条非 hero item 名称 | `ContainerRelativeShape` 圆角背景 |
| `MediumView` | hero 大字 + 全部 item 占比条（自绘 `Capsule`） | 颜色映射 red/orange/blue → `Color` |
| `LargeView` | `MediumView` + 7 天 `BarMark` 堆叠柱状图 | `import Charts`，`foregroundStyle(by: model)` |

## 数据流

```
UsageBoard ──写─▶ daily-overview.json
                       │
              Provider.timeline() 每 5 min
                       │
             StateLoader.load() ─▶ DailyOverview
                       │
                ┌──────┴──────┐
                ▼             ▼
            entry.now      entry.next (now+5min)
                       │
              WidgetKit 调度 → Small / Medium / LargeView
                       │
              用户点 Widget → 默认打开 host app
```

刷新策略：
- 每 5 分钟一帧（macOS widget 实际调度可能更慢，5 分钟是上限请求）
- Host app `ContentView` 的"重载小组件"按钮调 `reloadAllTimelines()`，用于调试和兜底
- 不做主动文件监听（FSEvents 在 widget extension 里不可靠）

## 错误处理

`StateLoader` 把所有异常归一化为 `LoadError`：

| 错误 | 来源 | UI 表现 |
|---|---|---|
| `.fileMissing` | `daily-overview.json` 不存在 | "未检测到 UsageBoard 数据，请先安装并启动" |
| `.decode(Error)` | JSON 字段缺失或类型不符 | "数据格式异常"，若 `updatedAt` 可用则附带显示 |
| `.stale(Date)` | `updatedAt` 距今 > 1 小时 | 正常显示，顶部加灰色徽标 "已过期 Xh" |
| `.empty` | `items` 为空数组 | "今日暂无用量" |

Provider 永远返回有效 `Timeline`（出错时返回一个 placeholder entry），绝不让 WidgetKit 白屏。

## 测试

- **单元测试** `StateLoaderTests`：用 fixture JSON 跑解码，覆盖四种场景：
  - 完整数据（直接复制当前 `daily-overview.json`）
  - 空 `items`
  - 字段缺失
  - 损坏 JSON
- **快照测试**（可选）：`swift-snapshot-testing` 给三个尺寸留基线 PNG
- **手测清单**：
  1. Xcode 跑 widget scheme
  2. Widget Simulator 添加 small / medium / large
  3. 手动改 `daily-overview.json` 后点"重载"，确认拿到新数据
  4. 重命名/删除 `daily-overview.json`，确认错误态文案正确
- **不测**：UsageBoard 自身的写入逻辑（不在本项目范围内）

## 非目标

- 不做 ChatGPT 配额 / API 配额查询（保持 TokenUsed 的"纯本地"定位）
- 不做主动通知或告警
- 不做用户配置面板（路径、刷新频率、模型别名都用合理默认值，需要时再迭代）
- 不内嵌进 UsageBoard 主项目（参见 docs/WIDGET.md 方案 C 已被排除的原因）

## 后续工作

实现完成后回填到 README.md 路线图，更新 `docs/WIDGET.md` 把"方案 B 原生 WidgetKit"标记为已实现，并补一条用户安装指南（Xcode 构建 → 拖 app 到 /Applications → 桌面右键添加 widget）。
