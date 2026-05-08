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
            return .failure(.decode(error))
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
