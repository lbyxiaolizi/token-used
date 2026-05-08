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
                    .font(.caption2)
            }
        }
        .chartXAxis {
            AxisMarks { _ in
                AxisValueLabel()
                    .font(.caption2)
            }
        }
        .accessibilityLabel("近 7 天 token 用量按模型堆叠柱状图")
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
