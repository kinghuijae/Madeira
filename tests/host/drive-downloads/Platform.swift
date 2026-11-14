// SPDX-License-Identifier: GPL-3.0-or-later
// Madeira Converter Exception: see LICENSE-EXCEPTION.md
// Host-only platform signatures for type-checking the actual queue coordinator.
// These do NOT test UIKit lifecycle or OS background transfer behavior.
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

protocol ObservableObject {}
@propertyWrapper struct Published<Value> { var wrappedValue: Value }
struct UIBackgroundTaskIdentifier: Equatable { static let invalid = Self() }
@MainActor final class UIApplication {
    static let shared = UIApplication()
    enum State { case active, background }
    var applicationState = State.active
    static let didBecomeActiveNotification = Notification.Name("active")
    static let didEnterBackgroundNotification = Notification.Name("background")
    func beginBackgroundTask(withName name: String, expirationHandler: (() -> Void)?) -> UIBackgroundTaskIdentifier { .invalid }
    func endBackgroundTask(_ task: UIBackgroundTaskIdentifier) {}
}
@MainActor protocol UIApplicationDelegate {}
struct UNNotificationSound { static let `default` = Self() }
final class UNMutableNotificationContent { var title = ""; var body = ""; var sound: UNNotificationSound? }
struct UNNotificationRequest { init(identifier: String, content: UNMutableNotificationContent, trigger: Int?) {} }
struct UNAuthorizationOptions: OptionSet { var rawValue: Int; static let alert = Self(rawValue: 1); static let sound = Self(rawValue: 2) }
final class UNUserNotificationCenter {
    static func current() -> UNUserNotificationCenter { Self() }
    func requestAuthorization(options: UNAuthorizationOptions, completionHandler: (Bool, Error?) -> Void) { completionHandler(false, nil) }
    func add(_ request: UNNotificationRequest) {}
}
struct ASWebAuthenticationSessionError: Error {
    enum Code { case canceledLogin }; var code: Code
}
@MainActor final class DriveSignIn {
    static let shared = DriveSignIn()
    func run() async throws -> DriveAccount { throw DriveError.signIn }
}
@MainActor final class LibraryModel {
    struct Entry { var driveJobID: UUID?; var path: String }
    static let shared = LibraryModel()
    static var drive: URL { URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("library/drive_c") }
    var entries: [Entry] = []
    func upsertDrive(id: UUID, title: String, path: String) {
        entries.removeAll { $0.driveJobID == id }; entries.append(Entry(driveJobID: id, path: path))
    }
}

// These fakes drive the real SteamDownloadBackground implementation. They test
// lifecycle decisions and progress publication, not iOS presentation/scheduling.
enum SteamSignIn {
    static func flag(_ name: String, default value: Bool) -> Bool { value }
}
enum SteamLog { static func event(_ line: String) {} }
struct SteamDownloadProgress {
    enum Phase { case downloading }
    var doneBytes: UInt64; var totalBytes: UInt64
    var pcName: String?; var pcDropped: Bool; var phase: Phase
}
@MainActor final class SteamOwnedLibrary {
    var hasActiveDownload = false
    func pauseForBackground() {}
    func resumeAfterBackground() {}
    func reconcileSession() {}
}
@MainActor final class BackgroundRun {
    struct Token: Hashable { let id = UUID() }
    static let shared = BackgroundRun()
    var expirations: [Token: () -> Void] = [:]
    func beginTask(_ name: String, expiration: @escaping () -> Void) -> Token {
        let token = Token(); expirations[token] = expiration; return token
    }
    func endTask(_ token: Token) { expirations[token] = nil }
}
class BGTask {
    var expirationHandler: (() -> Void)?
    var success: Bool?
    func setTaskCompleted(success: Bool) { self.success = success }
}
final class BGContinuedProcessingTask: BGTask {
    let progress = Progress(totalUnitCount: 1)
    var title = ""; var subtitle = ""
    func updateTitle(_ title: String, subtitle: String) { self.title = title; self.subtitle = subtitle }
}
final class BGContinuedProcessingTaskRequest {
    enum Strategy { case fail }
    let identifier: String; let title: String; let subtitle: String
    var strategy = Strategy.fail
    init(identifier: String, title: String, subtitle: String) {
        self.identifier = identifier; self.title = title; self.subtitle = subtitle
    }
}
@MainActor final class BGTaskScheduler {
    static let shared = BGTaskScheduler()
    var handlers: [String: (BGTask) -> Void] = [:]
    var requests: [String: BGContinuedProcessingTaskRequest] = [:]
    var refuses = false
    func register(forTaskWithIdentifier identifier: String, using queue: DispatchQueue?, launchHandler: @escaping (BGTask) -> Void) -> Bool {
        handlers[identifier] = launchHandler; return true
    }
    func submit(_ request: BGContinuedProcessingTaskRequest) throws {
        if refuses { throw NSError(domain: "test.scheduler", code: 1) }
        requests[request.identifier] = request
    }
    func cancel(taskRequestWithIdentifier identifier: String) { requests[identifier] = nil }
    func deliver(_ identifier: String) -> BGContinuedProcessingTask {
        requests[identifier] = nil
        let task = BGContinuedProcessingTask(); handlers[identifier]?(task); return task
    }
}

// Queue lifecycle tests never contact Google; failed metadata requests remain
// retryable until a test pauses the queue through the system activity.
final class HostNetwork: URLProtocol {
    static var session: URLSession {
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [HostNetwork.self]
        return URLSession(configuration: config)
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
