# Madeira's Wine patches

Changes to Wine (the `wine` submodule) that live in this repository until
they are in Wine's own repository. `apply.sh` applies them, in file-name
order, to the `wine` working tree before `build/wineserver/build.sh` builds
the server; it skips a patch that is already applied, and `apply.sh --revert`
takes them out. The `wine` submodule pin does not change.

| Patch | What it fixes |
|---|---|
| `0001-server-tcp-connect-timeout.patch` | A TCP connect still pending after `MADEIRA_CONNECT_TIMEOUT_MS` fails with WSAETIMEDOUT, as a connect to a peer that never answers does on Windows, instead of waiting for Darwin's 75 s. Valve's client waited 60 s for test.steampowered.com before it logged on in a Madeira Dock session (an address that did not answer). The app sets 10000 for Dock sessions; unset or 0 leaves connects unbounded. `[srv-conn-timeout]` lines in the log. Checked by `tests/host/check-connect-timeout.py` |

A patch must apply on the current `wine` pin. When the pin moves, rebase the
patches onto it (or drop a patch the new pin already covers).

This is separate from `patches/wine-opengl-winios.patch`, which is applied by
hand before the tracked `opengl32.dll` is rebuilt (`docs/BUILDING.md`).
