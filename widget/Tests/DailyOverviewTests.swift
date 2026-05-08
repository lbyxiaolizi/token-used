import XCTest

final class DailyOverviewTests: XCTestCase {

    private func loadFixture(_ name: String) throws -> Data {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("\(name).json")
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

        XCTAssertEqual(model.badge, "616.89M")
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
        XCTAssertEqual(model.items.first?.limit, 0)
        XCTAssertEqual(model.items.first?.color, .blue)
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
