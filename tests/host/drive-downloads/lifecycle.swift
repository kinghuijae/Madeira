// SPDX-License-Identifier: GPL-3.0-or-later
// Madeira Converter Exception: see LICENSE-EXCEPTION.md
import Foundation

@MainActor func check(_ condition: @autoclosure () -> Bool, _ label: String) {
    guard condition() else { fatalError("FAIL: " + label) }; print("PASS: " + label)
}
@MainActor func eventually(_ label: String, _ condition: () -> Bool) async throws {
    for _ in 0..<200 {
        if condition() { print("PASS: " + label); return }
        try await Task.sleep(nanoseconds: 10_000_000)
    }
    fatalError("FAIL: " + label)
}

@main struct LifecycleChecks {
    @MainActor static func main() async throws {
        setbuf(stdout, nil)
        let fm = FileManager.default
        let remote = DriveRemoteFile(id: "f", name: "game.exe", mimeType: "application/octet-stream", size: "3")
        let plan = DriveFilePlan(remote: remote, path: "game.exe", bytes: 3)
        func job(_ title: String) -> DriveJob {
            DriveJob(accountID: "a", source: remote, title: title, files: [plan], directories: [])
        }
        func install(_ value: inout DriveJob, programs: [String]) throws {
            value.state = .chooseProgram; value.installedFolder = "Google Drive/game-" + value.id.uuidString
            value.programs = programs.map { "llation/" + $0 }
            for program in programs {
                let url = LibraryModel.drive.appendingPathComponent(value.installedFolder! + "/" + program)
                try fm.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
                try Data("MZfixture".utf8).write(to: url)
            }
        }
        var single = job("Recovered game"), multiple = job("Choose a launcher")
        try install(&single, programs: ["amakanoPE_kor.exe"])
        try install(&multiple, programs: ["first.exe", "nested/second.bat"])
        var first = job("First download"), second = job("Second download")
        first.state = .paused; second.state = .paused
        first.files.append(DriveFilePlan(remote: remote, path: "data.bin", bytes: 3))
        let saved = DriveStorage.blocks(first)[0]
        try DriveStorage.directory(DriveStorage.block(saved).deletingLastPathComponent())
        try Data("abc".utf8).write(to: DriveStorage.block(saved))
        struct Saved: Codable { var jobs: [DriveJob] }
        let queue = DriveStorage.root.appendingPathComponent("queue.json")
        try JSONEncoder().encode(Saved(jobs: [single, multiple, first, second])).write(to: queue)
        let downloads = DriveDownloads.shared
        downloads.start()
        try await eventually("old single-program installation recovers and registers automatically") {
            downloads.jobs.first { $0.id == single.id }?.state == .ready
        }
        try await eventually("old multiple-program installation refreshes its choices") {
            Set(downloads.jobs.first { $0.id == multiple.id }?.programs ?? []) == Set(["first.exe", "nested/second.bat"])
        }
        check(LibraryModel.shared.entries.first { $0.driveJobID == single.id }?.path == single.installedFolder! + "/amakanoPE_kor.exe", "registration uses the actual installed executable")
        check(downloads.jobs.first { $0.id == multiple.id }?.state == .chooseProgram, "multiple executables require a choice")
        downloads.register(multiple.id, program: "nested/second.bat")
        check(downloads.jobs.first { $0.id == multiple.id }?.state == .ready, "repaired nested launcher can be registered")
        let persisted = try JSONDecoder().decode(Saved.self, from: Data(contentsOf: queue))
        check(persisted.jobs.first { $0.id == single.id }?.programs == ["amakanoPE_kor.exe"], "repaired program list is persisted")
        check(try! Data(contentsOf: LibraryModel.drive.appendingPathComponent(single.installedFolder! + "/amakanoPE_kor.exe")) == Data("MZfixture".utf8), "recovery preserves the installed game")

        let scheduler = BGTaskScheduler.shared, identifier = "test.madeira.download.drive"
        downloads.resume(first.id); downloads.resume(second.id)
        check(scheduler.requests[identifier] != nil, "resuming a Drive queue requests its own activity")
        let activity = scheduler.deliver(identifier)
        check(activity.title == "Downloading First download" && activity.progress.totalUnitCount == 6 && activity.progress.completedUnitCount == 3, "late activity delivery receives saved byte progress")
        downloads.pause(first.id)
        check(activity.title == "Downloading Second download" && activity.progress.totalUnitCount == 3 && activity.progress.completedUnitCount == 0, "activity advances to the next active game")
        downloads.resume(first.id)
        activity.expirationHandler?()
        try await eventually("system cancel pauses all remaining Drive downloads") {
            downloads.jobs.filter { $0.id == first.id || $0.id == second.id }.allSatisfy { $0.state == .paused }
        }
        check(activity.success == false && DriveStorage.has(saved), "system cancel ends the activity and preserves completed blocks")
        NotificationCenter.default.post(name: UIApplication.didBecomeActiveNotification, object: nil)
        check(downloads.jobs.first { $0.id == second.id }?.state == .paused, "foreground does not undo a user's system cancel")
        downloads.resume(first.id)
        check(scheduler.requests[identifier] != nil, "explicit resume starts a new activity")
        downloads.pause(first.id)
        check(scheduler.requests[identifier] == nil, "pausing before activity delivery cancels the pending request")

        var active = true, pauses = 0
        let background = SteamDownloadBackground(source: "Google Drive", suffix: "fixture", usesBackgroundSession: true)
        background.attach(active: { active }, pause: { active = false; pauses += 1 }, resume: {})
        scheduler.refuses = true
        background.downloadStarted(appID: 0, name: "Fallback")
        UIApplication.shared.applicationState = .background
        NotificationCenter.default.post(name: UIApplication.didEnterBackgroundNotification, object: nil)
        check(BackgroundRun.shared.expirations.isEmpty && pauses == 0, "refused activity does not pause URLSession or take app grace time")
        background.finish(success: false)
        scheduler.refuses = false
        background.downloadStarted(appID: 0, name: "Background wake")
        check(scheduler.requests["test.madeira.download.fixture"] == nil, "background URLSession wake never submits a foreground-only task")
        UIApplication.shared.applicationState = .active
        background.downloadStarted(appID: 0, name: "Progress")
        background.progress(doneBytes: 250, totalBytes: 1000)
        let progress = scheduler.deliver("test.madeira.download.fixture")
        check(progress.progress.completedUnitCount == 250 && progress.progress.totalUnitCount == 1000, "progress is retained before system task attachment")
        background.progress(doneBytes: 900, totalBytes: 1000)
        check(progress.progress.completedUnitCount == 900, "live byte progress reaches the system activity")
        background.finish(success: true)
        check(progress.success == true, "completed downloads finish their system activity")
        background.downloadStarted(appID: 0, name: "Quick finish")
        active = false; background.finish(success: true)
        let late = scheduler.deliver("test.madeira.download.fixture")
        check(late.success == true, "a late delivered task ends when the queue is already empty")

        var steamPaused = false
        let steam = SteamDownloadBackground(source: "Steam", suffix: "steamfixture")
        steam.attach(active: { !steamPaused }, pause: { steamPaused = true }, resume: {})
        UIApplication.shared.applicationState = .background
        steam.downloadStarted(appID: 1, name: "Steam fallback")
        check(BackgroundRun.shared.expirations.count == 1, "Steam still takes its existing background grace period")
        let expire = BackgroundRun.shared.expirations.values.first!
        expire()
        check(steamPaused && BackgroundRun.shared.expirations.isEmpty, "Steam still pauses when its grace period expires")
    }
}
