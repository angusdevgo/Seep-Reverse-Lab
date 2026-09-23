#!/usr/bin/env python3
"""Validate a directory of dumped dex files: dedupe, structural checks, stub-body ratio.

A memory dump (frida-dexdump & co.) hands you a pile of images: duplicate copies of
one dex, SDK plugin dexes that were never in the APK, structurally broken fragments,
extraction-shell skeletons whose method bodies are stubbed, and -- if you are lucky --
the original. `references/recon.md` states the rule (dedupe by content hash, validate
structure before trusting); this script is the tool that rule was missing.

Per file it reports: size, sha256, dex version, checksum/signature verdicts
(`dexutil.verify_dex_header`), class count, method-body census (no-code / real /
trivial-stub / nop-erased / minimal-form / empty), the stub and emptied ratios that
flag an extraction-shell skeleton, and --find pattern hits across the string table.
Files are grouped by sha256 and the survivors are ranked: most likely original first.

**Read `emptied%`, not `stub%`, for the skeleton call.** The two differ, and the
difference is load-bearing: `stub%` counts only bodies left as a lone `return*`, while
`emptied%` also counts bodies wiped to nothing but nops. A shell that clears the slot
instead of writing a return scores `stub% = 0.0` on a fully emptied image — measured,
and it used to be ranked the *most likely original* because of it. `stub%` is also
bimodal in practice: it lands at the app's own baseline or at ~100 %, with no band in
between, and partial extraction (75 % of bodies removed) moves it by 0.2 points. Full
matrix and commands: `docs/tool-verification/EXTENSION-extraction-shell-bench.md`.

Exit code 0 unless nothing in the input parses as a dex at all (exit 1).

Examples:
    python dex_dump_validate.py dumps/ --find 'Lcom/example/app/'
    python dex_dump_validate.py dumps/ --find 'Lcom/stub/' --json > report.json
    python dex_dump_validate.py one_dumped.dex
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dexutil import OFFSETS, read_uleb, u16, u32, verify_dex_header  # noqa: E402

MAGIC = b"dex\n"
KNOWN_VERSIONS = {b"035", b"036", b"037", b"038", b"039"}
RETURN_OPS = {0x0E, 0x0F, 0x10, 0x11}  # return-void / return / return-wide / return-object


def classify_body(data, code_off):
    """Classify one code_item's instruction stream.

    Returns one of 'empty' | 'stub' | 'erased' | 'malformed' | 'real'.

    'stub'      -- skip plain nop units (0x0000) and exactly one return* remains.
                   That is what an extraction shell leaves behind when it defers
                   decryption to first invocation, and what a repair fixture writes
                   when mimicking one.
    'erased'    -- insns_size > 0 but every unit is 0x0000. Measured on a fixture:
                   a body emptied by nop fill lands here, and reporting it as 'real'
                   (the pre-2026-09 behaviour) inverted the ranking, because a fully
                   nop-filled skeleton scored stub% = 0.0 and was named the most
                   likely original. A real compiler never emits a whole body of
                   nops, so this is skeleton evidence, not code.
    'minimal'   -- a body truncated to `const/4 vR, #0; return vR` and nop-padded,
                   with a non-zero high byte on the return. This is a *legal* minimal
                   non-void body, not a malformed one -- and it is a skeleton shape
                   the stub detector is blind to by design. Counted separately so the
                   blind spot is visible in the report instead of hiding inside
                   'real'. Measured: a fixture with all 5,061 bodies cut to this form
                   reports stub% = 1.9%, the same as its untouched control.
    'real'      -- anything else, including a body of a single non-return unit.

    A two-unit `const/4 v0, #0; return v0` is deliberately **not** a stub: it is what
    a *legal* minimal body looks like, and treating it as skeleton evidence would
    make every tiny accessor a false positive. That asymmetry is the detector's
    designed boundary, and it is measured in
    `docs/tool-verification/EXTENSION-extraction-shell-bench.md`.
    """
    insns_size = u32(data, code_off + 12)
    if insns_size == 0:
        return "empty"
    base = code_off + 16
    meaningful = 0
    last_unit = 0
    for k in range(insns_size):
        unit = u16(data, base + k * 2)
        if unit == 0x0000:            # plain nop / cleared slot
            continue
        meaningful += 1
        last_unit = unit
        if meaningful > 2:
            return "real"             # three units can never be a stub or a minimal
    if meaningful == 0:
        return "erased"               # every unit was 0x0000
    if meaningful == 1:
        op = last_unit & 0xFF         # first byte holds the opcode for 10x/11x
        if op == 0x0E:
            # 10x return-void has no operand: `0xNN0E` with NN != 0 is `return vNN`,
            # i.e. a non-void return wearing a return-void opcode -- minimal form.
            return "stub" if last_unit == 0x000E else "minimal"
        if op in (0x0F, 0x10, 0x11):  # 11x returns: high byte is the register
            return "stub"
        return "real"
    # meaningful == 2: legal minimal body only when it is `const/4 vR,#0; return* vR`
    first_unit = 0
    for k in range(insns_size):
        if u16(data, base + k * 2):
            first_unit = u16(data, base + k * 2)
            break
    if (first_unit & 0xFF) == 0x12 and (last_unit & 0xFF) in (0x0E, 0x0F, 0x10, 0x11):
        return "minimal"
    return "real"


def walk_methods(data, header):
    """Yield code_off for every method defined in class_defs (0 = abstract/native)."""
    for i in range(header["class_defs_size"]):
        cd = header["class_defs_off"] + i * 32
        p = u32(data, cd + 24)                       # class_data_off
        if p == 0:
            continue
        static_f, p = read_uleb(data, p)
        inst_f, p = read_uleb(data, p)
        direct_m, p = read_uleb(data, p)
        virtual_m, p = read_uleb(data, p)
        for _ in range(static_f + inst_f):
            _, p = read_uleb(data, p)                # field_idx_diff
            _, p = read_uleb(data, p)                # access_flags
        for _ in range(direct_m + virtual_m):
            _, p = read_uleb(data, p)                # method_idx_diff
            _, p = read_uleb(data, p)                # access_flags
            code_off, p = read_uleb(data, p)
            yield code_off


def string_find_hits(data, header, patterns):
    """Count string-table entries containing each pattern."""
    hits = {}
    for pat in patterns:
        pat_bytes = pat.encode("utf-8", "surrogateescape")
        n = 0
        for idx in range(header["string_ids_size"]):
            p = u32(data, header["string_ids_off"] + idx * 4)
            try:
                _, p = read_uleb(data, p)
                end = data.index(b"\x00", p)
            except Exception:
                continue
            if pat_bytes in data[p:end]:
                n += 1
        hits[pat] = n
    return hits


def profile_dex(path, patterns, trim=False):
    """Build the report dict for one file. 'error' key marks a rejected image.

    With trim=True, an image whose header file_size is *shorter* than the file is
    accepted after cutting the tail: /proc/<pid>/mem dumps are page-aligned, so the
    recorded VMA range is always longer than the dex it holds (measured on a real
    root-side dump: 17/17 images overran by 68-3724 bytes). A file *shorter* than
    its own file_size is still rejected -- that is a truncated read, not padding.
    """
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        data = fh.read()
    prof = {
        "path": os.path.abspath(path),
        "name": name,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if len(data) < 112:
        prof["error"] = "too small (%d B) to carry a dex header" % len(data)
        return prof
    if data[:4] != MAGIC:
        prof["error"] = "magic=%r" % data[:4]
        return prof
    version = data[4:7]
    prof["version"] = version.decode("ascii", "replace")
    if version not in KNOWN_VERSIONS:
        prof["error"] = "unknown version %r" % version
        return prof

    header = {k: u32(data, v) for k, v in OFFSETS.items()}
    if header["file_size"] != len(data):
        if trim and 0 < header["file_size"] < len(data):
            prof["trimmed_from"] = len(data)
            prof["trimmed_to"] = header["file_size"]
            data = data[: header["file_size"]]
            prof["size"] = len(data)
        else:
            prof["error"] = "file_size=%d actual=%d" % (header["file_size"], len(data))
            return prof
    if header["header_size"] != 112:
        prof["error"] = "header_size=%d (expected 112)" % header["header_size"]
        return prof
    for key in ("string_ids_off", "type_ids_off", "proto_ids_off",
                "field_ids_off", "method_ids_off", "class_defs_off"):
        off = header[key]
        if off and not (0 < off < len(data)):
            prof["error"] = "%s=0x%x out of range" % (key, off)
            return prof

    cksum_ok, sig_ok = verify_dex_header(bytearray(data))
    prof["checksum_ok"] = cksum_ok
    prof["signature_ok"] = sig_ok

    prof["classes"] = header["class_defs_size"]
    no_code = with_code = stubs = empties = erased = minimal = 0
    try:
        for code_off in walk_methods(data, header):
            if code_off == 0:                       # abstract / native declaration
                no_code += 1
                continue
            if code_off + 16 > len(data):
                continue                            # broken pointer: skip, don't die
            with_code += 1
            kind = classify_body(data, code_off)
            if kind == "stub":
                stubs += 1
            elif kind == "empty":
                empties += 1
            elif kind == "erased":
                erased += 1
            elif kind == "minimal":
                minimal += 1
    except Exception as exc:                        # desynced class_data: keep counts
        prof["walk_error"] = str(exc)
    prof["methods_no_code"] = no_code
    prof["methods_with_code"] = with_code
    prof["bodies_real"] = with_code - stubs - empties - erased - minimal
    prof["bodies_stub"] = stubs
    prof["bodies_empty"] = empties
    prof["bodies_erased"] = erased
    prof["bodies_minimal"] = minimal
    # trivial_ratio keeps its original definition (return*-stub share of bodies) so
    # existing records stay comparable. The skeleton signal is the union of every
    # measured emptied shape; a body wiped to nothing at all must never score lower
    # than a body wiped to `return-void`, or the ranking inverts (see
    # docs/tool-verification/EXTENSION-extraction-shell-bench.md).
    prof["trivial_ratio"] = (stubs / with_code) if with_code else 0.0
    prof["emptied_ratio"] = ((stubs + erased) / with_code) if with_code else 0.0

    if patterns:
        try:
            prof["find_hits"] = string_find_hits(data, header, patterns)
        except Exception as exc:
            prof["find_hits_error"] = str(exc)
    return prof


def collect_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += [os.path.join(p, n) for n in sorted(os.listdir(p))
                    if n.endswith(".dex")]
        elif os.path.isfile(p):
            out.append(p)
        else:
            print("warning: %s is not a file or directory, skipped" % p,
                  file=sys.stderr)
    return out


def rank_key(prof):
    """Sort key: most-likely-original first.

    Both body signals are needed, in the right order, and each was measured to fail
    alone:

    * the `return*`-stub share alone let a **nop-filled** skeleton score 0.0 and be
      named the most likely original, because a wiped body counts as neither a stub
      nor real code;
    * `emptied_ratio` alone still failed, because it is **bimodal** -- it sits at the
      host app's own baseline or at ~100 %, with nothing in between. A dex with 25 %
      of its bodies emptied measures *below* its own untouched control, 1.7 % against
      1.9 %, so the sort pointed at a modified image and called it the original;
    * `minimal + erased` alone failed too, and in the opposite direction: a skeleton
      that writes a bare `return-void` into every body has minimal = erased = 0 and
      would sort first, despite `emptied%` = 100.

    So the key combines both, and the combination has to let *either* signal disqualify
    an image rather than letting them tie:

    * level 1 -- `emptied_ratio >= 0.5`. Nothing that is mostly emptied is a candidate,
      whatever else it scores. This is the level that evicts the two skeletons the
      plain counts cannot see: an image with a bare `return-void` in every body has
      minimal = erased = 0, so a pure-count key ranked it first.
    * level 2 -- `minimal + erased`, the skeleton-evidence count, low-first. This is
      what orders the **bimodal band**, where `emptied_ratio` cannot: the untouched
      control carries 82, and the count is monotone as bodies are removed (1299 /
      2524 / 3736 / 4946 at 25 / 50 / 75 / 100 %).
    * level 3 -- `emptied_ratio` low-first, to separate what is left.
    """
    return (1 if prof.get("emptied_ratio", prof["trivial_ratio"]) >= 0.5 else 0,
            prof.get("bodies_minimal", 0) + prof.get("bodies_erased", 0),
            prof.get("emptied_ratio", prof["trivial_ratio"]),
            0 if prof["checksum_ok"] else 1,
            0 if prof["signature_ok"] else 1,
            prof["name"])


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Dedupe and structurally validate a directory of dumped dex "
                    "files; rank which image is the most likely original.")
    ap.add_argument("path", nargs="+",
                    help="a directory of *.dex dumps, or individual .dex files")
    ap.add_argument("--find", action="append", default=[], metavar="PATTERN",
                    help="count string-table hits for PATTERN (repeatable), "
                         "e.g. --find 'Lcom/example/app/'")
    ap.add_argument("--json", action="store_true",
                    help="emit the full report as JSON (deterministic; redirect "
                         "to a file to keep it)")
    ap.add_argument("--trim", action="store_true",
                    help="accept page-aligned dumps: cut a tail longer than the header's "
                         "file_size (/proc/<pid>/mem exports always overrun; a file shorter "
                         "than its own file_size is still rejected)")
    args = ap.parse_args(argv)

    files = collect_files(args.path)
    if not files:
        print("no .dex files found in the given path(s)", file=sys.stderr)
        return 1

    profiles = [profile_dex(f, args.find, args.trim) for f in files]
    valid = [p for p in profiles if "error" not in p]
    ranking = sorted(valid, key=rank_key)

    if args.json:
        print(json.dumps({"profiles": profiles,
                          "ranking": [p["name"] for p in ranking]}, indent=2))
        return 0 if valid else 1

    # ---- human-readable report -------------------------------------------------
    print("== dex dump validation: %d file(s), %d parse, %d rejected =="
          % (len(profiles), len(valid), len(profiles) - len(valid)))
    fmt = "%-28s %9s  %-12s  %3s  %-7s %-7s %6s %6s %6s %7s %7s %7s"
    print(fmt % ("name", "size", "sha256[:12]", "ver", "cksum", "sig",
                 "class", "noco", "code", "stub%", "erased%", "emptied%"))
    for p in profiles:
        if "error" in p:
            print("%-28s %9s  %-12s  %3s  REJECTED: %s"
                  % (p["name"], p["size"], p["sha256"][:12],
                     p.get("version", "?"), p["error"]))
            continue
        print(fmt % (p["name"], p["size"], p["sha256"][:12], p["version"],
                     "ok" if p["checksum_ok"] else "BAD",
                     "ok" if p["signature_ok"] else "BAD",
                     p["classes"], p["methods_no_code"], p["methods_with_code"],
                     "%.1f%%" % (100.0 * p["trivial_ratio"]),
                     "%.1f%%" % (100.0 * (p["bodies_erased"] / p["methods_with_code"]
                                          if p["methods_with_code"] else 0.0)),
                     "%.1f%%" % (100.0 * p.get("emptied_ratio", 0.0))))
        if p.get("trimmed_from"):
            print("%-28s   trimmed %d -> %d B (page-aligned dump)"
                  % ("", p["trimmed_from"], p["trimmed_to"]))
        if p.get("walk_error"):
            print("%-28s   walk stopped early: %s" % ("", p["walk_error"]))
        if p.get("bodies_minimal"):
            print("%-28s   minimal-form bodies: %d (const/4+return truncation -- a "
                  "skeleton shape the stub%% column cannot see)"
                  % ("", p["bodies_minimal"]))
        for pat, n in sorted(p.get("find_hits", {}).items()):
            print("%-28s   find %-24s %d" % ("", pat, n))

    groups = {}
    for p in valid:
        groups.setdefault(p["sha256"], []).append(p["name"])
    dup_groups = {h: n for h, n in groups.items() if len(n) > 1}
    print("\ndedupe: %d unique image(s) among %d valid file(s)"
          % (len(groups), len(valid)))
    for h, names in sorted(dup_groups.items()):
        print("  %s  %s" % (h[:16], ", ".join(names)))

    if ranking:
        print("\nranking (most likely original first):")
        for i, p in enumerate(ranking, 1):
            note = ""
            if p.get("emptied_ratio", 0.0) >= 0.5:
                note = ("  <-- SKELETON: emptied%%=%.0f, extraction-shell shape"
                        % (100.0 * p["emptied_ratio"]))
            elif p.get("bodies_erased", 0):
                note = ("  <-- %d body(ies) wiped to nops: skeleton evidence"
                        % p["bodies_erased"])
            print("  %d. %-28s stub%%=%.1f  erased%%=%.1f  min/erased=%d  cksum=%s  "
                  "sig=%s  classes=%d%s"
                  % (i, p["name"], 100.0 * p["trivial_ratio"],
                     100.0 * (p["bodies_erased"] / p["methods_with_code"]
                              if p["methods_with_code"] else 0.0),
                     p.get("bodies_minimal", 0) + p.get("bodies_erased", 0),
                     "ok" if p["checksum_ok"] else "BAD",
                     "ok" if p["signature_ok"] else "BAD",
                     p["classes"], note))
        top = ranking[0]
        copies = len(groups.get(top["sha256"], []))
        print("\nverdict: %s is the best-supported candidate for the original "
              "(%d copy(ies) in this set)" % (top["name"], copies))
        print("ranked by: mostly-emptied images evicted first (emptied%% >= 50), then "
              "the minimal+nop-erased body count low-first, then emptied%%.\n"
              "  Limits, stated rather than hidden: this cannot see a `throw`-stub "
              "skeleton (it scores at the control's own baseline), and a\n"
              "  partially extracted image still outranks a heavily stubbed one. "
              "Confirm the winner before using it as a patch baseline --\n"
              "  docs/tool-verification/EXTENSION-extraction-shell-bench.md")
    else:
        print("\nverdict: no image parsed as a dex -- nothing to rank")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
