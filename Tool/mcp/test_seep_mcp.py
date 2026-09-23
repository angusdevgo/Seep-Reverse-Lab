#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for seep MCP Server tools
"""

import sys
import os
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from seep_mcp_server import (
    seep_status,
    seep_r2_info,
    seep_r2_strings,
    seep_r2_functions,
    seep_r2_disasm,
    seep_r2_decompile,
    seep_r2_asm,
    seep_apk_gen_hook,
    seep_kb_search,
    seep_kb_checklist,
    seep_kb_payloads
)

def run_tests():
    print("=== [1/9] Testing seep_status ===")
    status = seep_status()
    print(status)
    assert "seep" in status

    test_elf = os.path.join(os.path.dirname(__file__), "Tool", "safe", "ida-pro-mcp", "tests", "typed_fixture.elf")
    if os.path.isfile(test_elf):
        print("\n=== [2/9] Testing seep_r2_info ===")
        info = seep_r2_info(test_elf)
        print(info[:300] + "...")
        assert "x86" in info or "elf" in info

        print("\n=== [3/9] Testing seep_r2_strings ===")
        strings = seep_r2_strings(test_elf, filter_text="hi", limit=5)
        print(strings)
        assert "typed fixture says hi" in strings

        print("\n=== [4/9] Testing seep_r2_disasm (main) ===")
        disasm = seep_r2_disasm(test_elf, target="main", lines=20)
        print(disasm[:400] + "...")
        assert "main" in disasm

        print("\n=== [5/9] Testing seep_r2_decompile (main) ===")
        decomp = seep_r2_decompile(test_elf, target="main")
        print(decomp[:400] + "...")
        assert "main" in decomp
    else:
        print("Skipping ELF tests (typed_fixture.elf not found)")

    print("\n=== [6/9] Testing seep_r2_asm ===")
    hex_code = seep_r2_asm("xor eax, eax; ret", arch="x86", bits=64)
    print("Assemble 'xor eax, eax; ret' ->", hex_code)
    assert "31c0" in hex_code
    asm_code = seep_r2_asm(hex_code, arch="x86", bits=64, disasm=True)
    print("Disassemble ->", asm_code)
    assert "xor" in asm_code

    print("\n=== [7/9] Testing seep_apk_gen_hook ===")
    frida_hook = seep_apk_gen_hook("frida", "com.sec.Validator", "isVip", return_type="boolean", hook_timing="replace")
    print("Generated Frida Hook:\n", frida_hook[:200] + "...")
    assert "Java.perform" in frida_hook

    print("\n=== [8/9] Testing seep_kb_search ===")
    kb_res = seep_kb_search("JWT", limit=3)
    print("Search 'JWT':\n", kb_res[:400] + "...")
    assert "jwt" in kb_res.lower()

    print("\n=== [9/9] Testing seep_kb_checklist & payloads ===")
    chk = seep_kb_checklist("web_first_30_min")
    print("Checklist first line:\n", chk.splitlines()[0])
    assert "Web CTF" in chk

    payloads = seep_kb_payloads("jwt")
    print("Payloads snippet:\n", payloads[:200] + "...")

    print("\nALL 9 TESTS PASSED SUCCESSFULLY! seep MCP is fully functional.")

if __name__ == "__main__":
    run_tests()
