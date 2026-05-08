import WidgetKit
import SwiftUI

@main
struct TokenUsedWidget: Widget {
    let kind = "TokenUsedWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: PlaceholderProvider()) { _ in
            Text("placeholder")
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("TokenUsed")
        .description("placeholder")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}

struct PlaceholderEntry: TimelineEntry {
    let date: Date
}

struct PlaceholderProvider: TimelineProvider {
    func placeholder(in context: Context) -> PlaceholderEntry {
        PlaceholderEntry(date: Date())
    }
    func getSnapshot(in context: Context, completion: @escaping (PlaceholderEntry) -> Void) {
        completion(PlaceholderEntry(date: Date()))
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<PlaceholderEntry>) -> Void) {
        completion(Timeline(entries: [PlaceholderEntry(date: Date())], policy: .never))
    }
}
