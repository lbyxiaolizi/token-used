# 桌面小组件方案

当前菜单栏面板需要点击图标才能查看。如果想让今日总览**常驻桌面**，下面是三条可选路径——按工程量从低到高排列。

## 方案对比

| 方案 | 是否要 fork UsageBoard | 工作量 | 体验 |
| --- | --- | --- | --- |
| **A. Übersicht 桌面小组件**（推荐先试） | 不动 | ~15 分钟，单个 `.coffee` 文件 | 浮在桌面，HTML/CSS 自由排版，直接调 Python 插件 |
| **B. 独立 WidgetKit 应用** | 不动 | 新建 Xcode 项目，~半天 | macOS 原生 widget（小/中/大三尺寸），SwiftUI 渲染，**只读** UsageBoard 状态缓存 |
| **C. 给 UsageBoard 加 Widget 扩展** | 需要 fork | 1-2 天 | 与 UsageBoard 同包发布，但要把 SwiftPM 转 Xcode 项目、加 App Group entitlement、重做签名打包 |

## 关键技术点

### WidgetKit 的硬约束

macOS Widget 是 app extension，运行在严格 sandbox 里：

- **不能 spawn 子进程**：`Foundation.Process` 在 widget extension 里被禁，**不能直接调 Python 脚本**。
- **只能读已写好的文件**：UsageBoard 把每个插件的 `PluginCachedState` 写到 `~/Library/Application Support/UsageBoard/states/<stateID>.json`。Widget 必须从这里读。
- **更新频率受系统调度**：TimelineProvider 推荐间隔 ≥ 5 分钟，紧急刷新走 Background Refresh。

### Übersicht 没有这些约束

[Übersicht](https://tracesof.net/uebersicht/) 是个壳层 Electron 容器：

- widget = `.coffee` 文件，含 `command:` 字段（任意 shell）+ `render:` 函数（HTML）
- 直接 `python3 ~/Library/...plugins/daily-overview-plugin.py`
- 自定义 CSS，可以做全透明、毛玻璃、固定尺寸
- 缺点：第三方工具，需要单独安装

## 推荐路线：A → B

### Step 1：Übersicht 原型验证

```bash
# 安装
brew install --cask ubersicht
```

写一个 widget 文件 `~/Library/Application Support/Übersicht/widgets/token-used.coffee`：

```coffee
command: "python3 \"#{process.env.HOME}/Library/Application Support/UsageBoard/plugins/daily-overview-plugin.py\" --usageboard-param USAGEBOARD_LANGUAGE=zh-Hans"

refreshFrequency: 60000  # 60 秒

render: (output) -> ""

update: (output, domEl) ->
  data = JSON.parse output
  hero = data.items[0]
  models = data.items[1..]
  domEl.innerHTML = """
    <div class="card">
      <div class="hero">#{hero.name}</div>
      <div class="models">
        #{("<div class='m'>" + m.name + "</div>" for m in models).join('')}
      </div>
    </div>
  """

style: """
  top: 60px
  right: 60px
  width: 280px
  padding: 16px
  background: rgba(0,0,0,0.55)
  backdrop-filter: blur(20px)
  color: white
  font-family: -apple-system
  border-radius: 12px

  .hero
    font-size: 22px
    font-weight: 600
    margin-bottom: 12px

  .m
    font-size: 13px
    opacity: 0.85
    line-height: 1.6
"""
```

然后从菜单栏 Übersicht 图标点 Refresh。

### Step 2：满意后再考虑 B

如果效果好但不想依赖 Übersicht，再做独立 WidgetKit 项目。结构：

```
TokenUsedWidget/
├── TokenUsedWidget.xcodeproj
├── App/                    # 极简容器 app（占位用）
│   └── ContentView.swift
└── Widget/                 # WidgetKit extension
    ├── TokenUsedWidget.swift
    ├── Provider.swift      # TimelineProvider，定期读 states/*.json
    └── Views/
        ├── SmallView.swift
        ├── MediumView.swift
        └── LargeView.swift
```

Provider 核心逻辑：

```swift
let stateURL = FileManager.default
  .urls(for: .applicationSupportDirectory, in: .userDomainMask)
  .first!
  .appendingPathComponent("UsageBoard/states/daily-overview.json")
let state = try JSONDecoder().decode(PluginCachedState.self, from: Data(contentsOf: stateURL))
```

由于 widget 不能调 Python，需要 UsageBoard 在后台保持运行（它会按插件的 `refreshIntervalSeconds` 持续刷新缓存）。Widget 只是这份缓存的"展示窗口"。

## 不推荐 C 的原因

把 widget 集成进 UsageBoard 主项目意味着：

1. **结构改动大**：SwiftPM 不支持 widget extension，必须转 Xcode `.xcodeproj`，触动构建脚本和发布流程
2. **签名复杂**：app + extension + App Group entitlement 需要 paid Apple Developer ID（临时签名 widget 可能不被通知中心信任）
3. **回流难**：除非作者愿意合并 PR，否则 fork 永远要追上游

只有当目标是「让 widget 进上游主分支」时才值得选 C。
