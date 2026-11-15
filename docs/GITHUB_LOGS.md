# Send Logs to GitHub

Madeira can commit a game's logs and configs to a private GitHub repository
of yours, where Claude Code reads them with the `game-triage` skill, on a PC
or in a cloud session. No cable, no share sheet, no copying files by hand.

## Set up once

1. Create a **private** repository, for example `madeira-logs`. It can be
   empty: the first report adds a README.
2. Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new):
   - Repository access: **Only select repositories**, that repository only.
   - Permissions: **Contents: Read and write** (Metadata: Read is added by GitHub).
   - An expiry date you are comfortable with.
3. In Madeira: **Settings › Advanced › GitHub Logs**. Enter the repository as
   `owner/name`, paste the token and tap **Save Token**. The token is kept in
   this device's Keychain (not synced) and is never written to a log.

## Send a report

After a game goes wrong, tap **Send Logs to GitHub** on the game's page (or on
the launch screen, under Get Help from Claude, when a launch fails). Type what
went wrong, or leave it empty, and tap **Send**. Settings has the same button
for the logs without a game.

Each report is one commit under `reports/<yyyy-MM-dd_HH-mm-ss>-<game>/`:

| File | What |
| --- | --- |
| `REPORT.md` | Game, Windows path, bitness, Steam App ID, which game the logs are from, build, device, iOS version, your note, and any log that was cut |
| `madeira-summary.txt` | The summary of the last session with a game |
| `madeira-last-game-log.txt(.gz)` | The last run with a game |
| `madeira-log.txt(.gz)` | The run that was going when you sent |
| `madeira.cfg.txt` | Global settings |
| `<game> - game cfg and settings.txt` | The game's own config, its Game details switches and its library entry |

These are the files Get Help from Claude shares, less the guide. Files over
512 KB are gzipped, and a log over 64 MB keeps only its last 64 MB.

## Read it with Claude Code

In Claude Code, in this repository, run `/game-triage` (optionally with the
game's name). The skill runs `tools/game-report.py`, which keeps a sparse clone
of the logs repository in `.local/madeira-logs`, so old reports are not
downloaded, and unpacks the report into `.local/madeira-reports/`.

The logs repository is found in this order: `--repo`, `$MADEIRA_LOGS_REPO`,
`git config madeira.logsRepo`, then `<owner of origin>/madeira-logs`.

- **On a PC**: your Git credentials need to reach the private repository.
- **In a cloud session** (Claude Code on the web or the Claude app): give the
  session's GitHub access the logs repository as well as Madeira.

The skill records each try in `history/<game>.md` in the logs repository, so a
later session, on either side, knows what was already tried.

`tests/host/check-github-logs.py` checks the app side by reading it and runs
the reader against a local repository made the way the app writes reports.
