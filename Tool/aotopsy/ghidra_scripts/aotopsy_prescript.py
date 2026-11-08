# -*- coding: utf-8 -*-
# aotopsy_prescript.py - Ghidra headless preScript
#
# Configures analysis options before Ghidra auto-analysis runs.
# Dart AOT binaries have patterns that confuse standard analyzers:
#   - No standard ARM64 function prologues (Dart uses unchecked entry +0x18)
#   - BLR X21 dispatch table calls (not switch tables)
#   - Dense data sections interleaved with code
#
# Registers the __dartcall calling convention via SpecExtension and sets it
# as the program-wide default, so no modification of Ghidra installation
# files is needed.
#
# Usage:
#   analyzeHeadless ... -preScript aotopsy_prescript.py -postScript aotopsy_apply.py ...

from ghidra.program.database import SpecExtension

# Dart AOT calling convention for ARM64.
# Key difference from standard __cdecl:
#   - X15 in <unaffected> (Dart shadow call stack / stack cache)
#   - X21, X26 (THR), X27 (PP), X28 (heap base) all <unaffected>
DART_PROTO_XML = """\
<prototype name="__dartcall" extrapop="0" stackshift="0">
  <input>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x0"/></pentry>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x1"/></pentry>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x2"/></pentry>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x3"/></pentry>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x4"/></pentry>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x5"/></pentry>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x6"/></pentry>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x7"/></pentry>
    <pentry minsize="1" maxsize="500" align="8"><addr offset="0" space="stack"/></pentry>
  </input>
  <output>
    <pentry minsize="1" maxsize="8" extension="zero"><register name="x0"/></pentry>
  </output>
  <unaffected>
    <register name="x15"/>
    <register name="x19"/>
    <register name="x20"/>
    <register name="x21"/>
    <register name="x22"/>
    <register name="x23"/>
    <register name="x24"/>
    <register name="x25"/>
    <register name="x26"/>
    <register name="x27"/>
    <register name="x28"/>
    <register name="x29"/>
    <register name="x30"/>
    <register name="sp"/>
    <register name="d8"/>
    <register name="d9"/>
    <register name="d10"/>
    <register name="d11"/>
    <register name="d12"/>
    <register name="d13"/>
    <register name="d14"/>
    <register name="d15"/>
  </unaffected>
  <killedbycall>
    <register name="x8"/>
    <register name="x9"/>
    <register name="x10"/>
    <register name="x11"/>
    <register name="x12"/>
    <register name="x13"/>
    <register name="x14"/>
    <register name="x16"/>
    <register name="x17"/>
    <register name="x18"/>
    <register name="d16"/>
    <register name="d17"/>
    <register name="d18"/>
    <register name="d19"/>
    <register name="d20"/>
    <register name="d21"/>
    <register name="d22"/>
    <register name="d23"/>
    <register name="d24"/>
    <register name="d25"/>
    <register name="d26"/>
    <register name="d27"/>
    <register name="d28"/>
    <register name="d29"/>
    <register name="d30"/>
    <register name="d31"/>
  </killedbycall>
</prototype>
"""


def main():
    println("aotopsy_prescript: configuring analysis for Dart AOT binary")

    # Step 1: Register __dartcall as a new calling convention via SpecExtension.
    try:
        spec_ext = SpecExtension(currentProgram)
        spec_ext.addReplaceCompilerSpecExtension(DART_PROTO_XML, monitor)
        println("  registered __dartcall calling convention")
    except Exception as e:
        println("  WARN: could not register __dartcall: %s" % str(e)[:120])

    # Step 2: Make __dartcall the program-wide default calling convention.
    # SpecExtension can't replace __cdecl (Ghidra blocks it), so we use
    # reflection to swap the defaultModel pointer. This ensures ALL call
    # targets (including unnamed stubs) use dart register classification,
    # eliminating extraout_x15 globally.
    try:
        cspec = currentProgram.getCompilerSpec()
        dartcall = cspec.getCallingConvention("__dartcall")
        if dartcall is not None:
            # BasicCompilerSpec has three prototype model fields that control
            # how the decompiler treats function calls:
            #   defaultModel     — default calling convention for new functions
            #   evalCurrentModel — prototype used to evaluate the current function
            #   evalCalledModel  — prototype used to evaluate CALLED functions
            # All three must point to __dartcall, otherwise the decompiler
            # will still use __cdecl (with X15 in killedbycall) for calls
            # to unknown targets, producing extraout_x15.
            base_class = cspec.getClass().getSuperclass()
            for field_name in ("defaultModel", "evalCurrentModel", "evalCalledModel"):
                f = base_class.getDeclaredField(field_name)
                f.setAccessible(True)
                f.set(cspec, dartcall)
            println("  set __dartcall as program default calling convention")
        else:
            println("  WARN: __dartcall not found after registration")
    except Exception as e:
        println("  WARN: could not set default CC: %s" % str(e)[:120])

    # Dart AOT doesn't use standard ARM64 prologues, so the aggressive
    # instruction finder creates false function starts in data regions.
    try:
        setAnalysisOption(currentProgram, "Aggressive Instruction Finder", "false")
        println("  disabled: Aggressive Instruction Finder")
    except Exception as e:
        println("  WARN: could not disable Aggressive Instruction Finder: %s" % str(e)[:60])

    # Dart functions don't follow standard non-return conventions.
    # The discovered non-returning analysis propagates incorrect assumptions.
    try:
        setAnalysisOption(currentProgram, "Non-Returning Functions - Discovered", "false")
        println("  disabled: Non-Returning Functions - Discovered")
    except Exception as e:
        println("  WARN: could not disable Non-Returning Functions - Discovered: %s" % str(e)[:60])

    # Decompiler Parameter ID performs heavy p-code varnode context analysis
    # during auto-analysis. On large Dart AOT binaries (36k+ functions), this
    # causes "VarnodeContext: out of address spaces" errors. We apply our own
    # signatures in the postscript, so this analyzer is redundant.
    try:
        setAnalysisOption(currentProgram, "Decompiler Parameter ID", "false")
        println("  disabled: Decompiler Parameter ID")
    except Exception as e:
        println("  WARN: could not disable Decompiler Parameter ID: %s" % str(e)[:60])

    println("aotopsy_prescript: done")


main()
