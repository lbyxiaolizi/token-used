import WidgetKit
import SwiftUI

struct OverviewEntry: TimelineEntry {
    let date: Date
    let state: ViewState

    enum ViewState {
        case ok(DailyOverview, isStale: Bool)
        case empty
        case fileMissing
        case decode
    }
}

struct Provider: TimelineProvider {
    private let loader: StateLoader

    init(loader: StateLoader = StateLoader()) {
        self.loader = loader
    }

    func placeholder(in context: Context) -> OverviewEntry {
        OverviewEntry(date: Date(), state: .empty)
    }

    func getSnapshot(in context: Context, completion: @escaping (OverviewEntry) -> Void) {
        completion(makeEntry(at: Date()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<OverviewEntry>) -> Void) {
        let now = Date()
        let entry = makeEntry(at: now)
        let next = now.addingTimeInterval(5 * 60)
        completion(Timeline(entries: [entry], policy: .after(next)))
    }

    private func makeEntry(at date: Date) -> OverviewEntry {
        switch loader.load() {
        case .success(let snap):
            return OverviewEntry(date: date, state: .ok(snap.model, isStale: snap.isStale))
        case .failure(.fileMissing):
            return OverviewEntry(date: date, state: .fileMissing)
        case .failure(.decode):
            return OverviewEntry(date: date, state: .decode)
        case .failure(.empty):
            return OverviewEntry(date: date, state: .empty)
        }
    }
}
