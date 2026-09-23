#!/usr/bin/env python3
"""Scan an ELF or a raw memory capture for inline `svc` instructions and name the syscall.

This is the tool behind one question: **is a libc-level hook even capable of seeing
this call?** Code that issues `svc #0` directly -- or through its own inline
`exit`/`kill`/`mprotect` table -- never enters libc, so `Interceptor.replace` on
`exit_group`/`kill`/`mprotect` cannot observe it and a userspace "block the exit"
strategy silently does nothing. That is the discriminator in
`references/detection-and-anti-analysis.md` between "the exit came from libc" and
"the exit bypassed libc": if the library that dies carries its own svc sites for
`exit`/`kill`, a libc hook is the wrong instrument.

It is also the sanity check for the *other* direction: a library with **no** svc
sites for the termination syscalls is evidence that a libc-level hook can work, so a
missing event is a finding about the hook rather than about the target.

How the syscall number is recovered, and why it is a heuristic:

- arm64 loads the number in `x8`, almost always as `movz x8, #imm` (or `mov` to x8,
  which assembles to the same), immediately before the `svc`. The scan looks back a
  short BOUNDED window for the nearest register-writing instruction that targets x8,
  and resolves the common immediate forms (`movz`, `mov` alias, `orr x8, xzr, #imm`).
  A number computed at runtime, or loaded from a table, will not resolve -- those
  sites are reported as `nr=?` with the raw instruction that wrote x8, because
  "I cannot read this one" is a different statement from "this is not a syscall".
- arm (32-bit Thumb/A32) uses `r7` and a `svc` with an 8-bit immediate; the same
  bounded lookback applies.

This script **finds and names**; it does not decide intent. A library full of
`svc` sites that are all `futex`/`read` is ordinary libc-free code, not evasion.
Read the histogram, not the total.

Usage:
    python svc_scan.py libfoo.so
    python svc_scan.py /data/local/tmp/libjiagu_a64.so --json
    python svc_scan.py linker64 --arch arm64 --follow-exec
    python svc_scan.py region.bin --raw --arch arm64 --base 0x7a12340000

Exit codes: 0 = scan completed (hits or not), 1 = the input could not be read or the
architecture could not be determined. A scan that finds zero svc sites exits 0: that
is a result, not an error.
"""
import argparse
import json
import os
import struct
import sys

try:
    from capstone import Cs, CS_ARCH_ARM64, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_THUMB
    from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_REG
    from capstone.arm import ARM_OP_IMM, ARM_OP_REG
except ImportError:  # pragma: no cover - dependency message is the point
    sys.stderr.write(
        "capstone is required: python -m pip install capstone\n"
        "(this repository's other native scripts use it as well)\n")
    raise SystemExit(1)

# arm64 syscall numbers (linux, asm-generic). Only the ones worth naming: a scan
# report that names `futex` is more useful than one that prints 98.
ARM64_SYSCALLS = {
    56: "openat", 57: "close", 61: "getdents64", 62: "lseek", 63: "read",
    64: "write", 66: "writev", 78: "readlinkat", 79: "newfstatat", 80: "fstat",
    93: "exit", 94: "exit_group", 98: "futex", 99: "set_robust_list",
    101: "nanosleep", 113: "clock_gettime", 117: "ptrace", 129: "kill",
    130: "tkill", 131: "tgkill", 134: "rt_sigaction", 135: "rt_sigprocmask",
    160: "uname", 167: "prctl", 169: "gettimeofday", 172: "getpid",
    173: "getppid", 174: "getuid", 175: "geteuid", 178: "gettid", 214: "brk",
    215: "munmap", 216: "mremap", 220: "clone", 221: "execve", 222: "mmap",
    226: "mprotect", 260: "wait4", 273: "set_robust_list", 276: "renameat",
    278: "getrandom", 280: "utimensat", 291: "statx",
}

# The three groups that decide whether a userspace strategy is even applicable.
TERMINATION = {93, 94, 129, 130, 131}          # exit / exit_group / kill / tkill / tgkill
EVASION = {117, 167, 226, 222, 220}            # ptrace / prctl / mprotect / mmap / clone
DISCOVERY = {56, 57, 61, 62, 63, 64, 78, 79}   # openat / close / getdents64 / read...

# arm (32-bit) numbers, for the armeabi-v7a half of a dual-ABI APK.
ARM_SYSCALLS = {
    1: "exit", 3: "read", 4: "write", 5: "open", 6: "close", 20: "getpid",
    37: "kill", 38: "rename", 45: "brk", 54: "ioctl", 91: "munmap",
    120: "clone", 122: "uname", 125: "mprotect", 192: "mmap2", 199: "getuid",
    224: "gettid", 238: "tkill", 240: "futex", 248: "exit_group", 268: "statfs64",
}

# How far back to look for the instruction that loads the syscall number. Real
# compilers put it 1-3 instructions before the svc (sometimes with an intermediate
# `orr`/`and`); 8 words is generous without letting an unrelated x8 write leak in.
LOOKBACK = 8


def parse_elf_segments(data):
    """Return [(file_offset, vaddr, filesz, exec_flag)] for PT_LOAD, or None if not ELF.

    Hand-walked rather than delegated to pyelftools on purpose: this kit's other
    native scripts do the same, because a target's section header table is exactly
    the thing a hardened binary forges (see `references/native-tamper-and-suicide.md`).

    Note the pf_x handling: it is *reported*, not used as a filter. Measured on a
    real device, the ROM's own `libc.so` and `linker64` both carry `pf_x == 0` on
    every PT_LOAD — so filtering to executable segments silently drops every hit on
    this platform. The flag is printed per segment instead, so a run that mixes code
    and data is visible rather than wrong.
    """
    if len(data) < 64 or data[:4] != b"\x7fELF":
        return None
    is64 = data[4] == 2
    little = data[5] == 1
    if not little:
        return None  # no big-endian Android target in this kit's scope
    if is64:
        e_phoff, = struct.unpack_from("<Q", data, 0x20)
        e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x36)
        segs = []
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            if off + 56 > len(data):
                break
            # Elf64_Phdr: p_type u32, p_flags u32, p_offset u64 ...
            p_type, p_flags = struct.unpack_from("<II", data, off)
            p_offset, p_vaddr, _p_paddr, p_filesz = struct.unpack_from("<QQQQ", data, off + 8)
            if p_type == 1:  # PT_LOAD
                segs.append((p_offset, p_vaddr, p_filesz, p_flags))
        return segs
    e_phoff, = struct.unpack_from("<I", data, 0x1C)
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x2A)
    segs = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        if off + 32 > len(data):
            break
        p_type = struct.unpack_from("<I", data, off)[0]
        p_offset, p_vaddr, _p_paddr, p_filesz, p_flags = struct.unpack_from("<IIIII", data, off + 4)
        if p_type == 1:
            segs.append((p_offset, p_vaddr, p_filesz, p_flags))
    return segs


def guess_arch(data):
    """'arm64' | 'arm' from the ELF header, else None."""
    if len(data) >= 20 and data[:4] == b"\x7fELF":
        machine = struct.unpack_from("<H", data, 18)[0]
        return {0xB7: "arm64", 0x28: "arm"}.get(machine)
    return None


def make_disassembler(arch, thumb):
    if arch == "arm64":
        md = Cs(CS_ARCH_ARM64, 0)  # little-endian is the default
    else:
        mode = CS_MODE_THUMB if thumb else CS_MODE_ARM
        md = Cs(CS_ARCH_ARM, mode)
    # operand types (register vs immediate) are only populated in detail mode;
    # without it capstone raises CS_ERR_DETAIL on `insn.operands`.
    md.detail = True
    return md


def load_immediate_into(md, arch, code, svc_off, reg_name):
    """Walk back from an svc and return (value, mnemonic, off) for the write to reg_name.

    Best-effort by design: a number assembled at runtime returns (None, last_write, off)
    so the site is still reported, with the instruction that produced the unknown.
    """
    start = max(0, svc_off - LOOKBACK * 4)
    window = code[start:svc_off]
    last_write = None
    for insn in md.disasm(window, start):
        ops = insn.operands
        if not ops:
            continue
        op0 = ops[0]
        if op0.type != (ARM64_OP_REG if arch == "arm64" else ARM_OP_REG):
            continue
        try:
            written = insn.reg_name(op0.reg)
        except Exception:  # pragma: no cover - capstone version drift
            continue
        if written != reg_name:
            continue
        last_write = (insn.mnemonic, insn.op_str, insn.address)
        # `movz x8, #93` / `mov x8, #93` / `orr x8, xzr, #93`
        for op in ops[1:]:
            if op.type == (ARM64_OP_IMM if arch == "arm64" else ARM_OP_IMM):
                return op.imm, insn.mnemonic, insn.address
    return None, last_write, None


def disasm_context(data, md, arch, off, before=4, after=2):
    """Disassemble a window around a site so a false positive can be told from a real one.

    The reason this exists: a byte scan for `svc` matches inside data. Measured on a
    real shell library, 21 "svc sites" turned out to sit in the middle of `scvtf` /
    `orr v25.4s` / `udf` byte soup with no call sequence anywhere near them — data,
    not a syscall instruction. A site whose neighbours are `udf` or NEON arithmetic
    is a byte-scan artefact; a real one sits at the end of a short sequence that
    loads a value into the syscall-number register.
    """
    lo = max(0, off - before * 4)
    hi = min(len(data), off + 4 + after * 4)
    out = []
    for insn in md.disasm(data[lo:hi], lo):
        out.append("%s0x%x: %s %s" % ("-> " if insn.address == off else "   ",
                                      insn.address, insn.mnemonic, insn.op_str))
    return out


def looks_like_data(md, data, arch, off, before=6):
    """True when the bytes just before the site are not a plausible instruction stream.

    Heuristic, and deliberately conservative: it only fires on the shapes that were
    actually observed around byte-scan hits inside data (`udf`, `scvtf` with a wide
    shift, NEON `mul v..s[..]`, an `orr w.., w.., #0xfffff...` mask). It never removes
    a site -- it labels it, because "this is a real svc I do not understand" and
    "this is not an instruction" need different follow-ups.
    """
    if off < 16:
        return False
    window = data[max(0, off - before * 4):off]
    for insn in md.disasm(window, max(0, off - before * 4)):
        m = insn.mnemonic
        if m == "udf":
            return True
        if m in ("scvtf", "ucvtf") and "#0x1" in insn.op_str:
            return True
        if m in ("mul", "mla") and "s[" in insn.op_str:
            return True
        if m == "orr" and "#0xfffff" in insn.op_str:
            return True
    return False


def scan_blob(data, arch, base, thumb=False, segs=None, code_only=False, context=0):
    """Return (sites, per_segment_counts). `segs` limits the scan to PT_LOAD regions."""
    md = make_disassembler(arch, thumb)
    reg = "x8" if arch == "arm64" else "r7"
    table = ARM64_SYSCALLS if arch == "arm64" else ARM_SYSCALLS

    ranges = []
    if segs:
        for idx, (p_offset, p_vaddr, p_filesz, p_flags) in enumerate(segs):
            if code_only and not (p_flags & 1):
                continue
            end = min(len(data), p_offset + p_filesz)
            if end > p_offset:
                ranges.append((p_offset, end, p_vaddr - p_offset, idx, p_flags))
    else:
        ranges.append((0, len(data), base, 0, None))

    sites = []
    per_segment = {}
    for lo, hi, vaddr_bias, idx, p_flags in ranges:
        # Word-aligned walk only: an unaligned resync over the whole file produces
        # garbage sites. Real svc sites sit on an instruction boundary, and the walk
        # is done per 4 bytes so a straddling pattern cannot hide one.
        n_here = 0
        off = lo + ((4 - lo % 4) % 4)
        while off + 4 <= hi:
            word = struct.unpack_from("<I", data, off)[0]
            is_svc = (word & 0xFFE0001F) == 0xD4000001 if arch == "arm64" else (
                (word & 0x0F000000) == 0x0F000000)
            if is_svc:
                imm = word & 0xFFFF if arch == "arm64" else word & 0xFF
                nr, mnemonic, woff = load_immediate_into(md, arch, data, off, reg)
                site = {
                    "offset": off,
                    "vaddr": vaddr_bias + off,
                    "svc_imm": imm,
                    "nr": nr,
                    "name": table.get(nr, "nr=%s" % nr) if nr is not None else None,
                    "writer": mnemonic,
                    "writer_off": woff,
                    "segment": idx,
                    "segment_exec": None if p_flags is None else bool(p_flags & 1),
                    "likely_data": looks_like_data(md, data, arch, off),
                }
                if context:
                    site["context"] = disasm_context(data, md, arch, off,
                                                     before=context, after=2)
                sites.append(site)
                n_here += 1
                if arch == "arm64":
                    off += 4
                    continue
            off += 4
        per_segment[idx] = (n_here, p_flags, lo, hi)
    return sites, per_segment


def group_of(site, arch):
    nr = site.get("nr")
    if nr is None:
        return "unresolved"
    table = TERMINATION if arch == "arm64" else {1, 37, 238, 248}
    evasion = EVASION if arch == "arm64" else {117, 125, 120, 167}
    discovery = DISCOVERY if arch == "arm64" else {3, 4, 5, 6, 78, 79}
    if nr in table:
        return "termination"
    if nr in evasion:
        return "evasion"
    if nr in discovery:
        return "discovery"
    return "other"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Scan an ELF (or raw capture) for inline `svc` sites and name the "
                    "syscall each one issues. Use it to decide whether a libc-level hook "
                    "can see a call at all: code that issues `svc #0` itself never enters "
                    "libc, so `Interceptor.replace` on exit/kill/mprotect cannot observe it.")
    ap.add_argument("path", help="ELF file (scanned via PT_LOAD when possible) or raw capture")
    ap.add_argument("--arch", choices=["arm64", "arm", "auto"], default="auto",
                    help="instruction set; 'auto' reads the ELF header (default), and is "
                         "required to be explicit for a raw capture")
    ap.add_argument("--thumb", action="store_true",
                    help="arm only: decode as Thumb rather than A32")
    ap.add_argument("--raw", action="store_true",
                    help="treat the input as an opaque memory capture even if it has ELF magic")
    ap.add_argument("--base", default="0x0",
                    help="load address for a raw capture, so --json reports real vaddrs")
    ap.add_argument("--json", action="store_true", help="emit the site list as JSON")
    ap.add_argument("--code-only", action="store_true",
                    help="scan only PT_LOAD segments whose pf_x is set. Off by default: "
                         "measured device libc/linker64 carry pf_x=0 on every segment, so "
                         "this flag can drop every hit on a real ROM. Use it to shrink a "
                         "noisy run, and check the per-segment counts it reports.")
    ap.add_argument("--context", type=int, default=0, metavar="N",
                    help="disassemble N instructions before each site and print them; the "
                         "way to tell a real svc from a byte-scan hit inside data")
    ap.add_argument("--max-sites", type=int, default=0, metavar="N",
                    help="stop after N sites (0 = no limit); for a hostile blob where the "
                         "point is the histogram, not every offset")
    args = ap.parse_args(argv)

    try:
        with open(args.path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        sys.stderr.write("cannot read %s: %s\n" % (args.path, exc))
        return 1

    segs = None
    arch = args.arch
    if not args.raw:
        if data[:4] != b"\x7fELF":
            sys.stderr.write(
                "%s is not an ELF; pass --raw --arch <arm64|arm> to scan it as a capture\n"
                % args.path)
            return 1
        detected = guess_arch(data)
        if args.arch == "auto":
            if detected is None:
                sys.stderr.write("cannot determine the architecture from the ELF header; "
                                 "pass --arch explicitly\n")
                return 1
            arch = detected
        segs = parse_elf_segments(data)
    elif args.arch == "auto":
        sys.stderr.write("--raw needs an explicit --arch (there is no header to read)\n")
        return 1

    base = int(args.base, 0)
    sites, per_segment = scan_blob(data, arch, base, thumb=args.thumb, segs=segs,
                                   code_only=args.code_only, context=args.context)
    truncated = False
    if args.max_sites and len(sites) > args.max_sites:
        sites = sites[:args.max_sites]
        truncated = True

    by_group = {}
    by_name = {}
    n_data = 0
    n_noload = 0
    for s in sites:
        g = group_of(s, arch)
        by_group[g] = by_group.get(g, 0) + 1
        key = s["name"] or "unresolved"
        by_name[key] = by_name.get(key, 0) + 1
        if s.get("likely_data"):
            n_data += 1
        if s["writer"] is None:
            n_noload += 1

    if args.json:
        print(json.dumps({
            "path": os.path.abspath(args.path),
            "arch": arch,
            "code_only": args.code_only,
            "segments": [
                {"index": i, "exec": None if fl is None else bool(fl & 1),
                 "file_range": [lo, hi], "svc_sites": c}
                for i, (c, fl, lo, hi) in sorted(per_segment.items())
            ],
            "sites": sites,
            "by_group": by_group,
            "by_name": by_name,
            "likely_data_sites": n_data,
            "no_load_sites": n_noload,
            "truncated": truncated,
        }, indent=2))
        return 0

    print("== svc scan: %s (%s) ==" % (os.path.basename(args.path), arch))
    if per_segment and segs:
        print("segments (pf_x is reported from the program header, not used as a filter):")
        for i, (c, fl, lo, hi) in sorted(per_segment.items()):
            print("  seg%-2d off=0x%-8x size=0x%-8x pf_x=%d   svc=%d"
                  % (i, lo, hi - lo, (fl & 1) if fl is not None else -1, c))
        skipped = len(segs) - len(per_segment)
        if skipped:
            print("  (%d PT_LOAD segment(s) skipped by --code-only)" % skipped)
    print("sites: %d%s" % (len(sites), "  (truncated by --max-sites)" if truncated else ""))
    if not sites:
        print("no inline `svc` instruction found in the scanned ranges.")
        print("reading: this file does not issue syscalls directly in the scanned bytes -- "
              "for the termination group that means a libc-level hook is not structurally "
              "excluded (see references/detection-and-anti-analysis.md).")
        return 0

    fmt = "  %-10s %-10s %-6s %-12s %-5s %s"
    print(fmt % ("offset", "vaddr", "svc#", "syscall", "nr", "note"))
    for s in sites:
        note = []
        if s.get("likely_data"):
            note.append("neighbours are udf/NEON soup")
        if s["writer"] is None:
            note.append("no syscall-number load nearby")
        print(fmt % ("0x%x" % s["offset"], "0x%x" % s["vaddr"], s["svc_imm"],
                     s["name"] or "?", s["nr"] if s["nr"] is not None else "?",
                     "; ".join(note)))
        for line in s.get("context", ()):
            print("        %s" % line)

    print("\nhistogram by group: %s" % ", ".join(
        "%s=%d" % (k, by_group[k]) for k in sorted(by_group)))
    print("histogram by syscall: %s" % ", ".join(
        "%s=%d" % (k, by_name[k]) for k in sorted(by_name, key=lambda x: -by_name[x])[:12]))

    term = by_group.get("termination", 0)
    unresolved = by_group.get("unresolved", 0)
    print("\nreading:")
    if n_data or n_noload:
        print("  %d site(s) carry a data-artefact flag (%d udf/NEON neighbours, %d with no "
              "syscall-number load nearby). Both mean `likely not an instruction`: verify "
              "with --context before treating any of them as a call, because a byte scan "
              "for `svc` matches inside data." % (max(n_data, n_noload), n_data, n_noload))
    if term:
        print("  %d termination site(s) (exit/exit_group/kill/tkill/tgkill): a libc-level "
              "hook CANNOT observe these. Prefer a static NOP at the site over an "
              "Interceptor.replace on libc, and check the site's own writer instruction "
              "before editing it." % term)
    else:
        print("  no termination site: your libc-level hook is not structurally excluded, so "
              "a missing exit event is a finding about the hook, not about the target.")
    if unresolved:
        print("  %d site(s) whose number is not a literal: either computed at runtime "
              "(`mov x8, x0`, `sxtw x8, w1`) or hidden behind a table. Report them as "
              "unknown -- do not assume a syscall number. A module whose svc sites are "
              "*all* unresolved is consistent with a deliberate indirection layer, but "
              "this scan cannot prove that; say `unresolved` in the record." % unresolved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
