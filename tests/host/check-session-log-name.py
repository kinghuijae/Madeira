#!/usr/bin/env python3
"""A Steam game's session log name (madeira_session_log_name, build/ntdll-unix/process_ios.c).

The function is compiled on its own with the host's C compiler and fed UTF-16
names: a Chinese exe (a Steam game of 2026-11-15 whose name came out as
"_________.exe"), an emoji's surrogate pair, a lone surrogate, the characters a
file name cannot hold, and a name longer than the buffer, which must stop
before a character that would not fit whole.
"""
from pathlib import Path
import os, re, shutil, subprocess, sys, tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'build/ntdll-unix/process_ios.c').read_text(encoding='utf-8')
m = re.search(r'^static unsigned madeira_session_log_name\(.*?^}\n', source, re.S | re.M)
if not m:
    sys.exit('FAIL: madeira_session_log_name is not in process_ios.c')
print('PASS: process_ios.c has madeira_session_log_name')
if 'n = madeira_session_log_name( ip + base, len - base, name, sizeof(name) );' not in source:
    sys.exit('FAIL: madeira_steam_session_log does not name the log with it')
print('PASS: the Steam session log is named with it')

cc = os.environ.get('CC') or shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
if not cc:
    print('SKIP: no C compiler')
    sys.exit(0)

cases = [
    # (UTF-16 units, buffer size, expected UTF-8 bytes)
    ([0x661f, 0x7a7a, 0x5217, 0x8f66, 0x4e0e, 0x767d, 0x7684, 0x65c5, 0x884c] + [ord(c) for c in '.exe'], 64,
     '星空列车与白的旅行.exe'.encode()),
    ([ord(c) for c in 'cs2.exe'], 64, b'cs2.exe'),
    ([0xd83d, 0xde00, ord('.'), ord('e')], 64, '😀.e'.encode()),
    ([0xd83d, ord('a'), 0xde00], 64, b'_a_'),
    ([ord(c) for c in 'a:b*c?"<>|/\\'] + [0x7f, 0x09, 0xe9], 64, b'a_b_c' + b'_' * 9 + 'é'.encode()),
    ([0x661f, 0x7a7a, 0x5217], 8, '星空'.encode()),       # 7 bytes of room: two characters (6), not the third
    ([ord('a')] * 70, 64, b'a' * 63),
    ([], 64, b''),
]

body = ['#include <stdio.h>', '#include <string.h>', 'typedef unsigned short WCHAR;', m.group(0),
        'static int check(const WCHAR *ip, int len, unsigned size, const char *want, unsigned wantn) {',
        '    char name[80]; unsigned n = madeira_session_log_name(ip, len, name, size);',
        '    return n == wantn && !memcmp(name, want, n) && name[n] == 0;', '}', 'int main(void) {', '    int bad = 0;']
for i, (units, size, want) in enumerate(cases):
    body.append(f'    {{ static const WCHAR ip{i}[] = {{ {", ".join(map(str, units)) or "0"} }};')
    escaped = ''.join(f'\\x{b:02x}' for b in want)
    body.append(f'      if (!check(ip{i}, {len(units)}, {size}, "{escaped}", {len(want)})) '
                f'{{ printf("FAIL: case {i}\\n"); bad = 1; }} }}')
body += ['    return bad;', '}']

with tempfile.TemporaryDirectory(prefix='madeira-session-log-name-') as work:
    c = Path(work) / 'check.c'
    exe = Path(work) / 'check'
    c.write_text('\n'.join(body) + '\n', encoding='utf-8')
    built = subprocess.run([cc, '-std=c99', '-Wall', '-Werror', str(c), '-o', str(exe)], capture_output=True, text=True)
    if built.returncode:
        print(built.stderr)
        sys.exit('FAIL: madeira_session_log_name does not compile on its own')
    ran = subprocess.run([str(exe)], capture_output=True, text=True)
    print(ran.stdout, end='')
    if ran.returncode:
        sys.exit('FAIL: madeira_session_log_name gives the wrong name')
print(f'PASS: {len(cases)} names: CJK and emoji as UTF-8, lone surrogates and file-name characters as _, cut on a whole character')
