// SPDX-License-Identifier: GPL-3.0-or-later
// Madeira Converter Exception: see LICENSE-EXCEPTION.md
//
//  Send Logs to GitHub: the files Get Help from Claude shares (ClaudeHelp.files:
//  the summary, the logs, madeira.cfg and a game's config and settings), less the
//  guide, committed in one commit to a private repository of the owner's, under
//  reports/<time>-<game>/ with a REPORT.md (game, build, device, the note typed
//  before sending). The game-triage Claude Code skill reads the newest report
//  from there (tools/game-report.py), on a PC or in a cloud session, so logs
//  never have to be copied by hand.
//
//  Logs over 512 KB are sent gzipped (logs compress about tenfold), and only
//  their last 64 MB. The token is a fine-grained one for that repository only
//  (Contents: Read and write), kept in Keychain on this device and never logged.
//  Nothing is sent until Send is tapped. Checked by tests/host/check-github-logs.py.
//

import Foundation
import Security
import SwiftUI
import UIKit

enum GitHubLogs {
    /// "owner/name" of the logs repository (Settings › Advanced › GitHub Logs).
    static let repoKey = "githubLogsRepo"
    /// Whether a token was saved, so the buttons show without reading Keychain.
    static let tokenSavedKey = "githubLogsTokenSaved"

    static let compressFrom = 512 * 1024
    static let maxLogBytes = 64 << 20

    static var repo: String {
        (UserDefaults.standard.string(forKey: repoKey) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func validRepo(_ text: String) -> Bool {
        text.range(of: #"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$"#, options: .regularExpression) != nil
    }

    struct Failure: LocalizedError {
        let text: String
        var errorDescription: String? { text }
    }

    struct Sent {
        let folder: String
        let url: URL
    }

    struct File {
        let path: String
        let data: Data
    }

    /// Commits this report and returns where it is.
    @MainActor static func send(entry: LibraryEntry?, note: String) async throws -> Sent {
        let repo = self.repo
        guard validRepo(repo) else {
            throw Failure(text: L("Enter the repository as owner/name in Settings › Advanced › GitHub Logs."))
        }
        guard let token = GitHubLogsKeychain.load(), !token.isEmpty else {
            throw Failure(text: L("Save a GitHub token in Settings › Advanced › GitHub Logs first."))
        }
        let hold = BackgroundRun.shared.beginTask("GitHub logs") {}
        defer { BackgroundRun.shared.endTask(hold) }

        let title = entry?.title ?? "Madeira"
        let folder = "reports/" + stamp() + "-" + slug(title)
        let header = reportHeader(entry: entry)
        let sources = ClaudeHelp.files(for: entry).filter { $0.lastPathComponent != ClaudeHelp.fileName }
        LogStore.shared.log("[github-logs] sending \(sources.count) files to \(repo) as \(folder)")

        let files = await Task.detached(priority: .userInitiated) { () -> [File] in
            prepare(sources, header: header, note: note)
        }.value
        let api = GitHubAPI(repo: repo, token: token)
        do {
            let branch = try await api.commit(files.map { File(path: folder + "/" + $0.path, data: $0.data) },
                                              message: "Report: \(title)")
            let bytes = files.reduce(0) { $0 + $1.data.count }
            LogStore.shared.log("[github-logs] sent \(files.count) files, \(bytes) bytes, to \(repo)@\(branch):\(folder)")
            let path = folder.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? folder
            let url = URL(string: "https://github.com/\(repo)/tree/\(branch)/\(path)")
                ?? URL(string: "https://github.com/\(repo)")!
            return Sent(folder: folder, url: url)
        } catch {
            LogStore.shared.log("[github-logs] failed: \(error.localizedDescription)", level: .error)
            throw error
        }
    }

    /// REPORT.md's first lines: what Claude needs before opening any log.
    @MainActor static func reportHeader(entry: LibraryEntry?) -> String {
        let device = UIDevice.current
        var lines = ["# Madeira report", ""]
        lines.append("- Time: \(ISO8601DateFormatter().string(from: Date()))")
        if let entry {
            lines.append("- Game: \(entry.title)")
            lines.append("- Program: \(entry.windowsPath)")
            lines.append("- Bits: \(entry.bits)")
            if let appID = entry.steamAppID { lines.append("- Steam App ID: \(appID)") }
        } else {
            lines.append("- Game: none (sent from Settings)")
        }
        lines.append("- Game in the logs: \(ClaudeHelp.lastProgram() ?? "none yet")")
        lines.append("- Build: \(BuildStamp.text)")
        lines.append("- Device: \(machine()), \(device.systemName) \(device.systemVersion)")
        return lines.joined(separator: "\n")
    }

    /// REPORT.md and the files, the big ones trimmed to their end and gzipped.
    static func prepare(_ sources: [URL], header: String, note: String) -> [File] {
        var files: [File] = []
        var trimmed: [String] = []
        for url in sources {
            guard let read = try? Data(contentsOf: url, options: .mappedIfSafe) else { continue }
            let name = url.lastPathComponent
            guard read.count > compressFrom else {
                files.append(File(path: name, data: Data(read)))
                continue
            }
            var data = read
            if data.count > maxLogBytes {
                trimmed.append("- \(name): the last \(maxLogBytes >> 20) MB of \(data.count >> 20) MB")
                data = Data(data.suffix(maxLogBytes))
            }
            if let packed = gzip(data) {
                files.append(File(path: name + ".gz", data: packed))
            } else {
                files.append(File(path: name, data: Data(data)))
            }
        }
        var report = header + "\n\n## What went wrong\n\n"
        let said = note.trimmingCharacters(in: .whitespacesAndNewlines)
        report += (said.isEmpty ? "(no note)" : said) + "\n"
        if !trimmed.isEmpty { report += "\n## Trimmed\n\n" + trimmed.joined(separator: "\n") + "\n" }
        report += "\n## Files\n\n" + files.map { "- \($0.path) (\($0.data.count) bytes)" }.joined(separator: "\n") + "\n"
        return [File(path: "REPORT.md", data: Data(report.utf8))] + files
    }

    // MARK: gzip

    /// RFC 1952 around NSData's .zlib output, which is raw DEFLATE (RFC 1951).
    static func gzip(_ data: Data) -> Data? {
        guard let deflated = try? (data as NSData).compressed(using: .zlib) as Data else { return nil }
        var out = Data([0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03])
        out.append(deflated)
        withUnsafeBytes(of: crc32(data).littleEndian) { out.append(contentsOf: $0) }
        withUnsafeBytes(of: UInt32(truncatingIfNeeded: data.count).littleEndian) { out.append(contentsOf: $0) }
        return out
    }

    static let crcTable: [UInt32] = (0..<256).map { n -> UInt32 in
        var c = UInt32(n)
        for _ in 0..<8 { c = (c & 1) != 0 ? 0xEDB8_8320 ^ (c >> 1) : c >> 1 }
        return c
    }

    static func crc32(_ data: Data) -> UInt32 {
        var c: UInt32 = 0xFFFF_FFFF
        crcTable.withUnsafeBufferPointer { table in
            data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
                for byte in raw { c = table[Int((c ^ UInt32(byte)) & 0xFF)] ^ (c >> 8) }
            }
        }
        return c ^ 0xFFFF_FFFF
    }

    // MARK: names

    static func stamp() -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        return f.string(from: Date())
    }

    /// A folder name from a game title: letters and digits, the rest as single dashes.
    static func slug(_ title: String) -> String {
        var out = ""
        for ch in title {
            if ch.isLetter || ch.isNumber { out.append(ch) } else if !out.hasSuffix("-") { out.append("-") }
        }
        let cut = String(out.trimmingCharacters(in: CharacterSet(charactersIn: "-")).prefix(48))
        return cut.isEmpty ? "Game" : cut
    }

    static func machine() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafePointer(to: &info.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) { String(cString: $0) }
        }
    }
}

/// The GitHub REST calls for one commit: blobs, a tree on top of the branch, a
/// commit and a fast-forward of the branch (retried when another report landed first).
private struct GitHubAPI {
    let repo: String
    let token: String

    func call(_ method: String, _ path: String, _ body: [String: Any]? = nil) async throws -> (Int, [String: Any]) {
        guard let url = URL(string: "https://api.github.com/repos/\(repo)\(path)") else {
            throw GitHubLogs.Failure(text: L("The repository was not found, or the token cannot see it."))
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 300
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("2022-11-28", forHTTPHeaderField: "X-GitHub-Api-Version")
        request.setValue("Madeira", forHTTPHeaderField: "User-Agent")
        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        return (status, json)
    }

    func expect(_ method: String, _ path: String, _ body: [String: Any]? = nil) async throws -> [String: Any] {
        let (status, json) = try await call(method, path, body)
        guard status == 200 || status == 201 else { throw failure(status, json) }
        return json
    }

    func failure(_ status: Int, _ json: [String: Any]) -> GitHubLogs.Failure {
        let said = json["message"] as? String ?? ""
        switch status {
        case 401: return GitHubLogs.Failure(text: L("GitHub refused the token. Make a new one and save it again."))
        case 403 where !said.lowercased().contains("rate limit"):
            return GitHubLogs.Failure(text: L("The token cannot write to this repository. Give it Contents: Read and write."))
        case 404: return GitHubLogs.Failure(text: L("The repository was not found, or the token cannot see it."))
        default: return GitHubLogs.Failure(text: L("GitHub answered with an error:") + " \(status) \(said)")
        }
    }

    /// The branch's newest commit; nil while the repository is empty (409) or has no such branch (404).
    func head(_ branch: String) async throws -> String? {
        let (status, json) = try await call("GET", "/git/ref/heads/\(branch)")
        if status == 404 || status == 409 { return nil }
        guard status == 200 else { throw failure(status, json) }
        return (json["object"] as? [String: Any])?["sha"] as? String
    }

    func sha(_ json: [String: Any]) throws -> String {
        guard let sha = json["sha"] as? String else {
            throw GitHubLogs.Failure(text: L("GitHub answered with an error:") + " \(json["message"] as? String ?? "?")")
        }
        return sha
    }

    /// One commit with every file; returns the branch it went to.
    func commit(_ files: [GitHubLogs.File], message: String) async throws -> String {
        let info = try await expect("GET", "")
        let branch = info["default_branch"] as? String ?? "main"
        var parent = try await head(branch)
        if parent == nil {
            // An empty repository takes no blobs: its first commit goes through the contents API.
            let readme = "# Madeira logs\n\nReports sent by Madeira (Send Logs to GitHub), read by the game-triage skill.\n"
            _ = try await expect("PUT", "/contents/README.md",
                                 ["message": "Start the Madeira logs", "content": Data(readme.utf8).base64EncodedString()])
            parent = try await head(branch)
        }
        guard var base = parent else { throw failure(404, [:]) }

        var tree: [[String: Any]] = []
        for file in files {
            let blob = try await expect("POST", "/git/blobs",
                                        ["content": file.data.base64EncodedString(), "encoding": "base64"])
            tree.append(["path": file.path, "mode": "100644", "type": "blob", "sha": try sha(blob)])
        }
        for attempt in 0..<3 {
            let commit = try await expect("GET", "/git/commits/\(base)")
            guard let baseTree = (commit["tree"] as? [String: Any])?["sha"] as? String else { throw failure(0, commit) }
            let newTree = try sha(try await expect("POST", "/git/trees", ["base_tree": baseTree, "tree": tree]))
            let newCommit = try sha(try await expect("POST", "/git/commits",
                                                     ["message": message, "tree": newTree, "parents": [base]]))
            let (status, json) = try await call("PATCH", "/git/refs/heads/\(branch)", ["sha": newCommit, "force": false])
            if status == 200 { return branch }
            // 422: the branch moved (another report landed first); build on its new head.
            guard status == 422, attempt < 2, let moved = try await head(branch) else { throw failure(status, json) }
            base = moved
        }
        throw failure(422, [:])
    }
}

/// The token, in Keychain on this device only.
enum GitHubLogsKeychain {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "madeira.github-logs",
         kSecAttrAccount as String: "token", kSecAttrSynchronizable as String: false]
    }

    static func load() -> String? {
        var q = query
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var value: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &value) == errSecSuccess, let data = value as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func save(_ token: String) -> Bool {
        let attributes: [String: Any] = [kSecValueData as String: Data(token.utf8),
                                         kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            return SecItemAdd(query.merging(attributes) { _, new in new } as CFDictionary, nil) == errSecSuccess
        }
        return status == errSecSuccess
    }

    static func delete() {
        SecItemDelete(query as CFDictionary)
    }
}

private struct GitHubLogsResult: Identifiable {
    let id = UUID()
    let sent: GitHubLogs.Sent?
    let error: String
}

/// "Send Logs to GitHub": shown once a repository and a token are saved.
struct GitHubLogsButton: View {
    let entry: LibraryEntry?
    @AppStorage(GitHubLogs.repoKey) private var repo = ""
    @AppStorage(GitHubLogs.tokenSavedKey) private var tokenSaved = false
    @State private var asking = false
    @State private var note = ""
    @State private var sending = false
    @State private var result: GitHubLogsResult?

    var body: some View {
        if tokenSaved && GitHubLogs.validRepo(repo.trimmingCharacters(in: .whitespacesAndNewlines)) {
            Button {
                note = ""
                asking = true
            } label: {
                if sending {
                    Label("Sending logs…", systemImage: "arrow.up.circle")
                } else {
                    Label("Send Logs to GitHub", systemImage: "arrow.up.doc")
                }
            }
            .disabled(sending)
            .alert("Send Logs to GitHub", isPresented: $asking) {
                TextField("What went wrong? (optional)", text: $note)
                Button("Send") { send() }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("The logs, madeira.cfg and the game's config go to your GitHub repository.")
            }
            .alert(result?.sent == nil ? Text("Could not send the logs") : Text("Logs sent"),
                   isPresented: Binding(get: { result != nil }, set: { if !$0 { result = nil } }),
                   presenting: result) { shown in
                if let url = shown.sent?.url {
                    Button("Copy Link") { UIPasteboard.general.string = url.absoluteString }
                }
                Button("OK", role: .cancel) {}
            } message: { shown in
                if shown.sent != nil {
                    Text("Ask Claude Code to run /game-triage. It reads the newest report.")
                } else {
                    Text(verbatim: shown.error)
                }
            }
        }
    }

    private func send() {
        sending = true
        let entry = entry
        let note = note
        Task { @MainActor in
            do {
                result = GitHubLogsResult(sent: try await GitHubLogs.send(entry: entry, note: note), error: "")
            } catch {
                result = GitHubLogsResult(sent: nil, error: error.localizedDescription)
            }
            sending = false
        }
    }
}

/// Settings › Advanced › GitHub Logs: the repository, the token and the button.
struct GitHubLogsSettingsSection: View {
    @AppStorage(GitHubLogs.repoKey) private var repo = ""
    @AppStorage(GitHubLogs.tokenSavedKey) private var tokenSaved = false
    @State private var token = ""

    var body: some View {
        Section {
            TextField("Repository (owner/name)", text: $repo)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            if tokenSaved {
                Button("Remove Token", role: .destructive) {
                    GitHubLogsKeychain.delete()
                    tokenSaved = false
                }
            } else {
                SecureField("Token", text: $token)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Save Token") {
                    if GitHubLogsKeychain.save(token.trimmingCharacters(in: .whitespacesAndNewlines)) {
                        tokenSaved = true
                        token = ""
                    }
                }
                .disabled(token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            GitHubLogsButton(entry: nil)
        } header: {
            Text("GitHub Logs")
        } footer: {
            Text("Send Logs to GitHub commits the logs, madeira.cfg and a game's config to a private repository of yours, where Claude Code reads them. Use a fine-grained token for that repository only, with Contents set to Read and write. The token stays in this device's Keychain.")
        }
    }
}
