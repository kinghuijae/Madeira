---
name: game-triage
description: Read the newest report Madeira sent with "Send Logs to GitHub" from the logs repository, find why a game fails, and fix it, either with config lines for that game or with a code change built by CI. Use when the user says a game crashed, will not start, shows a black screen, runs badly, or asks to look at the latest log or report, in any wording ("방금 게임 깨졌어", "로그 봐줘", "/game-triage Hades").
---

# Game triage

The user is Madeira's developer, testing a new game on their own iPhone. On the
game's page (or on the launch screen when it fails) they tap **Send Logs to
GitHub**, which commits a report to their private logs repository
(`app/Madeira/GitHubLogs.swift`). You read it from there, on their PC or in a
cloud session, so nothing is copied by hand. Then you fix it: config lines when
they are enough, a code change when they are not.

Speak to them as a developer: log lines, layers and file paths are welcome.
This is not the person-facing "Get Help from Claude" flow, so the reply rules in
section 1 of the guide do not apply; its reference sections do.

Arguments, when given, name the game, a report, or the symptom.

## 1. Fetch the report

From the repository root (any Python 3; it uses the standard library only):

```bash
python tools/game-report.py fetch                # the newest report
python tools/game-report.py fetch --game Hades   # the newest one for a game
python tools/game-report.py list                 # the newest report names
```

It keeps a sparse clone of the logs repository in `.local/madeira-logs` and
unpacks the report, gzipped logs included, into `.local/madeira-reports/<report>/`,
then prints the file list and `REPORT.md`: game, Windows path, bitness, build,
device, iOS version and the note the user typed.

The logs repository is `--repo`, then `$MADEIRA_LOGS_REPO`, then
`git config madeira.logsRepo`, then `<owner of origin>/madeira-logs`.

If it fails:
- **Clone refused**: on a PC, the user's Git credentials must reach that
  private repository. In a cloud session, the session's GitHub access must
  include the logs repository as well as Madeira; ask the user to add it.
- **No reports**: in Madeira, Settings › Advanced › GitHub Logs needs the
  repository (owner/name) and a fine-grained token for it with Contents: Read
  and write; then the button appears on each game's page.

## 2. Check it is the right run

- `REPORT.md`'s "Game in the logs" must be the game the report is about (or
  the one the user means). If not, the logs are from another run: ask them to
  play the game until it fails, then send again.
- `madeira-last-game-log.txt` is the last run with a game; `madeira-log.txt`
  is the run that was going when they sent, which may be a later launch.
- `REPORT.md`'s Build is the build on the device. Compare it with
  `git log --oneline -15`: if a fix you would suggest already landed after it,
  the answer is to update the app (SideStore source `main-latest`), not to fix
  it again.

## 3. Read in this order

1. `app/Madeira/Give-to-Claude-with-log-and-cfg.txt`: sections 2 to 9 are the
   known settings, launch modes, memory rules, log tags (6) and the games
   status list (7).
2. `REPORT.md`, then `madeira-summary.txt` in full.
3. The logs with Grep, never whole: they can be tens of MB. Search the tags of
   guide section 6, then the last 200 lines before the end or the crash. A log
   that was cut to its last 64 MB is listed under "Trimmed" in `REPORT.md`.
4. What was already tried: `python tools/game-report.py history <game>` prints
   `history/<game>.md` from the logs repository, so you do not retry what failed.
5. `<game> - game cfg and settings.txt` (this game's config, its Game details
   switches and its library entry) and `madeira.cfg.txt`.
6. Closest matches: `docs/compatibility/`, `docs/LEGACY_GAME_FINDINGS.md`, the
   topic docs under `docs/` for the store or feature involved, and
   `app/Madeira/GameRecommendations.swift` for games with similar engines.

Say what fails, at which layer (app, Madeira Dock/Steam, Wine and
`build/ntdll-unix`, FEX, DXMT, madeira-d3d12), with the exact log lines as
evidence and how sure you are.

## 4A. When a setting can fix it

- One change per try, so the next report says whether it worked.
- Give the game's whole new config in one code block (its current lines plus
  the change, each new line with a `#` comment saying why), to paste over
  Game details › Advanced › This game's config. Global changes to
  `madeira.cfg` only when the problem is not specific to this game.
- A Game details switch (AVX, NVIDIA GPU, fastsync, FPS limit, resolution,
  launch mode) is not in the config: say which switch to change, page by page.
- Then ask them to play again and send a new report.

## 4B. When it needs a code change

- Make the fix in this repository. Most Wine-side fixes live in
  `build/ntdll-unix/` and the app in `app/Madeira/`. The `FEX`, `wine`, `dxmt`
  and `madeira-dock` folders are submodules pinned to the original project's
  forks: changing them needs a personal fork of that submodule first
  (`docs/WINDOWS-DEVELOPMENT.md`), so say so before editing one. Never propose
  sending AI-written code to FEX-Emu upstream (`CONTRIBUTING.md`).
- If it can be both, prefer a per-game config or recommendation over a global
  behaviour change, unless the log shows the same fault would hit other games.
- Add or update the matching `tests/host/check-*.py` and run it. On Windows
  also run `.\tools\check-windows.ps1`; Swift does not compile there, so say
  that the Swift part is checked only by CI.
- Do not commit or push unless the user asks. A push to `main` builds the IPA
  and publishes it to the `main-latest` SideStore source
  (`docs/WINDOWS-DEVELOPMENT.md`); after updating the app they play again and
  send a new report.
- If config lines can work around it until the build lands, give them too (4A)
  and say they are temporary.

## 5. When a fix works

Offer to keep it for the next install and for others:
- the game's lines in `app/Madeira/GameRecommendations.swift` (checked by
  `tests/host/check-game-recommendations.py`);
- the game's line in section 7 of the guide, and any new log tag in section 6
  (checked by `tests/host/check-claude-help-guide.py`);
- a `docs/compatibility/` note for anything long.

## 6. Keep the game's history

The history lives in the logs repository, so a PC session and a cloud session
see the same one. In `.local/madeira-logs`, append to `history/<slug>.md`, where
`<slug>` is the report folder's name after the time
(`2026-11-15_14-03-22-Hades` → `Hades`); create it with the title, Windows path,
bitness and API at the top. One entry per try: the date, the report, the build,
the symptom, what you changed, and, once the next report shows it, the result.
Then commit only that file and push it to the logs repository:

```bash
git -C .local/madeira-logs add history/<slug>.md
git -C .local/madeira-logs commit -m "History: <game>"
git -C .local/madeira-logs push
```

That repository holds nothing but reports and these notes; never push Madeira
itself as part of this step.
