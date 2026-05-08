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
