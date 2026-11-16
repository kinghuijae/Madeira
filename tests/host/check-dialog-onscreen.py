#!/usr/bin/env python3
"""[dlg-onscreen] and env.MADEIRA_DIALOG_ONSCREEN; no Wine runs.

amakanoPE_kor.exe (report 2026-11-16_09-10-02-amakanoPE, build v0.13.1) opened a 255x86 two-button
screen-mode dialog and centred it on an empty rectangle: {-127,-43,128,43}, its default button off the
1920x1080 desktop. It was shown without activation, so the Return key went nowhere either, and the game
sat in the modal loop until it was quit. build/win32u-unix/driver_ios.c now moves a visible, captioned
top-level game-mode window that is smaller than the virtual screen and partly outside it to the centre of
the screen, on its own thread at its next message poll, and makes it foreground.

Checks: the production decision function compiled and run on the host (the log's rectangle, windows on
the screen, tiny and full-screen windows, other screen origins); the switch (default on, exactly "0" turns
it off); the wiring in driver_ios.c (noted from the game-mode branch of pWindowPosChanged with the window
rect, applied from pProcessEvents outside SetWindowPos, own thread only, captioned non-child windows only,
two moves per window, the move keeps size and z-order, foreground only when it is not already).
The host run is skipped when no C compiler is found; the source checks still run.
"""
from pathlib import Path
import os, shutil, subprocess, tempfile

root = Path(__file__).resolve().parents[2]
drv = (root / "build/win32u-unix/driver_ios.c").read_text(encoding="utf-8")


def function(signature):
    start = drv.index(signature)
    return drv[start:drv.index("\n}\n", start) + 3] + "\n"


# --- the decision, compiled and run ----------------------------------------------------------------------
region = (function("static int ios_dialog_onscreen_enabled(void)")
          + function("static int ios_dialog_onscreen_target( int left, int top, int right, int bottom, int screen_left, int screen_top,"))
harness = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
""" + region + r"""
int main( int argc, char **argv )
{
    int i;
    printf( "%d\n", ios_dialog_onscreen_enabled() );
    for (i = 1; i + 7 < argc; i += 8)
    {
        int x = -9999, y = -9999;
        int r = ios_dialog_onscreen_target( atoi( argv[i] ), atoi( argv[i + 1] ), atoi( argv[i + 2] ), atoi( argv[i + 3] ),
                                            atoi( argv[i + 4] ), atoi( argv[i + 5] ), atoi( argv[i + 6] ), atoi( argv[i + 7] ),
                                            &x, &y );
        if (r) printf( "%d,%d\n", x, y );
        else printf( "-\n" );
    }
    return 0;
}
"""
HD = (0, 0, 1920, 1080)
# (window rect, screen rect) -> new top-left corner, or "-" for "leave it"
cases = [
    ((-127, -43, 128, 43), HD, "832,497"),      # the report: centred on an empty rectangle
    ((-10, 100, 245, 186), HD, "832,497"),      # one pixel column off the left edge is enough
    ((1700, 1000, 1955, 1086), HD, "832,497"),  # off the bottom-right
    ((0, 0, 255, 86), HD, "-"),                 # exactly in the corner: on the screen
    ((832, 497, 1087, 583), HD, "-"),           # already centred (what the first move gives)
    ((1665, 994, 1920, 1080), HD, "-"),         # touching the far edges is still on the screen
    ((-20, -20, 0, 0), HD, "-"),                # under 32x32: the IME and message windows
    ((-5, -5, 26, 300), HD, "-"),               # 31 wide
    ((-8, -8, 1928, 1088), HD, "-"),            # a maximised / full-screen window larger than the screen
    ((-1, 0, 1919, 1080), HD, "-"),             # as wide as the screen: a game window, not a dialog
    ((-1, 0, 1918, 1079), HD, "0,0"),           # one pixel smaller both ways is a window that fits
    ((-127, -43, 128, 43), (0, 0, 1280, 720), "512,317"),
    ((-2000, 50, -1745, 136), (-1920, 0, 1920, 1080), "-128,497"),  # a virtual screen that starts left of 0
    ((-300, 50, -45, 136), (-1920, 0, 1920, 1080), "-"),             # left of 0 but on that screen
]
# The two expected corners above that depend on arithmetic, written out: (1920-255)/2, (1080-86)/2, ...
assert (1920 - 255) // 2 == 832 and (1080 - 86) // 2 == 497 and (1280 - 255) // 2 == 512 and (720 - 86) // 2 == 317
assert -1920 + (3840 - 255) // 2 == -128 and (1920 - 1919) // 2 == 0

cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
if not cc:
    print("SKIP: the decision function needs a C compiler; source checks only")
else:
    with tempfile.TemporaryDirectory() as t:
        c = Path(t) / "dlg.c"
        c.write_text(harness)
        exe = Path(t) / "dlg"
        flags = ["-std=gnu11", "-Wall", "-Wno-unused-function"]
        if os.name != "nt":
            flags.append("-fsanitize=address,undefined")
        subprocess.run([cc] + flags + [str(c), "-o", str(exe)], check=True)

        def run(env, args):
            e = {k: v for k, v in os.environ.items() if k != "MADEIRA_DIALOG_ONSCREEN"}
            e.update(env)
            r = subprocess.run([str(exe)] + [str(a) for a in args], capture_output=True, text=True, env=e)
            assert r.returncode == 0, (env, r.returncode, r.stdout, r.stderr)
            return r.stdout.split()

        flat = [v for window, screen, _ in cases for v in window + screen]
        out = run({}, flat)
        assert out[0] == "1", out                                    # unset: on
        assert out[1:] == [want for _, _, want in cases], list(zip(out[1:], cases))
        for value, want in (("0", "0"), ("1", "1"), ("", "1"), ("00", "1"), ("off", "1")):
            assert run({"MADEIRA_DIALOG_ONSCREEN": value}, [])[0] == want, (value, want)  # exactly "0" turns it off

# --- the wiring in driver_ios.c ------------------------------------------------------------------------------
note = function("static void ios_note_offscreen_dialog( HWND hwnd, const RECT *window )")
assert "if (!ios_dialog_onscreen_enabled()) return;" in note
assert "(style & (WS_CHILD | WS_MINIMIZE)) || !(style & WS_VISIBLE) || (style & WS_CAPTION) != WS_CAPTION" in note
assert "get_window_thread( hwnd, NULL ) != GetCurrentThreadId()" in note        # only the window's own thread
assert "hwnd == ios_offscreen_last && ios_offscreen_moves >= 2" in note
assert "ios_offscreen_dialog = hwnd;" in note
assert "NtUserSetWindowPos" not in note                                          # never inside pWindowPosChanged

apply = function("static void ios_apply_offscreen_dialog(void)")
assert apply.index("ios_offscreen_dialog = 0;") < apply.index("NtUserSetWindowPos")   # one try per note
assert "!is_window( hwnd ) || !is_window_visible( hwnd )" in apply
assert "get_window_rect( hwnd, &rect, get_thread_dpi() )" in apply                     # re-checked when it acts
assert apply.index("ios_dialog_onscreen_target(") < apply.index("NtUserSetWindowPos")
assert apply.index("if (ios_offscreen_moves >= 2) return;") < apply.index("NtUserSetWindowPos")
assert "NtUserSetWindowPos( hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE );" in apply
assert apply.count("NtUserSetWindowPos") == 1
assert "!= hwnd && !(get_window_long( hwnd, GWL_STYLE ) & WS_DISABLED)" in apply
assert "set_foreground_window( hwnd, FALSE, TRUE )" in apply
assert "[dlg-onscreen] hwnd=%p" in apply and "MADEIRA_DIALOG_ONSCREEN=0 disables" in apply

events = function("static BOOL winios_drv_process_events( DWORD mask )")
assert "if (ios_offscreen_dialog) ios_apply_offscreen_dialog();" in events
assert events.index("ios_apply_offscreen_dialog();") < events.index("winios_pProcessEvents( mask )")

changed = function("static void winios_drv_window_pos_changed(")
branch = changed[changed.index("if (visible && surface && winios_game_windows())"):]
branch = branch[:branch.index("}") + 1]
assert "winios_note_dialog_thread( hwnd, v );" in branch                          # the 16 ms wake still comes first
assert "ios_note_offscreen_dialog( hwnd, &new_rects->window );" in branch
# that branch sits inside the top-level / game-mode test
assert changed.index("NtUserGetAncestor( hwnd, GA_PARENT ) == get_desktop_window()") < changed.index("ios_note_offscreen_dialog(")

# --- the key ---------------------------------------------------------------------------------------------
catalog = root / "app/Madeira/ConfigCatalog.generated.swift"
if catalog.exists():
    assert 'ConfigOption(key: "env.MADEIRA_DIALOG_ONSCREEN"' in catalog.read_text(encoding="utf-8"), \
        "the settings catalog lists env.MADEIRA_DIALOG_ONSCREEN"

print("PASS: a captioned dialog smaller than the screen and partly off it (the report's {-127,-43,128,43}) is "
      "centred, windows on the screen, tiny ones and screen-sized ones are left alone, other screen origins work; "
      "it is on unless the switch is exactly 0; it is noted in pWindowPosChanged and moved from pProcessEvents on "
      "its own thread, twice at most, keeping size and z-order, and made foreground; the key is in the catalog")
