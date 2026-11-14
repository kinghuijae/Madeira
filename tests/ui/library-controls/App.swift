import SwiftUI
import UIKit
import GameController

// Only the JIT backend is stubbed. The title/search modifiers are extracted
// verbatim from the app by prepare.py, with one explicit diagnostic switch.
final class LibraryJITState: ObservableObject {
    static let shared = LibraryJITState()
    @Published var enabled = false
}
func L(_ value: String) -> String { value }

@main struct ControlsApp: App {
    var body: some Scene {
        WindowGroup {
            ControlsRoot()
        }
    }
}

struct ControlsRoot: View {
    @State private var tab = 0
    @State private var search = ""
    @State private var settingsSearch = ""
    @State private var add = false
    @State private var sorted = false
    private var plainTitle: Bool { ProcessInfo.processInfo.arguments.contains("--plain-title") }

    var body: some View {
        Group {
            if ProcessInfo.processInfo.arguments.contains("--no-root-modifiers") {
                tabs
            } else {
                tabs.background(Installer()).handlesGameControllerEvents(matching: .gamepad)
            }
        }
    }

    private var tabs: some View {
        TabView(selection: $tab) {
            NavigationStack {
                List {
                    Text(sorted ? "Sorted games" : "Games").accessibilityIdentifier("games")
                    Button("Body action") { sorted.toggle() }
                }
                .modifier(LibraryTabNavigation(search: $search, prompt: "Search your library"))
                .toolbar {
                    if !plainTitle { LibraryLargeTitle() }
                    ToolbarItem(placement: .topBarTrailing) {
                        Menu {
                            Button("Sort games") { sorted = true }
                        } label: { Image(systemName: "line.3.horizontal.decrease") }
                        .accessibilityIdentifier("sort")
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { add = true } label: { Image(systemName: "plus") }
                        .accessibilityIdentifier("add")
                    }
                }
                .sheet(isPresented: $add) { Text("Add game sheet").accessibilityIdentifier("add-sheet") }
            }
            .tabItem { Label("Library", systemImage: "square.grid.2x2.fill") }.tag(0)
            NavigationStack {
                List {
                    Text("Settings page").accessibilityIdentifier("settings-page")
                    NavigationLink("Appearance") { Text("Appearance page") }
                }
                .modifier(LibraryTabNavigation(search: $settingsSearch, prompt: "Search settings"))
                .toolbar { if !plainTitle { LibraryLargeTitle() } }
            }
            .tabItem { Label("Settings", systemImage: "gearshape.fill") }.tag(1)
        }
    }
}

// The production installer's UIView is noninteractive and installs no
// recognizer when New library grid is off, as in this baseline.
struct Installer: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        view.isUserInteractionEnabled = false
        view.isAccessibilityElement = false
        return view
    }
    func updateUIView(_ view: UIView, context: Context) {}
}
