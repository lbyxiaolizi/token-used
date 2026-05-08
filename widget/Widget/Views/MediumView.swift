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
