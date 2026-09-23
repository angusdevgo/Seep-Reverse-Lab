#ifndef R2_CONFIGURE_H
#define R2_CONFIGURE_H

#ifdef __cplusplus
extern "C" {
#endif

#include "r_version.h"

#define WANT_DEBUGSTUFF 1
#define R_CHECKS_LEVEL 1
#define R_CRITICAL_ENABLED 0
#define DEBUGGER 1
#define HAVE_DECL_ADDR_NO_RANDOMIZE 0
#ifdef __EMSCRIPTEN__
#define HAVE_ARC4RANDOM_UNIFORM 0
#else
#define HAVE_ARC4RANDOM_UNIFORM 0
#endif
#define HAVE_EXPLICIT_BZERO 0
#define HAVE_EXPLICIT_MEMSET 0
#define HAVE_CLOCK_NANOSLEEP 0
#define HAVE_SIGACTION 0
#define WANT_THREADS 1
#define WANT_CAPSTONE 1
#define HAVE_LINUX_CAN_H 0
#define R2_USE_NEW_ABI 0
#define R2_USE_SQSH 0

#define R_BUILDSYSTEM "meson"
#if 0 == 1
#define R2_CSVERSION 4
#elif 0 == 1
#define R2_CSVERSION 6
#else
#define R2_CSVERSION 5
#endif

#define WITH_STATIC_THEMES False

#define HAVE_GPERF 0
#if (HAVE_GPERF) == 1
#define HAVE_GPERF 0
#else
#define HAVE_GPERF 0
#endif

#ifdef R_MESON_VERSION
#define R2_PREFIX "."
#define R2_ETCDIR "./etc"
#define R2_LIBDIR "lib"
#define R2_BINDIR "./bin"
#define R2_INCDIR "include\\libr"
#define R2_DATDIR "./share"
#define R2_WWWROOT "./share//www"
#define R2_PLUGINS "lib\\plugins"
#define R2_EXTRAS "lib\\extras"
#define R2_BINDINGS "lib\\bindings"
#define R2_DATDIR_R2 "share"
#define R2_SDB "share"
#define R2_ZIGNS "share\\zigns"
#define R2_THEMES "share\\cons"
#define R2_FORTUNES R_JOIN_3_PATHS ("./share", "doc", "radare2")
#define R2_FLAGS "share\\flag"
#define R2_HUD "share\\hud"
#else
#if R2__WINDOWS__ || _MSC_VER
#define R2_PREFIX "."
#define R2_ETCDIR "etc"
#define R2_BINDIR "bin"
#define R2_LIBDIR "lib"
#define R2_INCDIR "include\\libr"
#define R2_DATDIR "share"
#define R2_WWWROOT "www"
#define R2_PLUGINS "lib\\plugins"
#define R2_EXTRAS "lib\\extras"
#define R2_BINDINGS "lib\\bindings"
#else
#define R2_PREFIX "."
#define R2_ETCDIR "./etc"
#define R2_LIBDIR "lib"
#define R2_BINDIR "./bin"
#define R2_INCDIR "include\\libr/libr"
#define R2_DATDIR "./share"
#define R2_WWWROOT R2_DATDIR "/radare2/" R2_VERSION "/www"
#define R2_PLUGINS "lib/radare2/" R2_VERSION
#define R2_EXTRAS "lib/radare2-extras/" R2_VERSION
#define R2_BINDINGS "lib/radare2-bindings/" R2_VERSION
#endif
#define R2_DATDIR_R2        R_JOIN_2_PATHS ("share", "radare2")
#define R2_SDB              R_JOIN_3_PATHS ("share", "radare2", R2_VERSION)
#define R2_ZIGNS            R_JOIN_4_PATHS ("share", "radare2", R2_VERSION, "zigns")
#define R2_THEMES           R_JOIN_4_PATHS ("share", "radare2", R2_VERSION, "cons")
#define R2_FLAGS            R_JOIN_4_PATHS ("share", "radare2", R2_VERSION, "flag")
#define R2_FORTUNES         R_JOIN_3_PATHS ("share", "doc", "radare2")
#define R2_HUD              R_JOIN_4_PATHS ("share", "radare2", R2_VERSION, "hud")
#endif

#define R2_SDB_FCNSIGN      R_JOIN_2_PATHS (R2_SDB, "fcnsign")
#define R2_SDB_OPCODES      R_JOIN_2_PATHS (R2_SDB, "opcodes")
#define R2_SDB_MAGIC        R_JOIN_2_PATHS (R2_SDB, "magic")
#define R2_SDB_FORMAT       R_JOIN_2_PATHS (R2_SDB, "format")

#define R2_GLOBAL_RC        R_JOIN_2_PATHS (R2_DATDIR_R2, "radare2rc")

#define HAVE_LIB_MAGIC 0
#define USE_LIB_MAGIC 0
#define HAVE_LIB_XXHASH 0
#define USE_LIB_XXHASH 0

#ifndef HAVE_LIB_SSL
#define HAVE_LIB_SSL 0
#endif

#ifndef WANT_SSL_CRYPTO
#define WANT_SSL_CRYPTO 0
#endif

#define HAVE_LIBUV 0

#if __MINGW32__
#define HAVE_PTRACE 0
#else
#define HAVE_PTRACE 0
#endif

#define USE_PTRACE_WRAP 0
#define HAVE_FORK 1
#define WANT_DYLINK 1
#define WITH_GPL 1

#if __APPLE__ && __POWERPC__
#define HAVE_JEMALLOC 0
#else
#define HAVE_JEMALLOC 0
#endif

#ifdef __cplusplus
}
#endif

#endif
