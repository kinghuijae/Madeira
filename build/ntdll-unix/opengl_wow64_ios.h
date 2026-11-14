/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Keep this narrow iOS fix in the native build, without requiring the optional
 * OpenGL renderer/thunk patch to be applied to the Wine submodule.
 */
#ifndef MADEIRA_OPENGL_WOW64_IOS_H
#define MADEIRA_OPENGL_WOW64_IOS_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "unixlib.h"
#include "unix_private.h"

#if defined(WINE_IOS) && defined(_WIN64)
static inline TEB *madeira_gl_teb64( ULONG_PTR address, const char *caller )
{
    /* thread_attach receives an already translated outer pointer. Other GL
     * thunks pass an embedded PTR32. ios_wow_host_ptr resolves the calling
     * process's registry entry, including windows spilled into the CEF band. */
    TEB32 *teb32 = address > 0xffffffffu ? (TEB32 *)address : ios_wow_host_ptr( (ULONG)address );
    TEB *teb64 = (TEB *)((char *)teb32 + teb32->WowTebOffset);

    if (!strcmp( caller, "wow64_thread_attach" ))
        fprintf( stderr, "[opengl-wow] thread attach arg=%p teb32=%p teb64=%p B=%p\n",
                 (void *)address, teb32, teb64, (void *)ios_wow_host_base() );
    return teb64;
}

#undef get_teb64
#define get_teb64(teb32) madeira_gl_teb64( (ULONG_PTR)(teb32), __func__ )
#endif
#endif
