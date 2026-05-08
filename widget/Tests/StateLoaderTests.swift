import XCTest

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

    private func placeFixture(_ name: String, as filename: String = "daily-overview.json",
                              file: StaticString = #filePath, line: UInt = #line) throws -> URL {
        let src = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("\(name).json")
        guard FileManager.default.fileExists(atPath: src.path) else {
            XCTFail("fixture 不存在：\(src.path)", file: file, line: line)
            throw NSError(domain: "fixture", code: 0)
        }
        let dst = tmpDir.appendingPathComponent(filename)
        try FileManager.default.copyItem(at: src, to: dst)
        return dst
    }

    func test_load_success() throws {
        let url = try placeFixture("daily-overview-full")
        // fixture 的 updatedAt 在 2026-05-08；把 now 也固定到当天，避免 stale 干扰
        let fakeNow = ISO8601DateFormatter().date(from: "2026-05-08T11:00:00Z")!
        let loader = StateLoader(stateFileURL: url, now: { fakeNow })

        switch loader.load() {
        case .success(let snapshot):
            XCTAssertNotNil(snapshot.model.badge)
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
        // fixture 的 updatedAt 是 2026-05-08；把 now 拨到 2026-05-10
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
