#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 ft7t8drgwf-wq
# Madeira Converter Exception: see LICENSE-EXCEPTION.md
"""A TCP connect still pending after MADEIRA_CONNECT_TIMEOUT_MS fails with
WSAETIMEDOUT (build/wine-patches/0001-server-tcp-connect-timeout.patch).

Valve's client checks test.steampowered.com before it logs on, and waited
60 s for an address that never answered the SYN (device log 2026-11-15:
218.38.137.28:80, Steam logon 61 s instead of 1 s). The wineserver now arms a
timer when a TCP connect starts and, if the socket is still connecting when it
fires, records ETIMEDOUT as the connect error and runs the socket's own POLLERR
path, so select, SO_ERROR and ConnectEx all see the failure.

Checks:
- the patch's text: it touches server/sock.c only, behind WINE_IOS, arms the
  timer where a TCP socket enters SOCK_CONNECTING, cancels it when the connect
  completes or fails and when the socket is destroyed, and initialises it in
  create_socket;
- build/wineserver/build.sh applies build/wine-patches before it compiles, and
  every wine patch applies in order on the pinned wine;
- the patched timer helpers, compiled out of the patched sock.c against fakes:
  the switch's range (1000-120000 ms, anything else is off), the relative
  timeout, a timer that fires on a connecting socket (ETIMEDOUT + one POLLERR),
  one that fires after the connect finished (nothing), a restart that replaces
  the first timer, and a cancel;
- the app sets 10000 for Madeira Dock sessions before the config's env lines,
  and the catalog and the help guide list the switch.
"""
from pathlib import Path
import os, re, shutil, subprocess, sys, tempfile

root = Path(__file__).resolve().parents[2]
patches = root / 'build/wine-patches'
patch_path = patches / '0001-server-tcp-connect-timeout.patch'
patch = patch_path.read_text(encoding='utf-8')
failures = 0


def check(condition, label):
    global failures
    print(('PASS: ' if condition else 'FAIL: ') + label)
    if not condition:
        failures += 1


files = sorted(l.split(' b/')[-1] for l in patch.splitlines() if l.startswith('diff --git'))
check(files == ['server/sock.c'], 'touches server/sock.c only')
added = '\n'.join(l[1:] for l in patch.splitlines() if l.startswith('+') and not l.startswith('+++'))
removed = [l for l in patch.splitlines() if l.startswith('-') and not l.startswith('---')]
check(not removed, 'adds lines only, so Wine without WINE_IOS builds as before')
check(added.count('#ifdef WINE_IOS') == added.count('#endif') == 6, 'every addition sits behind WINE_IOS')
check('getenv( "MADEIRA_CONNECT_TIMEOUT_MS" )' in added, 'reads MADEIRA_CONNECT_TIMEOUT_MS')
check('if (sock->state == SOCK_CONNECTING && is_tcp_socket( sock ))\n            madeira_connect_timeout_start( sock );'
      in added, 'arms the timer for TCP sockets only, as they enter SOCK_CONNECTING')
check('if (sock->state != SOCK_CONNECTING) madeira_connect_timeout_cancel( sock );' in added,
      'cancels it when the connect completes or fails')
check(re.search(r'sock->connect_timeout = NULL;\n    sock->connect_start = 0;', added) is not None,
      'create_socket starts every socket without a timer')

hunks = patch.split('\n@@ ')
destroy = [h for h in hunks if 'assert( obj->ops == &sock_ops );' in h and 'madeira_connect_timeout_cancel' in h]
check(len(destroy) == 1, 'sock_destroy cancels a pending timer, so it never fires on a freed socket')

build = (root / 'build/wineserver/build.sh').read_text(encoding='utf-8')
apply_at = build.find('bash "$REPO_ROOT/build/wine-patches/apply.sh"')
check(0 <= apply_at < build.find('compile_one()'), 'build/wineserver/build.sh applies the wine patches before compiling')
readme = (patches / 'README.md').read_text(encoding='utf-8')
check(f'`{patch_path.name}`' in readme, 'the README lists the patch')

app = (root / 'app/Madeira/ContentView.swift').read_text(encoding='utf-8')
dock = app.find('setenv("MADEIRA_CONNECT_TIMEOUT_MS", "10000", 1)')
check(dock > app.find('DockInstallers.prepare(game'), 'Madeira Dock sessions set 10000 ms')
catalog = (root / 'app/Madeira/ConfigCatalog.generated.swift').read_text(encoding='utf-8')
check('key: "env.MADEIRA_CONNECT_TIMEOUT_MS"' in catalog, 'the config catalog lists the switch')
guide = (root / 'app/Madeira/Give-to-Claude-with-log-and-cfg.txt').read_text(encoding='utf-8')
check('[srv-conn-timeout]' in guide and 'env.MADEIRA_CONNECT_TIMEOUT_MS' in guide,
      'the help guide names the log tag and the switch')

FAKES = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#ifndef ETIMEDOUT
#define ETIMEDOUT 60
#endif
#define POLLERR 0x008
#define WS_AF_INET 2
#define WS_AF_INET6 23
#define AFD_POLL_BIT_CONNECT_ERR 4
#define AFD_POLL_BIT_COUNT 10
#define ntohs(x) ((unsigned short)((((x) & 0xff) << 8) | (((x) >> 8) & 0xff)))
typedef long long timeout_t;
typedef void (*timeout_callback)( void *private );
struct timeout_user { timeout_t when; timeout_callback func; void *private; int live; };
static struct timeout_user users[16];
static int nusers, live_users;
static timeout_t current_time = 1000000000;
static struct timeout_user *add_timeout_user( timeout_t when, timeout_callback func, void *private )
{
    struct timeout_user *u = &users[nusers++];
    u->when = when; u->func = func; u->private = private; u->live = 1; live_users++;
    return u;
}
static void remove_timeout_user( struct timeout_user *u ) { if (u->live) { u->live = 0; live_users--; } }
static void fire( struct timeout_user *u ) { if (u->live) { u->live = 0; live_users--; u->func( u->private ); } }
enum connection_state { SOCK_LISTENING, SOCK_UNCONNECTED, SOCK_CONNECTING, SOCK_CONNECTED, SOCK_CONNECTIONLESS };
struct fd { int unused; };
struct sock
{
    struct fd *fd;
    enum connection_state state;
    int errors[AFD_POLL_BIT_COUNT];
    union {
        struct { unsigned short sa_family; } addr;
        struct { unsigned short sin_family; unsigned short sin_port; } in;
        struct { unsigned short sin6_family; unsigned short sin6_port; } in6;
    } peer_addr;
    struct timeout_user *connect_timeout;
    timeout_t connect_start;
};
static int polls, last_event;
static void sock_poll_event( struct fd *fd, int event ) { (void)fd; polls++; last_event = event; }
'''

DRIVER = r'''
#define EXPECT(c) do { if (!(c)) { printf("line %d: %s\n", __LINE__, #c); return 1; } } while (0)
int main( int argc, char **argv )
{
    struct fd fd;
    struct sock s;
    long want = argc > 1 ? strtol( argv[1], NULL, 10 ) : 0;

    memset( &s, 0, sizeof(s) );
    s.fd = &fd;
    s.state = SOCK_CONNECTING;
    s.peer_addr.in.sin_family = WS_AF_INET;
    s.peer_addr.in.sin_port = ntohs( 80 );

    madeira_connect_timeout_start( &s );
    if (!want)
    {
        EXPECT( !s.connect_timeout && !nusers );
        printf( "ok\n" );
        return 0;
    }
    EXPECT( s.connect_timeout && s.connect_timeout->when == -(timeout_t)want * 10000 );

    /* Fires while the socket is still connecting: the kernel's failure path. */
    current_time += (timeout_t)want * 10000;
    fire( s.connect_timeout );
    EXPECT( !s.connect_timeout && polls == 1 && last_event == POLLERR );
    EXPECT( s.errors[AFD_POLL_BIT_CONNECT_ERR] == ETIMEDOUT );

    /* Fires after the connect finished: nothing. */
    memset( s.errors, 0, sizeof(s.errors) );
    s.state = SOCK_CONNECTING;
    madeira_connect_timeout_start( &s );
    s.state = SOCK_CONNECTED;
    fire( s.connect_timeout );
    EXPECT( polls == 1 && !s.errors[AFD_POLL_BIT_CONNECT_ERR] && !s.connect_timeout );

    /* A restart replaces the first timer; a cancel removes it. */
    s.state = SOCK_CONNECTING;
    madeira_connect_timeout_start( &s );
    madeira_connect_timeout_start( &s );
    EXPECT( live_users == 1 );
    madeira_connect_timeout_cancel( &s );
    EXPECT( live_users == 0 && !s.connect_timeout );
    madeira_connect_timeout_cancel( &s );

    /* A socket without its fd any more is left alone. */
    madeira_connect_timeout_start( &s );
    s.fd = NULL;
    fire( s.connect_timeout );
    EXPECT( polls == 1 );
    printf( "ok\n" );
    return 0;
}
'''


def run_helpers(folder, source):
    start = source.index('#ifdef WINE_IOS\n/* madeira: a bound on how long a TCP connect may stay pending.')
    end = source.index('#endif\n', start) + len('#endif\n')
    src = folder / 'connect_timeout.c'
    src.write_text(FAKES + '#define WINE_IOS 1\n' + source[start:end] + DRIVER, encoding='utf-8')
    cc = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
    if not cc:
        print('SKIP: no C compiler, the helpers were not run')
        return
    exe = folder / 'connect_timeout.exe'
    flags = ['-std=c99', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    built = subprocess.run([cc, *flags, str(src), '-o', str(exe)], capture_output=True, text=True)
    check(built.returncode == 0, 'the patched helpers compile' + ('' if built.returncode == 0 else ':\n' + built.stderr))
    if built.returncode:
        return
    for value, want in [(None, 0), ('0', 0), ('999', 0), ('120001', 0), ('ten', 0), ('-5000', 0),
                        ('1000', 1000), ('10000', 10000), ('120000', 120000)]:
        env = dict(os.environ)
        env.pop('MADEIRA_CONNECT_TIMEOUT_MS', None)
        if value is not None:
            env['MADEIRA_CONNECT_TIMEOUT_MS'] = value
        r = subprocess.run([str(exe), str(want)], capture_output=True, text=True, env=env)
        out = r.stdout.strip().splitlines()
        check(r.returncode == 0 and out[-1:] == ['ok'],
              f'MADEIRA_CONNECT_TIMEOUT_MS={value}: ' + (f'{want} ms' if want else 'no bound') +
              ('' if r.returncode == 0 else ' (' + ' '.join(out) + ')'))
        if want:
            check(any(f'[srv-conn-timeout] a TCP connect pending {want} ms' in l for l in r.stderr.splitlines()) and
                  any('[srv-conn-timeout] dport=80 still connecting after' in l for l in r.stderr.splitlines()),
                  f'MADEIRA_CONNECT_TIMEOUT_MS={value}: logs the bound once and the timed-out connect')


wine = root / 'wine'
if not (wine / 'server/sock.c').exists() or not shutil.which('git'):
    print('SKIP: wine submodule not checked out, patch not applied or run')
else:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / 'wine'
        ok = True
        for p in sorted(patches.glob('*.patch')):
            for name in (l.split(' b/')[-1] for l in p.read_text(encoding='utf-8').splitlines()
                         if l.startswith('diff --git')):
                target = work / name
                if not target.exists():
                    pinned = subprocess.run(['git', 'show', 'HEAD:' + name], cwd=wine, capture_output=True)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(pinned.stdout)
            r = subprocess.run(['git', 'apply', str(p)], cwd=work, capture_output=True, text=True)
            if r.returncode != 0:
                print(r.stderr)
                ok = False
                break
        check(ok, 'every wine patch applies in order on the pinned wine')
        if ok:
            run_helpers(Path(tmp), (work / 'server/sock.c').read_text(encoding='utf-8'))

print(f'{failures} failure(s)')
sys.exit(1 if failures else 0)
