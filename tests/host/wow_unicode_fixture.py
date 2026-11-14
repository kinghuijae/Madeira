"""Compile the real Wine UTF conversions and case table in standalone host checks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def unicode_support():
    locale = (ROOT / 'wine/dlls/ntdll/locale_private.h').read_text(encoding='utf-8')
    env = (ROOT / 'build/ntdll-unix/env_ios.c').read_text(encoding='utf-8')
    private = (ROOT / 'wine/dlls/ntdll/unix/unix_private.h').read_text(encoding='utf-8')
    unixlib = (ROOT / 'wine/include/wine/unixlib.h').read_text(encoding='utf-8')
    result = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t WCHAR, USHORT;
typedef uint32_t DWORD;
typedef int NTSTATUS;
#define WINAPI
#define STATUS_SUCCESS 0
#define STATUS_BUFFER_TOO_SMALL ((NTSTATUS)0xc0000023)
#define STATUS_SOME_NOT_MAPPED 0x107
#define IS_HIGH_SURROGATE(c) ((c) >= 0xd800 && (c) <= 0xdbff)
#define IS_LOW_SURROGATE(c) ((c) >= 0xdc00 && (c) <= 0xdfff)
static USHORT *uctable;
'''
    for signature in ['static inline int get_utf16(', 'static inline unsigned int decode_utf8_char(',
                      'static inline NTSTATUS utf8_wcstombs_size(', 'static inline NTSTATUS utf8_mbstowcs_size(',
                      'static inline NTSTATUS utf8_mbstowcs(', 'static inline NTSTATUS utf8_wcstombs(']:
        result += function(locale, signature) + '\n'
    for signature in ['NTSTATUS WINAPI RtlUTF8ToUnicodeN(', 'NTSTATUS WINAPI RtlUnicodeToUTF8N(']:
        result += function(env, signature) + '\n'
    result += function(private, 'static inline WCHAR ntdll_towupper(') + '\n'
    result += function(unixlib, 'static inline size_t ntdll_wcslen(') + '\n#define wcslen ntdll_wcslen\n'
    result += r'''
static void init_case_table(const char *path)
{
    static USHORT data[32768];
    FILE *f = fopen(path, "rb");
    if (!f || !fread(data, 1, sizeof(data), f)) abort();
    fclose(f);
    uctable = data + 2;
}
'''
    return result
