# 原生 macOS Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `TokenUsed/widget/` 子目录交付一个原生 macOS Xcode 项目，包含极简 host app 与 WidgetKit extension，从 UsageBoard 状态缓存读数据，渲染 Small / Medium / Large 三种尺寸的今日 token 用量小组件。

**Architecture:** Host app 仅作 widget 分发载体；widget extension 通过 `StateLoader` 读取 `~/Library/Application Support/UsageBoard/states/daily-overview.json`，解码为 `DailyOverview`，由 `Provider` 每 5 分钟生成一帧 timeline 给三种 SwiftUI view 渲染。Large 视图用 Swift Charts 画 7 天堆叠柱状图。

**Tech Stack:** Swift 5.9+ / SwiftUI / WidgetKit / Swift Charts / XCTest

**Spec:** `docs/superpowers/specs/2026-05-08-native-macos-widget-design.md`

**前置事实：**
- 仓库根目录：`~/opc/codex/TokenUsed`
- 数据源文件：`~/Library/Application Support/UsageBoard/states/daily-overview.json`（运行时存在）
- 当前分支：`main`（保持单分支即可，spec 已批准）

---

## 文件结构

```
TokenUsed/widget/
├── TokenUsedWidget.xcodeproj/                            Task 0 在 Xcode GUI 中创建
├── App/
│   ├── TokenUsedApp.swift                                Task 8
│   └── ContentView.swift                                 Task 8
├── Widget/
│   ├── TokenUsedWidget.swift                             Task 4
│   ├── Provider.swift                                    Task 4
│   ├── Models/
│   │   └── DailyOverview.swift                           Task 2
│   ├── StateLoader.swift                                 Task 3
│   └── Views/
│       ├── SmallView.swift                               Task 5
│       ├── MediumView.swift                              Task 6
│       └── LargeView.swift                               Task 7
└── Tests/
    ├── Fixtures/
    │   ├── daily-overview-full.json                      Task 1
    │   ├── daily-overview-empty.json                     Task 1
    │   ├── daily-overview-missing-fields.json            Task 1
    │   └── daily-overview-corrupt.json                   Task 1
    ├── DailyOverviewTests.swift                          Task 2
    └── StateLoaderTests.swift                            Task 3
```

---

## Task 0: Xcode 项目骨架（人工 GUI 步骤）

> **重要**：此任务必须由人在 Xcode GUI 中执行。`.xcodeproj` 是包含 `project.pbxproj` 的目录，无法可靠地用脚本生成而不引入额外工具链。完成后 commit 一次，后续 Swift 源码 task 即可全自动化。

**Files:**
- Create: `TokenUsed/widget/TokenUsedWidget.xcodeproj/`
- Create: `TokenUsed/widget/App/TokenUsedApp.swift`（Xcode 自动生成的占位）
- Create: `TokenUsed/widget/Widget/TokenUsedWidget.swift`（Xcode 自动生成的占位）

- [ ] **Step 1: 在 Xcode 创建 host app**

打开 Xcode → `File > New > Project` → macOS → **App** → Next。
- Product Name: `TokenUsedWidget`
- Team: 选个人 Apple ID 即可（用于本地签名，不需付费 Developer Program）
- Organization Identifier: `com.tokenused`
- Interface: **SwiftUI**
- Language: **Swift**
- Storage: **None**
- Include Tests: **勾选**

Save 位置选 `~/opc/codex/TokenUsed/widget/`（如果该目录不存在就在 Finder 里先建一个空 `widget`）。Xcode 会在 `widget/TokenUsedWidget/` 下放源码——把 `widget/TokenUsedWidget/` 改名为 `widget/App/`（在 Xcode 左侧 navigator 里右键 `Show in Finder`，关闭 Xcode，改名后重开 Xcode 修复 group 引用，或直接在 Xcode 里用 right-click rename group 同时勾"Also rename folder"）。

- [ ] **Step 2: 加 Widget Extension**

`File > New > Target` → macOS → **Widget Extension** → Next。
- Product Name: `Widget`
- Include Configuration App Intent: **不勾**
- Include Live Activity: **不勾**
- Embed in Application: `TokenUsedWidget`

完成后 Xcode 创建 `widget/Widget/` 目录。把默认生成的 `Widget.swift` 重命名为 `TokenUsedWidget.swift`（在 navigator 里 right-click rename）。

- [ ] **Step 3: 调整 deployment target 与依赖**

Project navigator 选 `TokenUsedWidget` → `TokenUsedWidget` target → **General** → `Minimum Deployments` 设为 `macOS 14.0`。对 `Widget` target 同样设 `macOS 14.0`。

Widget target → `Build Phases` → `Link Binary With Libraries` → 确认 `WidgetKit.framework` 和 `SwiftUI.framework` 已存在；点 `+` 添加 `Charts.framework`（系统框架）。

- [ ] **Step 4: 验证项目能跑**

Cmd+B 构建。Run host app（不会做任何事，但应该启动一个空白窗口）。
Run widget scheme：左上 scheme 切到 `Widget` → Run → 选 "Today" 或在 Widget Simulator 里加一个 widget，能看到 Xcode 默认生成的占位 widget。

- [ ] **Step 5: Commit**

```bash
cd ~/opc/codex/TokenUsed
echo "widget/build/" >> .gitignore
echo "widget/**/xcuserdata/" >> .gitignore
echo "widget/**/*.xcworkspace/xcuserdata/" >> .gitignore
git add .gitignore widget/
git commit -m "$(cat <<'EOF'
新建 widget Xcode 项目骨架

- macOS App target: TokenUsedWidget
- Widget Extension target: Widget
- Deployment target: macOS 14.0
- 链入 Charts.framework

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: 测试 fixture 准备

**Files:**
- Create: `widget/Tests/Fixtures/daily-overview-full.json`
- Create: `widget/Tests/Fixtures/daily-overview-empty.json`
- Create: `widget/Tests/Fixtures/daily-overview-missing-fields.json`
- Create: `widget/Tests/Fixtures/daily-overview-corrupt.json`

- [ ] **Step 1: 拷贝完整数据 fixture**

```bash
cp "$HOME/Library/Application Support/UsageBoard/states/daily-overview.json" \
   ~/opc/codex/TokenUsed/widget/Tests/Fixtures/daily-overview-full.json
```

- [ ] **Step 2: 写空 items fixture**

文件：`widget/Tests/Fixtures/daily-overview-empty.json`

```json
{
  "badge": null,
  "chart": {
    "bucketUnit": "day",
    "buckets": [],
    "kind": "line",
    "period": "7d"
  },
  "items": [],
  "updatedAt": "2026-05-08T10:00:00Z"
}
```

- [ ] **Step 3: 写字段缺失 fixture**

文件：`widget/Tests/Fixtures/daily-overview-missing-fields.json`

```json
{
  "items": [
    {"id": "x", "name": "x", "used": 1.0}
  ]
}
```

(故意缺少 `updatedAt`、`chart`、`limit`、`color` 等)

- [ ] **Step 4: 写损坏 JSON fixture**

文件：`widget/Tests/Fixtures/daily-overview-corrupt.json`

```
{"items": [   ← 故意损坏，未闭合
```

- [ ] **Step 5: 把 Fixtures 加进 Test target**

在 Xcode 里左侧 navigator 把 `Tests/Fixtures/` 整个 group 拖进 `TokenUsedWidgetTests` target → 在弹窗中选 `Create folder references`（不是 group），勾 `TokenUsedWidgetTests` target。这样运行测试时 fixture 会以 Resource 形式打包进 test bundle。

- [ ] **Step 6: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/Tests/Fixtures/
git commit -m "$(cat <<'EOF'
新增 widget 测试 fixture（完整/空/缺字段/损坏）

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: DailyOverview Codable 模型 + 解码测试

**Files:**
- Create: `widget/Widget/Models/DailyOverview.swift`
- Create: `widget/Tests/DailyOverviewTests.swift`

> 注意：Models/ 目录里的 `DailyOverview.swift` 必须同时加入 **Widget target** 和 **TokenUsedWidgetTests target**（在 Xcode file inspector 的 Target Membership 勾两个），否则测试拿不到类型。

- [ ] **Step 1: 写失败测试**

文件：`widget/Tests/DailyOverviewTests.swift`

```swift
import XCTest
@testable import Widget

final class DailyOverviewTests: XCTestCase {

    private func loadFixture(_ name: String) throws -> Data {
        let bundle = Bundle(for: type(of: self))
        guard let url = bundle.url(forResource: name, withExtension: "json", subdirectory: "Fixtures") else {
            throw XCTSkip("缺少 fixture \(name)")
        }
        return try Data(contentsOf: url)
    }

    private var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }

    func test_decode_full() throws {
        let data = try loadFixture("daily-overview-full")
        let model = try decoder.decode(DailyOverview.self, from: data)

        XCTAssertEqual(model.badge, "553.21M")
        XCTAssertGreaterThan(model.items.count, 0)
        XCTAssertEqual(model.items.first?.id, "overview-today-total")
        XCTAssertEqual(model.items.first?.displayStyle, .ratio)
        XCTAssertEqual(model.chart.period, "7d")
        XCTAssertEqual(model.chart.buckets.count, 7)
    }

    func test_decode_empty() throws {
        let data = try loadFixture("daily-overview-empty")
        let model = try decoder.decode(DailyOverview.self, from: data)

        XCTAssertNil(model.badge)
        XCTAssertEqual(model.items.count, 0)
        XCTAssertEqual(model.chart.buckets.count, 0)
    }

    func test_decode_missing_fields_uses_defaults() throws {
        let data = try loadFixture("daily-overview-missing-fields")
        let model = try decoder.decode(DailyOverview.self, from: data)

        XCTAssertEqual(model.items.count, 1)
        XCTAssertEqual(model.items.first?.limit, 0)        // 缺省默认
        XCTAssertEqual(model.items.first?.color, .blue)    // 缺省默认
        XCTAssertEqual(model.items.first?.displayStyle, .percent)
    }

    func test_decode_corrupt_throws() throws {
        let data = try loadFixture("daily-overview-corrupt")
        XCTAssertThrowsError(try decoder.decode(DailyOverview.self, from: data))
    }

    func test_isHero() throws {
        let data = try loadFixture("daily-overview-full")
        let model = try decoder.decode(DailyOverview.self, from: data)
        XCTAssertTrue(model.items.first!.isHero)
        XCTAssertFalse(model.items.last!.isHero)
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Cmd+U（Test scheme: `TokenUsedWidget`）。
预期：5 个测试都报 `Cannot find 'DailyOverview' in scope`。

- [ ] **Step 3: 实现模型**

文件：`widget/Widget/Models/DailyOverview.swift`

```swift
import Foundation

struct DailyOverview: Codable {
    let updatedAt: Date?
    let badge: String?
    let items: [Item]
    let chart: Chart

    private enum CodingKeys: String, CodingKey {
        case updatedAt, badge, items, chart
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.updatedAt = try c.decodeIfPresent(Date.self, forKey: .updatedAt)
        self.badge = try c.decodeIfPresent(String.self, forKey: .badge)
        self.items = try c.decodeIfPresent([Item].self, forKey: .items) ?? []
        self.chart = try c.decodeIfPresent(Chart.self, forKey: .chart) ?? Chart.empty
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(updatedAt, forKey: .updatedAt)
        try c.encodeIfPresent(badge, forKey: .badge)
        try c.encode(items, forKey: .items)
        try c.encode(chart, forKey: .chart)
    }
}

extension DailyOverview {
    struct Item: Codable, Identifiable {
        let id: String
        let name: String
        let used: Double
        let limit: Double
        let color: ColorTag
        let displayStyle: DisplayStyle

        var isHero: Bool { id == "overview-today-total" }
        var ratio: Double { limit > 0 ? min(used / limit, 1.0) : 0 }

        private enum CodingKeys: String, CodingKey {
            case id, name, used, limit, color, displayStyle
        }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            self.id = try c.decode(String.self, forKey: .id)
            self.name = try c.decode(String.self, forKey: .name)
            self.used = try c.decodeIfPresent(Double.self, forKey: .used) ?? 0
            self.limit = try c.decodeIfPresent(Double.self, forKey: .limit) ?? 0
            self.color = try c.decodeIfPresent(ColorTag.self, forKey: .color) ?? .blue
            self.displayStyle = try c.decodeIfPresent(DisplayStyle.self, forKey: .displayStyle) ?? .percent
        }
    }

    enum ColorTag: String, Codable {
        case red, orange, blue, green, gray
    }

    enum DisplayStyle: String, Codable {
        case ratio, percent
    }

    struct Chart: Codable {
        let kind: String
        let period: String
        let bucketUnit: String
        let buckets: [Bucket]

        static let empty = Chart(kind: "line", period: "7d", bucketUnit: "day", buckets: [])

        struct Bucket: Codable, Identifiable {
            let id: String
            let label: String
            let segments: [Segment]
        }

        struct Segment: Codable {
            let model: String
            let tokens: Double
        }
    }
}
```

- [ ] **Step 4: 跑测试确认通过**

Cmd+U。预期：5 个测试全绿。

如果 `test_decode_full` 报 `chart.buckets.count != 7`：fixture 是直接从生产环境拷的，今天可能是周五；buckets 数量取决于 period（7d）。如不为 7，先 print 真实 count，再调整断言为 `XCTAssertGreaterThanOrEqual(7)`——但按 plugin 代码 buckets 长度严格等于 7。

- [ ] **Step 5: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/Widget/Models/DailyOverview.swift widget/Tests/DailyOverviewTests.swift
git commit -m "$(cat <<'EOF'
新增 DailyOverview Codable 模型与解码测试

覆盖完整 / 空 items / 字段缺失 / 损坏 JSON 四种场景。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: StateLoader 与错误归一化

**Files:**
- Create: `widget/Widget/StateLoader.swift`
- Create: `widget/Tests/StateLoaderTests.swift`

> 把 `StateLoader.swift` 同时加入 Widget target 和 TokenUsedWidgetTests target。

- [ ] **Step 1: 写失败测试**

文件：`widget/Tests/StateLoaderTests.swift`

```swift
import XCTest
@testable import Widget

final class StateLoaderTests: XCTestCase {

    private var tmpDir: URL!

    override func setUpWithError() throws {
        tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tmpDir)
    }

    private func placeFixture(_ name: String, as filename: String = "daily-overview.json") throws -> URL {
        let bundle = Bundle(for: type(of: self))
        let src = bundle.url(forResource: name, withExtension: "json", subdirectory: "Fixtures")!
        let dst = tmpDir.appendingPathComponent(filename)
        try FileManager.default.copyItem(at: src, to: dst)
        return dst
    }

    func test_load_success() throws {
        let url = try placeFixture("daily-overview-full")
        // fixture 的 updatedAt 是 2026-05-08；把 now 也固定到当天，避免 stale
        let fakeNow = ISO8601DateFormatter().date(from: "2026-05-08T11:00:00Z")!
        let loader = StateLoader(stateFileURL: url, now: { fakeNow })

        switch loader.load() {
        case .success(let snapshot):
            XCTAssertEqual(snapshot.model.badge, "553.21M")
            XCTAssertFalse(snapshot.isStale)
        case .failure(let err):
            XCTFail("应成功，得到 \(err)")
        }
    }

    func test_load_file_missing() {
        let url = tmpDir.appendingPathComponent("missing.json")
        let loader = StateLoader(stateFileURL: url, now: { Date() })

        if case .failure(.fileMissing) = loader.load() { return }
        XCTFail("应返回 .fileMissing")
    }

    func test_load_decode_error() throws {
        let url = try placeFixture("daily-overview-corrupt")
        let loader = StateLoader(stateFileURL: url, now: { Date() })

        if case .failure(.decode) = loader.load() { return }
        XCTFail("应返回 .decode")
    }

    func test_load_empty_items() throws {
        let url = try placeFixture("daily-overview-empty")
        let loader = StateLoader(stateFileURL: url, now: { Date() })

        if case .failure(.empty) = loader.load() { return }
        XCTFail("空 items 应返回 .empty")
    }

    func test_load_stale_returns_success_with_flag() throws {
        let url = try placeFixture("daily-overview-full")
        // fixture 的 updatedAt 是 2026-05-08，把 now 拨到 2026-05-10
        let fakeNow = ISO8601DateFormatter().date(from: "2026-05-10T12:00:00Z")!
        let loader = StateLoader(stateFileURL: url, now: { fakeNow })

        switch loader.load() {
        case .success(let snapshot):
            XCTAssertTrue(snapshot.isStale)
            XCTAssertNotNil(snapshot.model.updatedAt)
        case .failure(let err):
            XCTFail("stale 也应返回 success（带 isStale 标记），得到 \(err)")
        }
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Cmd+U。预期：5 个测试报 `Cannot find 'StateLoader' in scope`。

- [ ] **Step 3: 实现 StateLoader**

文件：`widget/Widget/StateLoader.swift`

```swift
import Foundation

enum LoadError: Error {
    case fileMissing
    case decode(Error)
    case empty
}

struct LoadedSnapshot {
    let model: DailyOverview
    let isStale: Bool
}

struct StateLoader {
    let stateFileURL: URL
    let now: () -> Date
    let staleThreshold: TimeInterval

    init(stateFileURL: URL? = nil,
         now: @escaping () -> Date = Date.init,
         staleThreshold: TimeInterval = 3600) {
        self.stateFileURL = stateFileURL ?? Self.defaultStateFileURL()
        self.now = now
        self.staleThreshold = staleThreshold
    }

    static func defaultStateFileURL() -> URL {
        FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("UsageBoard/states/daily-overview.json")
    }

    func load() -> Result<LoadedSnapshot, LoadError> {
        guard FileManager.default.fileExists(atPath: stateFileURL.path) else {
            return .failure(.fileMissing)
        }

        let data: Data
        do {
            data = try Data(contentsOf: stateFileURL)
        } catch {
            return .failure(.fileMissing)
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        let model: DailyOverview
        do {
            model = try decoder.decode(DailyOverview.self, from: data)
        } catch {
            return .failure(.decode(error))
        }

        if model.items.isEmpty {
            return .failure(.empty)
        }

        let isStale: Bool = {
            guard let updatedAt = model.updatedAt else { return false }
            return now().timeIntervalSince(updatedAt) > staleThreshold
        }()

        return .success(LoadedSnapshot(model: model, isStale: isStale))
    }
}
```

- [ ] **Step 4: 跑测试确认通过**

Cmd+U。预期：5 个 StateLoader 测试 + 5 个 DailyOverview 测试全部通过。

- [ ] **Step 5: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/Widget/StateLoader.swift widget/Tests/StateLoaderTests.swift
git commit -m "$(cat <<'EOF'
新增 StateLoader：路径定位、解码、错误归一化

错误类型：fileMissing / decode / stale(>1h) / empty。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: TimelineProvider + Widget 入口

**Files:**
- Create: `widget/Widget/Provider.swift`
- Modify: `widget/Widget/TokenUsedWidget.swift`（替换 Xcode 默认内容）

- [ ] **Step 1: 实现 Provider**

文件：`widget/Widget/Provider.swift`

```swift
import WidgetKit
import SwiftUI

struct OverviewEntry: TimelineEntry {
    let date: Date
    let state: ViewState

    enum ViewState {
        case ok(DailyOverview, isStale: Bool)
        case empty
        case fileMissing
        case decode
    }
}

struct Provider: TimelineProvider {
    private let loader: StateLoader

    init(loader: StateLoader = StateLoader()) {
        self.loader = loader
    }

    func placeholder(in context: Context) -> OverviewEntry {
        OverviewEntry(date: Date(), state: .empty)
    }

    func getSnapshot(in context: Context, completion: @escaping (OverviewEntry) -> Void) {
        completion(makeEntry(at: Date()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<OverviewEntry>) -> Void) {
        let now = Date()
        let entry = makeEntry(at: now)
        let next = now.addingTimeInterval(5 * 60)
        completion(Timeline(entries: [entry], policy: .after(next)))
    }

    private func makeEntry(at date: Date) -> OverviewEntry {
        switch loader.load() {
        case .success(let snap):
            return OverviewEntry(date: date, state: .ok(snap.model, isStale: snap.isStale))
        case .failure(.fileMissing):
            return OverviewEntry(date: date, state: .fileMissing)
        case .failure(.decode):
            return OverviewEntry(date: date, state: .decode)
        case .failure(.empty):
            return OverviewEntry(date: date, state: .empty)
        }
    }
}
```

- [ ] **Step 2: 实现 Widget 入口**

文件：`widget/Widget/TokenUsedWidget.swift`（**完全替换** Xcode 默认内容）

```swift
import WidgetKit
import SwiftUI

@main
struct TokenUsedWidget: Widget {
    let kind = "TokenUsedWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: Provider()) { entry in
            TokenUsedWidgetView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("TokenUsed")
        .description("今日 token 用量与各模型占比")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

struct TokenUsedWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: OverviewEntry

    var body: some View {
        switch family {
        case .systemSmall:  SmallView(entry: entry)
        case .systemMedium: MediumView(entry: entry)
        case .systemLarge:  LargeView(entry: entry)
        default:            MediumView(entry: entry)
        }
    }
}
```

- [ ] **Step 3: 临时占位 view 让项目能编译**

为了让 Task 4 自身可编译（Task 5/6/7 还没做），暂时在 `TokenUsedWidget.swift` 末尾追加：

```swift
// MARK: - 占位实现，Task 5/6/7 会替换
struct SmallView: View {
    let entry: OverviewEntry
    var body: some View { Text("small placeholder") }
}
struct MediumView: View {
    let entry: OverviewEntry
    var body: some View { Text("medium placeholder") }
}
struct LargeView: View {
    let entry: OverviewEntry
    var body: some View { Text("large placeholder") }
}
```

- [ ] **Step 4: 编译验证**

Cmd+B。预期：构建成功。Cmd+U：所有现有测试通过（Provider 没单元测试，因为它依赖 WidgetKit context）。

- [ ] **Step 5: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/Widget/Provider.swift widget/Widget/TokenUsedWidget.swift
git commit -m "$(cat <<'EOF'
新增 Provider 与 Widget 入口

TimelineProvider 5 分钟一帧；三尺寸路由；占位 view 待替换。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: SmallView

**Files:**
- Create: `widget/Widget/Views/SmallView.swift`
- Modify: `widget/Widget/TokenUsedWidget.swift`（删除 SmallView 占位）

- [ ] **Step 1: 实现 SmallView**

文件：`widget/Widget/Views/SmallView.swift`

```swift
import SwiftUI
import WidgetKit

struct SmallView: View {
    let entry: OverviewEntry

    var body: some View {
        switch entry.state {
        case .ok(let model, let isStale): loaded(model, isStale: isStale)
        case .empty:                      message("今日暂无用量")
        case .fileMissing:                message("未检测到 UsageBoard")
        case .decode:                     message("数据格式异常")
        }
    }

    @ViewBuilder
    private func loaded(_ model: DailyOverview, isStale: Bool) -> some View {
        let hero = model.items.first { $0.isHero }
        let top = model.items.first { !$0.isHero }
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Text("今日 token")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if isStale {
                    Text("已过期")
                        .font(.system(size: 9))
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(.gray.opacity(0.25), in: Capsule())
                        .foregroundStyle(.secondary)
                }
            }
            Text(model.badge ?? hero?.name ?? "—")
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            Spacer(minLength: 0)
            if let top {
                Text(top.name)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func message(_ text: String) -> some View {
        VStack(alignment: .leading) {
            Image(systemName: "exclamationmark.triangle")
                .foregroundStyle(.tertiary)
            Text(text)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(3)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

#Preview(as: .systemSmall) {
    TokenUsedWidget()
} timeline: {
    OverviewEntry(date: .now, state: .empty)
}
```

- [ ] **Step 2: 删除 SmallView 占位**

打开 `widget/Widget/TokenUsedWidget.swift`，删掉文件末尾的 `struct SmallView ... }` 占位（保留 MediumView/LargeView 占位）。

- [ ] **Step 3: 编译 + 在 widget simulator 看效果**

Cmd+B。Run widget scheme，在系统 widget gallery 选 `systemSmall`。
- 当前 daily-overview.json 有数据：应看到 "今日 token / 553.21M / claude-opus-4-7..."
- 删 daily-overview.json：应看到 "未检测到 UsageBoard"

- [ ] **Step 4: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/Widget/Views/SmallView.swift widget/Widget/TokenUsedWidget.swift
git commit -m "$(cat <<'EOF'
SmallView：合计大数字 + top1 模型 + 错误态文案

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: MediumView

**Files:**
- Create: `widget/Widget/Views/MediumView.swift`
- Modify: `widget/Widget/TokenUsedWidget.swift`（删除 MediumView 占位）

- [ ] **Step 1: 实现 MediumView**

文件：`widget/Widget/Views/MediumView.swift`

```swift
import SwiftUI
import WidgetKit

struct MediumView: View {
    let entry: OverviewEntry

    var body: some View {
        switch entry.state {
        case .ok(let model, let isStale): loaded(model, isStale: isStale)
        case .empty:                      message("今日暂无用量")
        case .fileMissing:                message("未检测到 UsageBoard，请先安装并启动")
        case .decode:                     message("数据格式异常")
        }
    }

    @ViewBuilder
    private func loaded(_ model: DailyOverview, isStale: Bool) -> some View {
        let hero = model.items.first { $0.isHero }
        let rest = model.items.filter { !$0.isHero }
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(hero?.name ?? "今日合计")
                    .font(.headline)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Spacer()
                if isStale {
                    Text("已过期")
                        .font(.system(size: 10))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(.gray.opacity(0.25), in: Capsule())
                        .foregroundStyle(.secondary)
                }
            }
            VStack(spacing: 5) {
                ForEach(rest.prefix(4)) { item in
                    row(item)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func row(_ item: DailyOverview.Item) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(item.name)
                    .font(.caption)
                    .lineLimit(1)
                Spacer()
                Text(String(format: "%.0f%%", item.ratio * 100))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(.quaternary)
                    Capsule()
                        .fill(color(for: item.color))
                        .frame(width: geo.size.width * item.ratio)
                }
            }
            .frame(height: 4)
        }
    }

    private func color(for tag: DailyOverview.ColorTag) -> Color {
        switch tag {
        case .red:    return .red
        case .orange: return .orange
        case .blue:   return .blue
        case .green:  return .green
        case .gray:   return .gray
        }
    }

    private func message(_ text: String) -> some View {
        Text(text)
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview(as: .systemMedium) {
    TokenUsedWidget()
} timeline: {
    OverviewEntry(date: .now, state: .empty)
}
```

- [ ] **Step 2: 删除 MediumView 占位**

打开 `widget/Widget/TokenUsedWidget.swift`，删掉 MediumView 占位 struct。

- [ ] **Step 3: 编译并目视检查**

Cmd+B。在 widget simulator 加一个 medium：应看到 hero 行 "今日合计 ▸ 553.21M tokens" + 下方各模型条。

- [ ] **Step 4: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/Widget/Views/MediumView.swift widget/Widget/TokenUsedWidget.swift
git commit -m "$(cat <<'EOF'
MediumView：hero + 各模型占比条

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: LargeView + 7 天 Swift Charts 堆叠柱状图

**Files:**
- Create: `widget/Widget/Views/LargeView.swift`
- Modify: `widget/Widget/TokenUsedWidget.swift`（删除 LargeView 占位）

- [ ] **Step 1: 实现 LargeView**

文件：`widget/Widget/Views/LargeView.swift`

```swift
import SwiftUI
import WidgetKit
import Charts

struct LargeView: View {
    let entry: OverviewEntry

    var body: some View {
        switch entry.state {
        case .ok(let model, _):    loaded(model)
        case .empty:               message("今日暂无用量")
        case .fileMissing:         message("未检测到 UsageBoard，请先安装并启动")
        case .decode:              message("数据格式异常")
        }
    }

    @ViewBuilder
    private func loaded(_ model: DailyOverview) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            MediumView(entry: entry)
                .frame(maxHeight: 130)
            Divider()
            chart(model)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func chart(_ model: DailyOverview) -> some View {
        Chart {
            ForEach(model.chart.buckets) { bucket in
                ForEach(bucket.segments, id: \.model) { seg in
                    BarMark(
                        x: .value("Day", bucket.label),
                        y: .value("Tokens", seg.tokens)
                    )
                    .foregroundStyle(by: .value("Model", seg.model))
                }
            }
        }
        .chartLegend(.hidden)
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 3)) { _ in
                AxisGridLine()
                AxisValueLabel()
                    .font(.system(size: 8))
            }
        }
        .chartXAxis {
            AxisMarks { _ in
                AxisValueLabel()
                    .font(.system(size: 8))
            }
        }
    }

    private func message(_ text: String) -> some View {
        Text(text)
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview(as: .systemLarge) {
    TokenUsedWidget()
} timeline: {
    OverviewEntry(date: .now, state: .empty)
}
```

- [ ] **Step 2: 删除 LargeView 占位**

打开 `widget/Widget/TokenUsedWidget.swift`，删掉 LargeView 占位 struct。

- [ ] **Step 3: 编译并目视检查**

Cmd+B。Widget simulator 加 large：应看到上半 medium 内容 + 下半 7 天柱状图（5/06 5/07 5/08 三天有色块，前面四天空）。

- [ ] **Step 4: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/Widget/Views/LargeView.swift widget/Widget/TokenUsedWidget.swift
git commit -m "$(cat <<'EOF'
LargeView：MediumView + 7 天 Swift Charts 堆叠柱状图

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Host App ContentView + 重载按钮

**Files:**
- Modify: `widget/App/TokenUsedApp.swift`（替换 Xcode 默认）
- Modify: `widget/App/ContentView.swift`（替换 Xcode 默认）

- [ ] **Step 1: 替换 TokenUsedApp**

文件：`widget/App/TokenUsedApp.swift`（**整个文件替换**）

```swift
import SwiftUI

@main
struct TokenUsedApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 420, minHeight: 280)
        }
        .windowResizability(.contentSize)
    }
}
```

- [ ] **Step 2: 替换 ContentView**

文件：`widget/App/ContentView.swift`（**整个文件替换**）

```swift
import SwiftUI
import WidgetKit

struct ContentView: View {
    @State private var lastReload: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("TokenUsed Widget")
                .font(.title2).bold()

            Text("将本应用保留在 Applications 文件夹后，桌面右键 → 编辑小组件 → 添加 “TokenUsed”，即可在桌面看到今日 token 用量。")
                .font(.body)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            Text("数据由 UsageBoard 写入：~/Library/Application Support/UsageBoard/states/daily-overview.json")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .textSelection(.enabled)

            Spacer()

            HStack {
                Button {
                    WidgetCenter.shared.reloadAllTimelines()
                    lastReload = Date()
                } label: {
                    Label("重载所有时间线", systemImage: "arrow.clockwise")
                }
                if let lastReload {
                    Text("上次重载：\(lastReload.formatted(date: .omitted, time: .standard))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(20)
    }
}

#Preview { ContentView() }
```

- [ ] **Step 3: 编译并启动 host app**

Cmd+R（host app scheme）。预期：弹出窗口，标题 "TokenUsed Widget"，能点 "重载所有时间线"。

- [ ] **Step 4: Commit**

```bash
cd ~/opc/codex/TokenUsed
git add widget/App/TokenUsedApp.swift widget/App/ContentView.swift
git commit -m "$(cat <<'EOF'
极简 host app：说明文案 + 重载所有时间线按钮

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 全链路手测 + 文档回填

**Files:**
- Modify: `README.md`
- Modify: `docs/WIDGET.md`

- [ ] **Step 1: 全链路手测清单**

在 Xcode 同时跑 widget scheme，桌面添加三个尺寸的 widget。逐项验证：

| # | 操作 | 预期 |
|---|---|---|
| 1 | 当前 daily-overview.json 完整 | 三个 widget 都正常显示数据 |
| 2 | 点 host app 的"重载所有时间线" | widget 立即重读，显示一致 |
| 3 | `mv ~/Library/Application\ Support/UsageBoard/states/daily-overview.json{,.bak}`，再"重载" | 三个 widget 显示 "未检测到 UsageBoard" 类文案 |
| 4 | 把 .bak 改回来 | 重载后恢复正常 |
| 5 | 把 daily-overview.json 改成 `{` 单字符 | 重载后显示 "数据格式异常" |
| 6 | 改回正常 | 恢复 |
| 7 | 把 daily-overview.json 的 `updatedAt` 改成 2 天前 | 重载后 small/medium 仍显示数据，但角落出现 "已过期" 灰色徽标；large 不显示徽标但数据仍在 |
| 8 | 改回正常 | 恢复 |

任何项失败：回到对应 Task 修复后再继续。

- [ ] **Step 2: 更新 README 路线图**

打开 `~/opc/codex/TokenUsed/README.md`，把：

```
- [ ] 桌面小组件（参见 [docs/WIDGET.md](docs/WIDGET.md)，推荐 Übersicht 路线）
```

改为：

```
- [x] 桌面小组件（原生 WidgetKit）：参见 [widget/](widget/) 与 [docs/WIDGET.md](docs/WIDGET.md)
```

- [ ] **Step 3: 更新 docs/WIDGET.md**

在 `docs/WIDGET.md` 文件最顶部插入一个状态块：

```markdown
> **更新（2026-05-08）**：方案 B（独立 WidgetKit 应用）已落地，源码在 [`widget/`](../widget/)。下文保留三方案对比作为设计依据。
```

构建与安装步骤补一段到方案 B 章节末尾：

```markdown
### 安装（方案 B 已实现）

1. `open widget/TokenUsedWidget.xcodeproj`
2. Xcode → 选 `TokenUsedWidget` scheme → `Product > Archive`
3. Distribute → Copy App → 把 `TokenUsedWidget.app` 拖到 `/Applications`
4. 启动一次该 app（让系统注册 widget extension）
5. 桌面右键 → 编辑小组件 → 搜 "TokenUsed" → 添加（small / medium / large 任选）
```

- [ ] **Step 4: 跑完整测试套件 + 总结提交**

```bash
cd ~/opc/codex/TokenUsed
xcodebuild test -project widget/TokenUsedWidget.xcodeproj -scheme TokenUsedWidget -destination 'platform=macOS'
```

预期：全部测试通过。

```bash
git add README.md docs/WIDGET.md
git commit -m "$(cat <<'EOF'
回填 widget 落地文档

README 路线图勾选；WIDGET.md 顶部加状态块与安装步骤。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: 验收总结**

通报：完成 9 个 task，源码在 `widget/`，spec/plan 在 `docs/superpowers/`，README 已勾选；三尺寸 widget 全部跑通；4 类错误态目视确认。
