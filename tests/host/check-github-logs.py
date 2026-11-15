#!/usr/bin/env python3
"""Send Logs to GitHub (app/Madeira/GitHubLogs.swift) and its reader (tools/game-report.py).

Swift does not run here, so the app side is checked by reading it:
  * the file is in the Xcode project, and the button is on Game details, on the
    launch screen's failure buttons and in Settings (page and search);
  * the token lives in Keychain on this device only and never reaches the log;
  * logs are trimmed and gzipped with the RFC 1952 header, the reflected CRC-32
    polynomial and a little-endian trailer, as tools/game-report.py expects;
  * the report goes under reports/<time>-<game>/ with a REPORT.md first.
The reader is run for real: a local logs repository gets two reports the way the
app writes them (a gzipped log made exactly as GitHubLogs.gzip frames it), and
`fetch`, `fetch --game` and `history` must give back the same bytes.
"""
from pathlib import Path
import os, re, shutil, struct, subprocess, sys, tempfile, zlib

root = Path(__file__).resolve().parents[2]
app = root / 'app/Madeira'
failures = 0


def check(condition, label):
    global failures
    print(('PASS: ' if condition else 'FAIL: ') + label)
    if not condition:
        failures += 1


swift = (app / 'GitHubLogs.swift').read_text(encoding='utf-8')
library = (app / 'Library.swift').read_text(encoding='utf-8')
settings = (app / 'SettingsPages.swift').read_text(encoding='utf-8')
project = (app.parent / 'Madeira.xcodeproj/project.pbxproj').read_text(encoding='utf-8')

check(project.count('A100CA02 /* GitHubLogs.swift in Sources */') == 2 and
      project.count('A200CA02 /* GitHubLogs.swift */') == 3, 'GitHubLogs.swift is in the app target')
check(library.count('GitHubLogsButton(entry: entry)') == 2, 'Game details and the launch screen offer the button')
check('GitHubLogsSettingsSection()' in settings and 'GitHubLogsSettingsSection()' in library,
      'Settings > Advanced and the settings search show the section')

check('kSecAttrService as String: "madeira.github-logs"' in swift and
      'kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly' in swift and
      'kSecAttrSynchronizable as String: false' in swift, 'the token is in Keychain, this device only')
logged = re.findall(r'LogStore\.shared\.log\(([^\n]*)\)', swift)
check(logged and not any('token' in line.lower() for line in logged), 'no log line carries the token')
check('"Bearer \\(token)"' in swift and 'https://api.github.com/repos/' in swift, 'the token only goes to api.github.com')

check('Data([0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03])' in swift, 'gzip header: deflate, no flags, Unix')
check('0xEDB8_8320' in swift and 'compressed(using: .zlib)' in swift, 'raw DEFLATE body and the reflected CRC-32')
check('crc32(data).littleEndian' in swift and 'UInt32(truncatingIfNeeded: data.count).littleEndian' in swift,
      'gzip trailer: CRC-32 and size, little-endian')
check('static let maxLogBytes = 64 << 20' in swift and 'data.suffix(maxLogBytes)' in swift, 'logs keep their last 64 MB')
check('"reports/" + stamp() + "-" + slug(title)' in swift and '"yyyy-MM-dd_HH-mm-ss"' in swift and
      '[File(path: "REPORT.md"' in swift, 'reports/<time>-<game>/ with REPORT.md first')
check('$0.lastPathComponent != ClaudeHelp.fileName' in swift, 'the guide is not sent (the repository has it)')


def app_gzip(data):
    """GitHubLogs.gzip: header, raw DEFLATE, CRC-32, size."""
    c = zlib.compressobj(6, zlib.DEFLATED, -15)
    body = c.compress(data) + c.flush()
    return bytes([0x1f, 0x8b, 8, 0, 0, 0, 0, 0, 0, 3]) + body + struct.pack('<II', zlib.crc32(data), len(data) & 0xffffffff)


def git(*args, cwd):
    subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True)


def report(fetch_args, home, url):
    env = dict(os.environ, MADEIRA_REPORTS_HOME=str(home))
    return subprocess.run([sys.executable, str(root / 'tools/game-report.py'), '--repo', url, *fetch_args],
                          env=env, capture_output=True, text=True, encoding='utf-8')


work = Path(tempfile.mkdtemp(prefix='madeira-github-logs-'))
try:
    source = work / 'logs'
    source.mkdir()
    git('init', '-q', '-b', 'main', cwd=source)
    git('config', 'user.email', 'test@example.invalid', cwd=source)
    git('config', 'user.name', 'test', cwd=source)
    git('config', 'uploadpack.allowFilter', 'true', cwd=source)
    log = b''.join(b'[wine] line %d of the session\n' % i for i in range(60000))
    for name, game in [('2026-11-14_09-00-00-Hades', 'Hades'), ('2026-11-15_14-03-22-Metro-2033', 'Metro 2033')]:
        folder = source / 'reports' / name
        folder.mkdir(parents=True)
        (folder / 'REPORT.md').write_text(f'# Madeira report\n\n- Game: {game}\n', encoding='utf-8')
        (folder / 'madeira-summary.txt').write_text(f'Program: C:\\Games\\{game}\\game.exe\n', encoding='utf-8')
        (folder / 'madeira-last-game-log.txt.gz').write_bytes(app_gzip(log + game.encode()))
    (source / 'history').mkdir()
    (source / 'history' / 'Hades.md').write_text('# Hades\n\n- 2026-11-14: pool = 768, still crashed\n', encoding='utf-8')
    git('add', '.', cwd=source)
    git('commit', '-q', '-m', 'reports', cwd=source)
    url = source.as_uri()
    home = work / 'home'

    newest = report(['fetch'], home, url)
    out = home / 'madeira-reports' / '2026-11-15_14-03-22-Metro-2033'
    check(newest.returncode == 0 and 'report: 2026-11-15_14-03-22-Metro-2033' in newest.stdout and
          '- Game: Metro 2033' in newest.stdout, 'fetch picks the newest report and prints REPORT.md')
    check((out / 'madeira-last-game-log.txt').read_bytes() == log + b'Metro 2033' if out.exists() else False,
          'the app-framed gzip log comes back byte for byte')
    check(not (home / 'madeira-logs' / 'reports' / '2026-11-14_09-00-00-Hades').exists(),
          'the clone checks out only the report asked for')

    by_game = report(['fetch', '--game', 'hades'], home, url)
    check(by_game.returncode == 0 and 'report: 2026-11-14_09-00-00-Hades' in by_game.stdout, 'fetch --game matches the name')
    history = report(['history', 'Hades'], home, url)
    check(history.returncode == 0 and 'pool = 768' in history.stdout, 'history prints what was tried')
    missing = report(['fetch', 'nope'], home, url)
    check(missing.returncode != 0 and '2026-11-15_14-03-22-Metro-2033' in missing.stderr, 'an unknown report lists the newest')
finally:
    shutil.rmtree(work, ignore_errors=True)

sys.exit(1 if failures else 0)
