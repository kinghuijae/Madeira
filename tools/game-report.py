#!/usr/bin/env python3
"""Fetch the reports Madeira's "Send Logs to GitHub" commits to the logs repository.

Used by the game-triage Claude Code skill (.claude/skills/game-triage). The app
(app/Madeira/GitHubLogs.swift) commits each report under reports/<time>-<game>/:
REPORT.md, madeira-summary.txt, the logs (gzipped when large), madeira.cfg.txt
and the game's config and settings. This keeps a sparse, blob-less clone of the
repository in .local/madeira-logs (only the reports asked for are downloaded) and
unpacks a report into .local/madeira-reports/<report>/ as plain text.

The repository (owner/name, or a full Git URL) is, in order: --repo, $MADEIRA_LOGS_REPO, `git config madeira.logsRepo`,
then <owner of origin>/madeira-logs. Standard library only:

    python tools/game-report.py list
    python tools/game-report.py fetch                 (the newest report)
    python tools/game-report.py fetch --game Hades    (the newest report whose name has "Hades")
    python tools/game-report.py fetch 2026-11-15_14-03-22-Hades
    python tools/game-report.py history Hades         (print history/<game>.md, if any)
"""
import argparse
import gzip
import os
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# $MADEIRA_REPORTS_HOME moves both folders (tests/host/check-github-logs.py uses it).
HOME = Path(os.environ.get("MADEIRA_REPORTS_HOME") or ROOT / ".local")
CLONE = HOME / "madeira-logs"
OUT = HOME / "madeira-reports"


def git(*args, cwd=None, check=True):
    run = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and run.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{run.stderr.strip()}")
    return run.stdout


def logs_repo(arg):
    if arg:
        return arg
    if os.environ.get("MADEIRA_LOGS_REPO"):
        return os.environ["MADEIRA_LOGS_REPO"]
    configured = git("config", "--get", "madeira.logsRepo", cwd=ROOT, check=False).strip()
    if configured:
        return configured
    origin = git("remote", "get-url", "origin", cwd=ROOT, check=False).strip()
    m = re.search(r"github\.com[:/]([^/]+)/", origin)
    if m:
        return f"{m.group(1)}/madeira-logs"
    sys.exit("No logs repository: pass --repo owner/name or run `git config madeira.logsRepo owner/name`.")


def sync(repo):
    url = repo if "://" in repo else f"https://github.com/{repo}.git"
    if not (CLONE / ".git").exists():
        CLONE.parent.mkdir(parents=True, exist_ok=True)
        print(f"cloning {url} (sparse, without old logs) ...", file=sys.stderr)
        git("clone", "--filter=blob:none", "--sparse", url, str(CLONE))
    else:
        git("pull", "--ff-only", "--quiet", cwd=CLONE)
    git("sparse-checkout", "add", "history", cwd=CLONE, check=False)


def reports():
    listing = git("ls-tree", "-d", "--name-only", "HEAD", "reports/", cwd=CLONE, check=False)
    return sorted(Path(line).name for line in listing.splitlines() if line.strip())


def unpack(name):
    git("sparse-checkout", "add", f"reports/{name}", cwd=CLONE)
    source = CLONE / "reports" / name
    target = OUT / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for f in sorted(source.iterdir()):
        data = f.read_bytes()
        if f.suffix == ".gz":
            try:
                data = gzip.decompress(data)
            except (OSError, EOFError, zlib.error):
                data = zlib.decompress(data[10:-8], -15)  # raw DEFLATE inside, if the trailer is off
            (target / f.stem).write_bytes(data)
        else:
            (target / f.name).write_bytes(data)
    return target


def cmd_list(args):
    sync(logs_repo(args.repo))
    for name in reports()[-args.count:]:
        print(name)


def cmd_fetch(args):
    sync(logs_repo(args.repo))
    names = reports()
    if not names:
        sys.exit("The logs repository has no reports yet: tap Send Logs to GitHub in Madeira first.")
    if args.report:
        if args.report not in names:
            sys.exit(f"No report {args.report}; the newest are:\n" + "\n".join(names[-10:]))
        name = args.report
    elif args.game:
        wanted = [n for n in names if args.game.lower() in n.lower()]
        if not wanted:
            sys.exit(f"No report for '{args.game}'; the newest are:\n" + "\n".join(names[-10:]))
        name = wanted[-1]
    else:
        name = names[-1]
    target = unpack(name)
    print(f"report: {name}")
    print(f"folder: {target}")
    for f in sorted(target.iterdir()):
        print(f"{f.stat().st_size:>12}  {f.name}")
    report = target / "REPORT.md"
    if report.exists():
        print()
        print(report.read_text(encoding="utf-8", errors="replace"))


def cmd_history(args):
    sync(logs_repo(args.repo))
    folder = CLONE / "history"
    matches = sorted(p for p in folder.glob("*.md") if args.game.lower() in p.stem.lower()) if folder.exists() else []
    if not matches:
        print(f"No history for '{args.game}' yet ({folder}).")
    for p in matches:
        print(f"== {p}")
        print(p.read_text(encoding="utf-8", errors="replace"))


def main():
    for stream in (sys.stdout, sys.stderr):  # REPORT.md and game titles are UTF-8; a Windows console may not be
        stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", help="the logs repository, owner/name")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("list", help="the newest report names")
    s.add_argument("--count", type=int, default=15)
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser("fetch", help="download and unpack a report (the newest by default)")
    s.add_argument("report", nargs="?")
    s.add_argument("--game", help="the newest report whose name contains this")
    s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("history", help="what was already tried for a game")
    s.add_argument("game")
    s.set_defaults(fn=cmd_history)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
