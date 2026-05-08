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
