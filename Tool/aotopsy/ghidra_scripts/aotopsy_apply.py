# -*- coding: utf-8 -*-
# aotopsy_apply.py - Ghidra headless postScript
#
# Reads flutter_meta.json produced by `aotopsy meta`, applies:
#   1. Function creation + renaming
#   2. Struct types for Dart classes + typed function signatures
#   3. EOL comments (THR fields, PP pool references)
#   4. Selective decompilation export for signal (focus) functions
#
# Usage (headless):
#   analyzeHeadless <project_dir> <project_name> \
#       -import <libapp.so> -overwrite \
#       -scriptPath <path_to_this_dir> \
#       -preScript aotopsy_prescript.py \
#       -postScript aotopsy_apply.py <flutter_meta.json> [<output_dir>]
#
# Script args:
#   arg[0]: path to flutter_meta.json (required)
#   arg[1]: output directory for decompiled .c files (optional)

import json
import os

from ghidra.program.model.symbol import SourceType
from ghidra.program.model.data import (
    Pointer64DataType, Pointer32DataType, PointerDataType,
    StructureDataType, CategoryPath, VoidDataType, LongDataType,
    IntegerDataType,
)
from ghidra.program.model.listing import ParameterImpl
from ghidra.program.model.listing import Function as GhidraFunction
from java.util import ArrayList
from ghidra.app.decompiler import DecompInterface

try:
    from ghidra.program.model.pcode import HighFunctionDBUtil
    HAS_HFDB_UTIL = True
except Exception as e:
    HAS_HFDB_UTIL = False

try:
    from ghidra.program.model.data import DataTypeConflictHandler
    REPLACE_HANDLER = DataTypeConflictHandler.REPLACE_HANDLER
except Exception as e:
    REPLACE_HANDLER = None


def resolve_meta_path(args):
    """Resolve flutter_meta.json path from script args or relative to this script."""
    if args and len(args) >= 1 and args[0]:
        return args[0]
    # Standalone mode: look for ../flutter_meta.json relative to this script.
    try:
        script_dir = os.path.dirname(os.path.abspath(sourceFile.getAbsolutePath()))
    except Exception:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, "..", "flutter_meta.json")
    if os.path.exists(candidate):
        return candidate
    raise RuntimeError(
        "flutter_meta.json not found. Pass as script argument or place this script in <output>/ghidra/"
    )


def main():
    args = getScriptArgs()
    try:
        meta_path = resolve_meta_path(args)
    except RuntimeError as e:
        println("ERROR: %s" % str(e))
        return
    out_dir = args[1] if len(args) > 1 else None

    println("aotopsy_apply: loading %s" % meta_path)

    with open(meta_path, "r") as f:
        meta = json.load(f)

    stats = {
        "functions": len(meta.get("functions", [])),
        "renamed": 0,
        "created": 0,
        "create_failed": 0,
        "labels": 0,
        "comments": 0,
        "comment_failed": 0,
        "decompiled": 0,
        "decompile_failed": 0,
    }

    fm = currentProgram.getFunctionManager()
    listing = currentProgram.getListing()
    symtab = currentProgram.getSymbolTable()

    # Detect image base: Ghidra rebases shared objects (typically +0x100000).
    mem = currentProgram.getMemory()
    image_base = currentProgram.getImageBase().getOffset()
    println("  image base: 0x%x" % image_base)

    # Determine pointer size from metadata (compressed pointers = 4 bytes).
    pointer_size = meta.get("pointer_size", 8)
    println("  pointer_size: %d" % pointer_size)

    # ptr_type = pointer to void (for return types, params — always 8 bytes in AArch64).
    # PointerDataType(VoidDataType()) renders as "void *" instead of "undefined *".
    ptr_type = PointerDataType(VoidDataType())

    # field_type = type used for Dart object fields inside structs.
    # With compressed pointers (4 bytes), fields are 32-bit pointers.
    # Without compression (8 bytes), fields are 64-bit pointers.
    if pointer_size == 4:
        field_type = Pointer32DataType()
    else:
        field_type = PointerDataType(VoidDataType())

    # Phase 1a: Force disassembly at all function addresses.
    # Ghidra's auto-analysis skips Dart AOT code (no standard prologues).
    println("Phase 1a: disassembling at %d addresses..." % stats["functions"])
    disasm_ok = 0
    disasm_fail = 0
    for entry in meta.get("functions", []):
        addr_int = int(entry["addr"], 16) + image_base
        addr = toAddr(addr_int)
        if listing.getInstructionAt(addr) is not None:
            disasm_ok += 1
            continue
        try:
            clearListing(addr)
            disassemble(addr)
            if listing.getInstructionAt(addr) is not None:
                disasm_ok += 1
            else:
                disasm_fail += 1
        except Exception as e:
            disasm_fail += 1
    println("  disassembled=%d failed=%d" % (disasm_ok, disasm_fail))

    # Phase 1b: Create/rename functions.
    println("Phase 1b: creating/renaming %d functions..." % stats["functions"])
    for entry in meta.get("functions", []):
        addr_int = int(entry["addr"], 16) + image_base
        addr = toAddr(addr_int)
        name = entry["name"]

        fn = fm.getFunctionAt(addr)
        if fn is not None:
            try:
                fn.setName(name, SourceType.USER_DEFINED)
                stats["renamed"] += 1
            except Exception as e:
                println("  WARN: rename failed at %s: %s" % (entry["addr"], str(e)[:80]))
            continue

        # Try to create function.
        try:
            fn = createFunction(addr, name)
            if fn is not None:
                stats["created"] += 1
                continue
        except Exception as e:
            pass

        # Fallback: disassemble at the address, then try again.
        try:
            disassemble(addr)
            fn = createFunction(addr, name)
            if fn is not None:
                stats["created"] += 1
                continue
        except Exception as e:
            pass

        # Last resort: create a label so the name appears.
        try:
            symtab.createLabel(addr, name, SourceType.USER_DEFINED)
            stats["labels"] += 1
        except Exception as e:
            stats["create_failed"] += 1

    println("  created=%d renamed=%d labels=%d failed=%d" % (
        stats["created"], stats["renamed"], stats["labels"], stats["create_failed"]))

    # Verify: count how many functions exist now at our addresses.
    verify_count = 0
    for entry in meta.get("functions", []):
        addr = toAddr(int(entry["addr"], 16) + image_base)
        if fm.getFunctionAt(addr) is not None:
            verify_count += 1
    println("  verified: %d/%d addresses have functions" % (verify_count, stats["functions"]))

    # Phase 1c: Create struct types for Dart classes.
    # Must run BEFORE param application so typed 'this' pointers can reference structs.
    classes = meta.get("classes", [])
    struct_by_owner = {}  # class_name -> Ghidra DataType
    if classes:
        println("Phase 1c: creating %d class struct types..." % len(classes))
        dtm = currentProgram.getDataTypeManager()
        cat = CategoryPath("/DartClasses")
        struct_created = 0
        struct_failed = 0

        for cls in classes:
            try:
                cname = cls["class_name"]
                sname = "Dart_" + sanitize(cname)
                size = cls["instance_size"]
                if size <= 0:
                    continue
                fields = cls.get("fields", [])

                struct_dt = StructureDataType(cat, sname, size)
                for field in fields:
                    offset = field["byte_offset"]
                    fname = field["name"]
                    if offset >= 0 and offset + pointer_size <= size:
                        struct_dt.replaceAtOffset(offset, field_type, pointer_size, fname, "")

                resolved = dtm.addDataType(struct_dt, REPLACE_HANDLER)
                struct_by_owner[cname] = resolved
                struct_created += 1
            except Exception as e:
                struct_failed += 1
                if struct_failed <= 5:
                    println("  WARN: struct %s: %s" % (cls.get("class_name", "?"), str(e)[:80]))

        println("  structs created=%d failed=%d (lookup=%d)" % (struct_created, struct_failed, len(struct_by_owner)))
    else:
        println("Phase 1c: skipped (no class layouts)")

    # Phase 1c2: Create DartThread struct from THR fields.
    thr_fields = meta.get("thr_fields", [])
    if thr_fields:
        println("Phase 1c2: creating DartThread struct (%d fields)..." % len(thr_fields))
        dtm = currentProgram.getDataTypeManager()
        cat = CategoryPath("/DartClasses")
        try:
            # Find max offset to determine struct size.
            max_off = max(f["offset"] for f in thr_fields)
            thr_size = max_off + 8  # last field is a pointer
            thr_dt = StructureDataType(cat, "DartThread", thr_size)
            thr_placed = 0
            for tf in thr_fields:
                off = tf["offset"]
                tname = tf["name"]
                if off >= 0 and off + 8 <= thr_size:
                    thr_dt.replaceAtOffset(off, ptr_type, 8, tname, "")
                    thr_placed += 1
            dtm.addDataType(thr_dt, REPLACE_HANDLER)
            println("  DartThread: %d/%d fields placed (size=%d)" % (thr_placed, len(thr_fields), thr_size))
        except Exception as e:
            println("  WARN: DartThread creation failed: %s" % str(e)[:120])
    else:
        println("Phase 1c2: skipped (no THR fields)")

    # Prepare DartThread* type for register retyping in decompiler output.
    # When x26 is typed as DartThread*, the decompiler resolves
    # *(long *)(unaff_x26 + 0x38) → THR->stack_limit automatically.
    dart_thread_ptr_dt = None
    if thr_fields and HAS_HFDB_UTIL:
        dtm_check = currentProgram.getDataTypeManager()
        resolved = dtm_check.getDataType(CategoryPath("/DartClasses"), "DartThread")
        if resolved:
            dart_thread_ptr_dt = PointerDataType(resolved)
            println("  DartThread* ready for register retyping")

    # Phase 1d: Apply function signatures (typed parameters + return type).
    # For methods (functions with an owner class):
    #   - First param = this: Dart_OwnerClass* (typed pointer to owner struct)
    #   - Remaining params = generic pointers
    # For all functions:
    #   - Calling convention = __dartcall (registered by prescript via SpecExtension)
    #   - Return type = pointer (Dart functions return objects, not undefined)
    println("Phase 1d: applying function signatures...")
    sig_applied = 0
    sig_failed = 0
    ret_applied = 0
    this_typed = 0
    for entry in meta.get("functions", []):
        addr = toAddr(int(entry["addr"], 16) + image_base)
        fn = fm.getFunctionAt(addr)
        if fn is None:
            continue

        owner = entry.get("owner", "")
        pc = entry.get("param_count", 0)

        # Set calling convention to __dartcall (registered by prescript).
        # Must happen BEFORE replaceParameters to avoid "Unknown calling convention" warning.
        try:
            fn.setCallingConventionName("__dartcall")
        except Exception as e:
            pass

        # Set return type to pointer (Dart returns objects, not undefined).
        try:
            fn.setReturnType(ptr_type, SourceType.USER_DEFINED)
            ret_applied += 1
        except Exception as e:
            pass

        # Build parameter list (ArrayList for JPype/PyGhidra overload resolution).
        params = ArrayList()

        # Methods get typed 'this' as first parameter.
        # param_count excludes implicit 'this', so we add it separately.
        if owner:
            if owner in struct_by_owner:
                this_dt = PointerDataType(struct_by_owner[owner])
                this_typed += 1
            else:
                this_dt = ptr_type
            params.add(ParameterImpl("this", this_dt, currentProgram))

        # Explicit parameters.
        for i in range(pc):
            params.add(ParameterImpl("p%d" % i, ptr_type, currentProgram))

        if params.size() == 0:
            continue

        try:
            fn.replaceParameters(params,
                GhidraFunction.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS,
                True, SourceType.USER_DEFINED)
            # P2.5-4: replaceParameters can reset the calling convention
            # back to the default. Re-apply __dartcall after replaceParameters.
            try:
                fn.setCallingConventionName("__dartcall")
            except Exception:
                pass
            sig_applied += 1
        except Exception as e:
            sig_failed += 1
            if sig_failed <= 3:
                println("  WARN: replaceParameters failed for %s: %s" % (entry.get("name", "?"), str(e)[:120]))

    println("  signatures applied=%d failed=%d return_types=%d this_typed=%d" % (
        sig_applied, sig_failed, ret_applied, this_typed))

    # Phase 2: Set EOL comments.
    # P2.5-2: Prefix aotopsy comments with a marker so re-runs only
    # replace our own comments, preserving user-added comments.
    AOTOPSY_COMMENT_PREFIX = "aotopsy: "
    comment_entries = meta.get("comments", [])
    println("Phase 2: setting %d comments..." % len(comment_entries))
    comments_preserved = 0
    for entry in comment_entries:
        addr_int = int(entry["addr"], 16) + image_base
        addr = toAddr(addr_int)
        text = entry["text"]
        # Check if there's an existing comment.
        existing = getEOLComment(addr)
        if existing:
            # Check if the aotopsy marker is already present to avoid
            # duplicating aotopsy comments on re-runs. If the marker is
            # already in the existing comment, replace only the aotopsy
            # portion; otherwise append.
            if AOTOPSY_COMMENT_PREFIX in existing:
                # Split on the marker: everything before is user comment,
                # everything from the marker onward is the old aotopsy block.
                idx = existing.find(AOTOPSY_COMMENT_PREFIX)
                user_part = existing[:idx].rstrip("\n")
                text = (user_part + "\n" if user_part else "") + AOTOPSY_COMMENT_PREFIX + text
            else:
                # User has added their own comment here — append ours.
                comments_preserved += 1
                text = existing + "\n" + AOTOPSY_COMMENT_PREFIX + text
        else:
            text = AOTOPSY_COMMENT_PREFIX + text
        try:
            setEOLComment(addr, text)
            stats["comments"] += 1
        except Exception as e:
            stats["comment_failed"] += 1
    if comments_preserved > 0:
        println("  preserved %d user comment(s) by appending" % comments_preserved)

    println("  set=%d failed=%d" % (stats["comments"], stats["comment_failed"]))

    # Phase 3: Selective decompilation.
    # Build addr → owner lookup for directory grouping.
    owner_by_addr = {}
    for entry in meta.get("functions", []):
        owner = entry.get("owner", "")
        if owner:
            owner_by_addr[entry["addr"]] = owner

    focus = meta.get("focus_functions", [])
    if out_dir and focus:
        println("Phase 3: decompiling %d focus functions..." % len(focus))
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        ifc = DecompInterface()
        # Use "decompile" simplification to reduce VarnodeContext pressure.
        ifc.setSimplificationStyle("decompile")
        ifc.openProgram(currentProgram)

        index = []
        not_found = 0
        for addr_str in focus:
            addr_int = int(addr_str, 16) + image_base
            addr = toAddr(addr_int)

            # Try exact match first, then containing.
            fn = fm.getFunctionAt(addr)
            if fn is None:
                fn = fm.getFunctionContaining(addr)

            if fn is None:
                not_found += 1
                if not_found <= 5:
                    println("  WARN: no function at %s" % addr_str)
                index.append({
                    "addr": addr_str,
                    "name": "unknown",
                    "file": None,
                    "decompile_ok": False,
                    "reason": "no_function",
                })
                stats["decompile_failed"] += 1
                continue

            fn_name = fn.getName()
            try:
                result = ifc.decompileFunction(fn, 60, monitor)
            except Exception as e:
                index.append({
                    "addr": addr_str,
                    "name": fn_name,
                    "file": None,
                    "decompile_ok": False,
                    "reason": str(e)[:100],
                })
                stats["decompile_failed"] += 1
                continue

            # Retype Dart registers for readable decompiler output:
            #   x26 → THR (DartThread*)  — resolves field accesses
            #   x27 → PP               — object pool pointer
            #   x28 → HEAP_BASE        — compressed pointer base
            #   x15 → SHADOW_SP        — Dart shadow call stack
            if result and result.decompileCompleted() and HAS_HFDB_UTIL:
                hfunc = result.getHighFunction()
                if hfunc:
                    retyped = _retype_dart_registers(
                        hfunc, dart_thread_ptr_dt, ptr_type)
                    if retyped:
                        try:
                            result = ifc.decompileFunction(fn, 60, monitor)
                        except Exception as e:
                            pass

            if result and result.decompileCompleted():
                decomp = result.getDecompiledFunction()
                if decomp:
                    c_code = decomp.getC()
                    # Strip cosmetic warning from SpecExtension-registered CC.
                    # The native decompiler doesn't receive SpecExtension CCs,
                    # so it flags __dartcall as unknown. The CC works functionally.
                    c_code = c_code.replace(
                        "/* WARNING: Unknown calling convention -- yet parameter storage is locked */\n\n", "")
                    c_code = c_code.replace(
                        "/* WARNING: Unknown calling convention -- yet parameter storage is locked */\n", "")
                    safe_name = addr_str.replace("0x", "") + "_" + sanitize(fn_name)
                    # Use owner-based subdirectory if available.
                    owner = owner_by_addr.get(addr_str, "")
                    if owner:
                        sub_dir = os.path.join(out_dir, sanitize(owner))
                        if not os.path.exists(sub_dir):
                            os.makedirs(sub_dir)
                        out_file = os.path.join(sanitize(owner), safe_name + ".c")
                    else:
                        out_file = safe_name + ".c"
                    out_path = os.path.join(out_dir, out_file)
                    with open(out_path, "w") as cf:
                        cf.write(c_code)
                    index.append({
                        "addr": addr_str,
                        "name": fn_name,
                        "file": out_file,
                        "decompile_ok": True,
                    })
                    stats["decompiled"] += 1
                    continue

            reason = "decompile_incomplete"
            if result:
                err_msg = result.getErrorMessage()
                if err_msg:
                    reason = err_msg[:100]

            index.append({
                "addr": addr_str,
                "name": fn_name,
                "file": None,
                "decompile_ok": False,
                "reason": reason,
            })
            stats["decompile_failed"] += 1

        if not_found > 0:
            println("  %d focus functions not found" % not_found)

        ifc.dispose()

        # Write index.json.
        index_path = os.path.join(out_dir, "index.json")
        with open(index_path, "w") as idx:
            json.dump(index, idx, indent=2)
        println("  decompiled=%d failed=%d" % (stats["decompiled"], stats["decompile_failed"]))
    elif focus:
        println("Phase 3: skipped (no output directory specified)")
    else:
        println("Phase 3: skipped (no focus functions)")

    # Disable Decompiler Parameter ID before exiting.
    # Ghidra auto-re-analyzes after postScript changes. The re-analysis triggers
    # "VarnodeContext: out of address spaces" errors on large Dart AOT binaries.
    # Since we already applied our own signatures, this analyzer is redundant.
    try:
        setAnalysisOption(currentProgram, "Decompiler Parameter ID", "false")
    except Exception as e:
        pass

    # Summary.
    println("AOTOPSY_APPLY: functions=%d renamed=%d created=%d labels=%d comments=%d decompiled=%d failed=%d" % (
        stats["functions"],
        stats["renamed"],
        stats["created"],
        stats["labels"],
        stats["comments"],
        stats["decompiled"],
        stats["decompile_failed"],
    ))


def _retype_dart_registers(hfunc, dart_thread_ptr_dt, ptr_type):
    """Retype Dart-specific unaffected registers for readable decompiler output.

    Renames and types:
      x15 → SHADOW_SP   (long*)  Dart shadow call stack
      x21 → DT          (long)  dispatch table pointer
      x22 → DART_NULL   (long)  Dart null object
      x26 → THR         (DartThread*)  resolves struct field accesses
      x27 → PP          (long*)  object pool pointer (indexed)
      x28 → HEAP_BASE   (long)  compressed pointer base
      x29 → FP          (long)  frame pointer
      x30 → LR          (long)  link register / return address

    Also handles 32-bit subregister variants (w22, etc.) and Ghidra's
    internal register-space names (unaff_000040b4 = upper half of x22).

    Returns True if any symbols were retyped (caller should re-decompile).
    """
    long_type = LongDataType()
    int_type = IntegerDataType()  # 4 bytes — for w-regs and upper halves
    long_ptr_type = PointerDataType(long_type)  # long * — for stack/pool pointers

    # Map unaff_/in_ names to (readable_name, type).
    # None type = keep existing type.
    RENAMES = {
        # 64-bit registers — typed to eliminate undefined8
        "unaff_x15": ("SHADOW_SP",    long_ptr_type),  # Dart shadow stack
        "unaff_x21": ("DT",           long_type),
        "unaff_x22": ("DART_NULL",    long_type),
        "unaff_x26": ("THR",          dart_thread_ptr_dt),  # DartThread*
        "unaff_x27": ("PP",           long_ptr_type),  # pool pointer — indexed
        "unaff_x28": ("HEAP_BASE",    long_type),
        "unaff_x29": ("FP",           long_type),
        "unaff_x30": ("LR",           long_type),
        # 32-bit subregister variants (w-regs) — suffixed _lo to avoid
        # duplicate variable declarations when both x-reg and w-reg appear
        "unaff_w15": ("SHADOW_SP_lo", int_type),
        "unaff_w21": ("DT_lo",        int_type),
        "unaff_w22": ("DART_NULL_lo", int_type),
        "unaff_w26": ("THR_lo",       int_type),
        "unaff_w27": ("PP_lo",        int_type),
        "unaff_w28": ("HEAP_BASE_lo", int_type),
        "unaff_w29": ("FP_lo",        int_type),
        "unaff_w30": ("LR_lo",        int_type),
        # Upper 32-bit halves (Ghidra register-space offsets)
        # These are internal split-register names — type as int
        "unaff_000040b4":         ("DART_NULL_HI", int_type),   # upper x22
        "in_register_00004004":   ("x0_HI",        int_type),   # upper x0
        "in_register_0000400c":   ("x1_HI",        int_type),   # upper x1
        "in_register_00004014":   ("x2_HI",        int_type),   # upper x2
        "in_register_0000401c":   ("x3_HI",        int_type),   # upper x3
        "in_register_00004024":   ("x4_HI",        int_type),   # upper x4
        "in_register_0000402c":   ("x5_HI",        int_type),   # upper x5
        "in_register_00004034":   ("x6_HI",        int_type),   # upper x6
        "in_register_0000403c":   ("x7_HI",        int_type),   # upper x7
        # 32-bit parameter in-registers (w0-w7)
        "in_w0":  ("p0",    int_type),
        "in_w1":  ("p1",    int_type),
        "in_w2":  ("p2",    int_type),
        "in_w3":  ("p3",    int_type),
        "in_w4":  ("p4",    int_type),
        "in_w5":  ("p5",    int_type),
        "in_w6":  ("p6",    int_type),
        "in_w7":  ("p7",    int_type),
    }

    did_retype = False
    lsm = hfunc.getLocalSymbolMap()
    # Snapshot the iterator to avoid ConcurrentModificationException.
    symbols = list(lsm.getSymbols())
    for sym in symbols:
        sym_name = sym.getName()
        entry = RENAMES.get(sym_name)
        if entry is None:
            # P2.5-3: Dynamic fallback for register-space offset names.
            # Hardcoded offsets (e.g., unaff_000040b4) break on Ghidra upgrades
            # because the register space base offset can change. Try to match
            # by pattern: unaff_<hex> or in_register_<hex> are upper halves
            # of registers. Map them based on the offset relative to x0's
            # register-space offset.
            #
            # L-2 (oracle-audit): 0x4004 is Ghidra 10.x-specific (x0 at 0x4000,
            # upper half at 0x4004). On Ghidra 11+ this offset may differ.
            # If this fallback produces wrong xN_HI names or all indices are
            # out of range (silently skipped by the 0<=reg_idx<=31 check),
            # verify the register-space base offset for your Ghidra version
            # by checking a known register (e.g., x26 = THR) in the decompiler
            # and updating 0x4004 accordingly. The primary RENAMES map above
            # is not affected by this issue.
            if sym_name.startswith("unaff_") and len(sym_name) > 10:
                # Try to compute which register this is an upper half of.
                # Format: unaff_<8-hex-digits> — offset in register space.
                try:
                    offset = int(sym_name[6:], 16)
                    # x0 is at 0x4000, each register is 8 bytes apart.
                    # Upper half = base + 4.
                    reg_idx = (offset - 0x4004) // 8
                    if 0 <= reg_idx <= 31:
                        entry = ("x%d_HI" % reg_idx, int_type)
                except ValueError:
                    pass
            elif sym_name.startswith("in_register_") and len(sym_name) > 16:
                try:
                    offset = int(sym_name[12:], 16)
                    reg_idx = (offset - 0x4004) // 8
                    if 0 <= reg_idx <= 31:
                        entry = ("x%d_HI" % reg_idx, int_type)
                except ValueError:
                    pass
        if entry is None:
            continue
        new_name, new_dt = entry
        try:
            dt = new_dt if new_dt else sym.getDataType()
            HighFunctionDBUtil.updateDBVariable(
                sym, new_name, dt, SourceType.USER_DEFINED)
            did_retype = True
        except Exception as e:
            pass
    return did_retype


def sanitize(name):
    """Sanitize a function name for use as a filename."""
    out = []
    for ch in name:
        if ch.isalnum() or ch in ("_", "-", "."):
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out)
    if len(s) > 120:
        s = s[:120]
    return s


main()
