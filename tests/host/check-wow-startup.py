#!/usr/bin/env python3
"""Compile the production Unicode hold policy, window lookup and OpenGL TEB fix.

Runs on Windows or POSIX without an iOS SDK. No Wine process or game is run.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from wow_unicode_fixture import ROOT, function, unicode_support

virtual = (ROOT / 'build/ntdll-unix/virtual_ios.c').read_text(encoding='utf-8')
process = (ROOT / 'build/ntdll-unix/process_ios.c').read_text(encoding='utf-8')
gl = (ROOT / 'wine/dlls/opengl32/unix_wgl.c').read_text(encoding='utf-8')
header = (ROOT / 'build/ntdll-unix/opengl_wow64_ios.h').read_text(encoding='utf-8')
build = (ROOT / 'build/ntdll-unix/build.sh').read_text(encoding='utf-8')
assert build.count('-include "$BUILD_DIR/opengl_wow64_ios.h"') == 2
bridge = (ROOT / 'app/Madeira/WineProcessBridge.m').read_text(encoding='utf-8')
assert bridge.index('for (NSString *raw in [gameText ') < bridge.index('__wine_main(argc, argv)')

harness = unicode_support() + r'''
#include <assert.h>
#include <stddef.h>
typedef uintptr_t ULONG_PTR;
typedef uint32_t ULONG;
#define IOS_WOW_MAX_WINDOWS 8
#define IOS_CHILD_SLOTS 32
#define IOS_CHILD_PATH 260
#define IOS_WOW_WINDOW_SIZE ((ULONG_PTR)1 << 32)
#define pthread_mutex_lock(p) ((void)(p))
#define pthread_mutex_unlock(p) ((void)(p))
#define pthread_equal(a,b) ((a) == (b))
#define pthread_self() 7
#define dprintf(fd,...) fprintf(stderr, __VA_ARGS__)
#ifdef _WIN32
__declspec(dllimport) void * __stdcall VirtualAlloc(void *, size_t, unsigned long, unsigned long);
__declspec(dllimport) int __stdcall VirtualFree(void *, size_t, unsigned long);
#define setenv(k,v,overwrite) _putenv_s(k,v)
#define unsetenv(k) _putenv_s(k, "")
#else
#include <sys/mman.h>
#endif
typedef struct { unsigned short Length, MaximumLength; WCHAR *Buffer; } UNICODE_STRING;
static int ios_child_lock, ios_wow_mutex, ios_main_image_i386;
static unsigned ios_child_untracked;
static int ios_child_slot_current = -1;
static double ios_child_now(void) { return 0; }
'''
# Compile the actual slot's allocation, copy, accessor and release.
harness += next(line for line in process.splitlines() if line.startswith('static struct { char name[64]; char path[IOS_CHILD_PATH];')
                and 'ios_child_slots[' in line) + '\n'
for signature in ['static void ios_child_path_text(', 'static int ios_child_slot_take(',
                  'static void ios_child_slot_release(', 'const WCHAR *ios_child_image_path(']:
    harness += function(process, signature) + '\n'
start = virtual.index('static WCHAR ios_wow_hold_for[260];')
end = virtual.index('static struct ios_wow_placeholder *ios_wow_placeholder_find(')
harness += virtual[start:end]
harness += r'''
static struct { ULONG_PTR base; unsigned for_game; } ios_wow_placeholders[IOS_WOW_MAX_WINDOWS];
static unsigned ios_wow_placeholder_count;
static void ios_wow_session_arm(void) {}
static int ios_wow_map_allows_window(void) { return 1; }
static unsigned long ios_wow_env_ulong(const char *name, unsigned long fallback)
{ const char *s = getenv(name); return s ? strtoul(s, NULL, 10) : fallback; }
static void ios_wow_reserve_placeholders(unsigned want)
{ ios_wow_placeholder_count = want; ios_wow_placeholders[0].base = 0x7100000000ULL; }
'''
harness += function(virtual, 'static void ios_wow_session_start(') + '\n'
harness += r'''
struct ios_wow_window { ULONG_PTR base; void *peb; int owner, dead, leaked; };
static struct ios_wow_window ios_wow_windows[IOS_WOW_MAX_WINDOWS];
static unsigned ios_wow_window_count = 2;
static void *current_peb;
static void *ios_jit_current_peb(void) { return current_peb; }
'''
for signature in ['static struct ios_wow_window *ios_wow_slot_for_peb(',
                  'static struct ios_wow_window *ios_wow_slot_current(', 'ULONG_PTR ios_wow_base(void)']:
    harness += function(virtual, signature) + '\n'
unixlib = (ROOT / 'wine/include/wine/unixlib.h').read_text(encoding='utf-8')
# The real ios_wow_base is linked here; omit only the optional-symbol guard.
harness += 'static ULONG_PTR ios_wow_host_base(void) { return ios_wow_base(); }\n'
harness += function(unixlib, 'static inline void *ios_wow_host_ptr(') + '\n'
harness += r'''
typedef struct { char unused[0xfdc]; int32_t WowTebOffset; } TEB32;
typedef struct { char unused[0x180c]; int32_t WowTebOffset; } TEB;
static TEB *expected_teb;
static NTSTATUS thread_attach(void *teb) { assert(teb == expected_teb); return 0; }
'''
harness += function(header, 'static inline TEB *madeira_gl_teb64(') + '\n'
harness += '#define get_teb64(teb32) madeira_gl_teb64((ULONG_PTR)(teb32), __func__)\n'
harness += function(gl, 'NTSTATUS wow64_thread_attach(') + '\n'
harness += r'''
static WCHAR *wide(const char *text)
{
    DWORD bytes;
    WCHAR *out = calloc(strlen(text) + 1, sizeof(WCHAR));
    assert(out && !RtlUTF8ToUnicodeN(out, strlen(text) * sizeof(WCHAR), &bytes, text, strlen(text)));
    return out;
}
static void match(const char *text, int wanted)
{
    const WCHAR *seen;
    WCHAR *path = wide(text);
    UNICODE_STRING image = { wcslen(path) * sizeof(WCHAR), 0, path };
    ios_child_slot_current = ios_child_slot_take(&image);
    free(path); /* the slot must own a copy, including paths longer than 260 */
    assert(ios_wow_child_in_hold_folder(&seen) == wanted);
    char utf8[2048];
    assert(!strcmp(ios_wow_path_utf8(seen, utf8, sizeof(utf8)), text));
    ios_child_slot_release(ios_child_slot_current);
    assert(!ios_child_image_path());
}
static void policy(const char *global, const char *game, unsigned wanted)
{
    memset(ios_wow_hold_for, 0, sizeof(ios_wow_hold_for));
    memset(ios_wow_placeholders, 0, sizeof(ios_wow_placeholders));
    unsetenv("MADEIRA_WOW_HOLD_FOR_GAME");
    if (global) setenv("MADEIRA_WOW_HOLD_FOR_GAME", global, 1);
    if (game) setenv("MADEIRA_WOW_HOLD_FOR_GAME", game, 1);
    ios_wow_session_start();
    assert(ios_wow_placeholder_count == 1);
    assert(ios_wow_placeholders[0].base == 0x7100000000ULL);
    assert(ios_wow_placeholders[0].for_game == wanted);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    init_case_table(argv[1]);
    setenv("MADEIRA_WOW_HOLD_WINDOWS", "1", 1);
    unsetenv("MADEIRA_WOW_PLACEHOLDERS");
    setenv("MADEIRA_WOW_HOLD_FOR", "C:/Program Files (x86)/Steam/steamapps/common/星空列车与白的旅行", 1);
    policy(NULL, NULL, 1);
    match("c:\\program files (x86)\\steam\\steamapps\\common\\星空列车与白的旅行\\星空列车与白的旅行.exe", 1);
    match("\\??\\C:/Program Files (x86)/Steam/steamapps/common/星空列车与白的旅行/Bin/game.exe", 1);
    match("\\\\?\\C:/Program Files (x86)/Steam/steamapps/common/星空列车与白的旅行/game.exe", 1);
    match("C:/Program Files (x86)/Steam/steamapps/common/星空列车与白的旅行2/game.exe", 0);
    match("C:/Program Files (x86)/Common Files/Steam/SteamService.exe", 0);
    match("C:/", 0);
    match("\\", 0);
    char long_path[700] = "C:/Program Files (x86)/Steam/steamapps/common/星空列车与白的旅行/";
    memset(long_path + strlen(long_path), 'a', 400);
    match(long_path, 1);
    policy("1", "0", 0);
    policy("0", NULL, 0);
    policy("0", "1", 1);
    setenv("MADEIRA_WOW_HOLD_FOR", "\\\\?\\C:/GÄMES/ТЕСТ/", 1);
    policy(NULL, NULL, 1);
    match("c:/gämes/тест/game.exe", 1);
    setenv("MADEIRA_WOW_HOLD_FOR", "C:/Games/Terraria/", 1);
    policy(NULL, NULL, 1);
    match("C:/games/TERRARIA/Terraria.exe", 1);
    match("C:/games/Terraria2/game.exe", 0);
    puts("PASS: original UTF-16 paths, UTF-8 diagnostics, Unicode case, slashes, prefixes and folder boundary");
    puts("PASS: default restriction, global=0, game=0 and game=1 overriding global=0");

    ULONG_PTR bases[] = { 0x7100000000ULL, 0x7a00000000ULL, 0 };
    for (unsigned i = 0; i < 3; i++)
    {
        void *address = (void *)(bases[i] + 0x300000);
#ifdef _WIN32
        void *mapped = VirtualAlloc(address, 0x4000, 0x3000, 0x04);
#else
        void *mapped = mmap(address, 0x4000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
#endif
        assert(mapped == address);
        ios_wow_windows[i] = (struct ios_wow_window){ bases[i], (void *)(uintptr_t)(i + 1), 7, 0, 0 };
        ios_wow_window_count = i == 2 ? 0 : 2;
        current_peb = ios_wow_windows[i].peb;
        expected_teb = mapped;
        TEB32 *teb32 = (TEB32 *)((char *)mapped + 0x2000);
        teb32->WowTebOffset = -0x2000;
        assert(offsetof(TEB32, WowTebOffset) == 0xfdc);
        assert(ios_wow_base() == bases[i]);
        assert(!wow64_thread_attach(teb32));
        assert(!wow64_thread_attach((void *)0x302000));
        assert(get_teb64(0x302000) == expected_teb);
#ifdef _WIN32
        assert(VirtualFree(mapped, 0, 0x8000));
#else
        assert(!munmap(mapped, 0x4000));
#endif
    }
    ios_wow_window_count = 2;
    current_peb = NULL;
    ios_wow_windows[0].owner = 8;
    assert(ios_wow_base() == bases[1]); /* boot-thread fallback also finds the spill */
    ios_wow_windows[1].dead = 1;
    ios_wow_windows[0].leaked = 1;
    assert(!ios_wow_base());
    /* An already-host pointer without a window stays intact too. */
    TEB32 legacy = {0};
    legacy.WowTebOffset = 0;
    assert(get_teb64((ULONG_PTR)&legacy) == (TEB *)&legacy);
    puts("PASS: actual wow64_thread_attach at B=0x7100000000, B=0x7a00000000 and B=0; no double base");
    puts("PASS: registry PEB lookup, boot-thread fallback and dead/leaked window exclusion");
    return 0;
}
'''

cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
if not cc:
    raise SystemExit('C compiler required for WoW startup regression check')
with tempfile.TemporaryDirectory(prefix='madeira-wow-startup-') as tmp:
    src = Path(tmp) / 'check.c'
    exe = Path(tmp) / ('check.exe' if os.name == 'nt' else 'check')
    src.write_text(harness, encoding='utf-8')
    subprocess.run([cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Wno-implicit-fallthrough',
                    '-Wno-unused-parameter', '-Werror', str(src), '-o', str(exe)], check=True)
    subprocess.run([str(exe), str(ROOT / 'wine/nls/l_intl.nls')], check=True)
    # Check the real forced-include integration against Wine's complete headers,
    # as well as the executable harness above (which isolates the runtime code).
    src.write_text('#include <wchar.h>\n#undef iswspace\n#include "opengl_wow64_ios.h"\n' +
                   function(gl, 'NTSTATUS wow64_thread_attach('), encoding='utf-8')
    for flags in [[], ['-DWINE_IOS=1']]:
        subprocess.run([cc, '-fsyntax-only', '-Werror=implicit-function-declaration',
                        '-D__WINESRC__', '-D_NTSYSTEM_', '-D_ACRTIMP=', '-DWINBASEAPI=', '-DWINE_UNIX_LIB',
                        '-I' + str(ROOT / 'build/ntdll-unix'), '-I' + str(ROOT / 'wine/dlls/opengl32'),
                        '-I' + str(ROOT / 'wine/include'), *flags, str(src)], check=True)
    print('PASS: native-build shim compiles with real Wine headers, with and without WINE_IOS')
