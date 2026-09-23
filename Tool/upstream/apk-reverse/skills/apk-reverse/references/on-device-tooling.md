# On-device tooling — MT Manager, APK MCP, LSPosed, Termux

Sometimes the PC is the wrong place to work: the device already has the APK installed, the edit is
one string, the target is a 38 MB repack you would otherwise push back and forth, or there simply
is no laptop in the loop. This file covers the **on-device toolchain** and — more importantly —
when each tool beats its PC counterpart and when it does not.

Evidence basis: the facts below come from a real configured environment (Android 11, Magisk +
Zygisk, LSPosed v1.9.2, MT Manager 2.26.9). Framework
activation and the module set are `observed` there; per-workflow usability notes are `measured`
where marked, otherwise `inferred`. The MT MCP tool surface is from MT's official documentation
(`observed` as a list; live invocation requires the service to be running — see).


**Load this when:** the work is better done on the phone than on the PC -- one-string edits, an already-installed target, or no laptop in the loop. It gives MT Manager edit/repack/sign and its APK MCP surface, LSPosed Manager, and Termux.

## 1. MT Manager as a reverse-engineering workbench

MT Manager (`bin.mt.plus`) is a file manager plus APK editor. For this skill's purposes it is a
**complete repack pipeline that runs on the phone**: view, edit, rebuild, sign.

What it covers, mapped to this skill's workflow stages:

| Skill stage | MT capability | Notes |
|---|---|---|
| Recon (manifest, SDKs) | APK viewer: manifest, entry list, string search across dex/resources | String search is the fast path; no full Java decompile in the editor workflow |
| Dex reading/editing | Dex viewer + smali-level editing | Smali is the editing granularity — same discipline as `dex-patching.md` |
| Removing signature verification | Built-in "去除签名校验" (signature-check killer) feature | Convenience feature; audit what it actually patched — a Java-layer signature killer can be a decoy while a native check still kills you (`code-virtualization-and-custom-linkers.md` §decoy) |
| Extracting artifacts | Pull `classes.dex`, `.so`, `resources.arsc`, axml out of any APK/zip | Useful to move a single `.so` to the PC toolchain without a full unzip |
| Repack + sign | Rebuild APK and sign it on device | Output lands in MT's working directory; verify with the same discipline as `repack-and-sign.md` (alignment, `resources.arsc` rules still apply — the platform enforces them regardless of which machine built the file) |

**When MT beats the PC pipeline:** quick single-file edits, on-the-spot verification on the same
device the app is installed on, and sessions where shuffling 40 MB APKs over USB dominates the
work. **When the PC wins:** anything scriptable/repeatable, dex-wide cross-referencing
(`find_refs.py`), byte-precision patching with header recomputation, and anything needing a real
decompiler. The honest split: MT for **breadth on device**, PC for **depth and repeatability**.
`inferred`.

## 2. MT's built-in APK MCP server

MT 2.26.9+ ships an "APK MCP" service: it exposes MT's analysis and modification capabilities to
an MCP (Model Context Protocol) client — which in practice means an AI agent drives MT's tooling
over HTTP while the human sees the results on the phone. The official framing: AI understands the
request and calls the tools; MT does the local read/modify/repack/sign.

**Transport and endpoint** (`measured` on the reference environment):

- Streamable HTTP MCP at `http://127.0.0.1:8787/mcp` from the PC, via `adb forward tcp:8787
  tcp:8787`; or directly `http://<phone-ip>:8787/mcp` on the LAN.
- **The service must be started by hand in the MT UI** (side drawer → Tools → APK MCP → Start).
  adb cannot start it. Before it is started, the port is simply not listening — probe with
  `scripts/mt_mcp_probe.py`, which prints waiting instructions in that state.

**Tool surface** (official documentation; names observed from the published list):

| Category | Tools |
|---|---|
| Open/selection | `mt_apk_list_available_apks`, `mt_apk_open` |
| Reading/search | `mt_apk_list`, `mt_apk_search`, `mt_apk_read_text`, `mt_apk_read_bytes`, `mt_apk_continue` |
| Dex analysis | `mt_apk_dex_outline_class`, `mt_apk_dex_xref` |
| Resources | `mt_apk_resource_read`, `mt_apk_resource_xref` |
| Native static | `mt_apk_native_inspect`, `mt_apk_native_read_items`, `mt_apk_native_map_address`, `mt_apk_native_xref`, `mt_apk_native_disassemble`, `mt_apk_native_function_cfg` |
| Modification | `mt_apk_edit_open`, `mt_apk_edit_text`, `mt_apk_edit_resource`, `mt_apk_patch_bytes`, `mt_apk_native_patch_instructions`, `mt_apk_native_patch_string`, `mt_apk_edit_check`, `mt_apk_build` |
| Cleanup | `mt_apk_close` |

**Official constraints — budget your plans around these, not around hopes:**

1. **No Java decompilation.** The stated position: AI reads smali directly; decompiled Java of
   hardened/R8'd code misleads more than it helps. Cross-references (`dex_xref`) and class
   outlines are the structural view.
2. **`resources.arsc`: existing entries only.** No new locales or new entries — edit what ships,
   do not plan feature-additions through arsc.
3. **`.so` support is static analysis only.** No dynamic execution, no emulation, no C/C++
   pseudocode. Xrefs and CFG are "best-effort within a limited budget" — direct static results,
   **not** proof of a complete call chain or of runtime behaviour. For depth, the PC side (IDA/
   Ghidra-class, see `toolchain.md`) remains the answer.

**Handing an APK to the server** (three supported ways): open an APK in MT's file list and stay
on its info dialog ("the current APK file"); open an installed app's info dialog the same way; or
drop the APK into MT's configured MCP working directory and refer to it by filename/package. The
working directory is also where rebuild output lands.

**Probing from the PC:** `python scripts/mt_mcp_probe.py` does the full JSON-RPC handshake
(initialize → initialized → tools/list) with no MCP SDK dependency and prints a grouped tool
inventory. If MT's MCP has not been started in the UI, it exits with waiting instructions and
code 2 — usable as a loop check ("is it up yet") while you start it by hand. `measured`.

## 3. LSPosed Manager — the module route on device

LSPosed (via Zygisk) gives you a **Java-layer hook platform that needs no PC at runtime**: write/
install a module once, and it applies to target apps at every launch.

Facts from the reference environment (`observed`):

- Activation is verifiable from logs: the `ZygiskCompanion: welcome to LSPosed!` banner, the
  version line, the `lspd` daemon process running as system.
- Install discipline: `magisk --install-module` unpacks to `/data/adb/modules_update/` and only
  **merges after a reboot** — a module that "did not install" is usually one that has not merged
  yet. `ls /data/adb/modules/` is the truth; `modules_update/` non-empty means pending.
- Zygisk itself needs one reboot after being enabled before its injection layer exists at all.

Limits that matter for this skill: LSPosed hooks **Java/ART** — it cannot hook inside a native
`.so` (that is Frida/IDA territory, and the reason `framework-runtimes.md`'s runtime check
exists), and it does nothing for Flutter/Dart AOT logic below the platform channel. Use it for
the layer it owns: Java API interception, intent/telemetry rewriting, feature gates that live in
Java. A hook module is also **not a deliverable** for a request that wants an installable APK —
it is an environment change on your device (`detection-and-anti-analysis.md` Step 4 keeps these
separate).

## 4. Termux + frida-server — device-side dynamic analysis

The phone can run the whole dynamic stack alone: Termux (or a plain root shell) hosts
`frida-server`, and scripts run through Termux's own Python.

- **frida-server version must match the PC-side frida tooling** when the PC is also in the loop
  (`dynamic-frida.md` owns this). Device-only operation still needs a matching `frida` client in
  Termux.
- **Disguise the server when the target hunts it**: a renamed binary and a non-default port are
  the minimum; a detection-savvy target scans process names and default ports. The reference
  environment carried renamed server copies from prior work — the technique is standard, and the
  detection mechanics are `kernel-and-environment-hardening.md`.
- **32/64-bit**: a `zygote64_32` device runs both ABIs; make sure the frida-server architecture
  matches the process you are attaching to (`environment.md` §which architecture is actually
  executing).
- Keep sessions simple: attach-mode on a hardened target inherits every §1 problem of
  `kernel-and-environment-hardening.md`; prefer spawn, and prefer `spawn_patch_detach.py`-style
  patch-then-detach when you only need a memory fix to stick.

## 5. On-device forensics — where the data is

Rooted-phone data inspection does not need a PC round-trip. The full layout, formats and
ownership rules live in `runtime-data.md` (DataStore/MMKV/SQLite paths, `chown`/`restorecon`
after restores, the "app rewrites your edit" decision tree) — on device, MT Manager's file
browser with root covers the same reads, and Termux covers scripted pulls. The two on-device
cautions that most often bite: edit files **only with the app force-stopped** (the in-memory
copy wins otherwise), and re-check ownership after any reinstall (the uid increments).

## Checklist

- [ ] Chose the workbench deliberately: MT (on-device, fast) vs PC (scriptable, deep) — not by habit
- [ ] MCP started in MT's UI and probed (`mt_mcp_probe.py` exits 0) before planning agent-driven edits
- [ ] MCP plans respect the three official constraints (no Java decompile, arsc entries-only, `.so` static-only)
- [ ] LSPosed modules verified merged (`/data/adb/modules/`, not `modules_update/`) before testing
- [ ] frida-server architecture matches the target process; disguised if the target scans
- [ ] Data edits done with the app stopped; ownership fixed after reinstalls
