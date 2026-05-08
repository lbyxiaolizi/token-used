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

// MARK: - 占位实现，Task 7 会替换
struct LargeView: View {
    let entry: OverviewEntry
    var body: some View { Text("large placeholder") }
}
