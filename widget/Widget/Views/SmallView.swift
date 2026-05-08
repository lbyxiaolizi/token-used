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
                    Text(staleLabel(for: model))
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

    private func staleLabel(for model: DailyOverview) -> String {
        guard let updatedAt = model.updatedAt else { return "已过期" }
        let hours = Int(Date().timeIntervalSince(updatedAt) / 3600)
        return hours >= 1 ? "已过期 \(hours)h" : "已过期"
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
