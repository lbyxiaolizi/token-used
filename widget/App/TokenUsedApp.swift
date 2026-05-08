import SwiftUI

@main
struct TokenUsedApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 420, minHeight: 280)
        }
        .windowResizability(.contentSize)
    }
}
