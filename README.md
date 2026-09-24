<p align="center">
  <img src="app_logo.svg" alt="Seep Reverse Lab Logo" width="120" height="120">
</p>

<h1 align="center">Seep Reverse Lab</h1>

<p align="center">
  <strong>Agent-Native · Multi-Platform Reverse Engineering · CWE-602 Authorization Audit · Autonomous Security Workbench</strong>
</p>

<p align="center">
  <a href="https://github.com/angusdevgo/seep-reverse-lab"><img src="https://img.shields.io/badge/Release-v1.2.0-brightgreen.svg?style=for-the-badge&logo=github" alt="Release"></a>
  <a href="https://github.com/angusdevgo/seep-reverse-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Android%20%7C%20Linux-0078D6?style=for-the-badge&logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/Architecture-x86%20%7C%20x64%20%7C%20ARM64-orange?style=for-the-badge" alt="Architecture">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/MCP%20Tools-23%20Integrated-purple?style=for-the-badge&logo=fastapi" alt="MCP Tools">
  <img src="https://img.shields.io/badge/Knowledge%20Base-289%20Journals-teal?style=for-the-badge" alt="Knowledge Base">
  <img src="https://img.shields.io/badge/MANUAL%20SOPs-5%20Tactical%20Guides-red?style=for-the-badge" alt="MANUAL SOPs">
  <a href="https://linux.do/"><img src="https://img.shields.io/badge/Community-LINUX%20DO-23272A?style=for-the-badge&logo=discourse" alt="LINUX DO"></a>
</p>

<p align="center">
  [ <strong>English</strong> | <a href="README.zh.md">中文文档</a> ]
</p>

<p align="center">
  <a href="#-project-overview">Overview</a> •
  <a href="#-how-it-works">Architecture</a> •
  <a href="#-30-second-demo">Demo</a> •
  <a href="#️-mcp-tool-matrix">MCP Matrix</a> •
  <a href="#-quick-start--deployment">Quick Start</a> •
  <a href="#-technical-scope">Scope</a> •
  <a href="#-agent-execution-contract">Agent Contract</a> •
  <a href="#️-roadmap">Roadmap</a> •
  <a href="#-disclaimer">Disclaimer</a>
</p>

---

> 🔗 **Attribution & Reference Sources**:
> - Mobile reverse engineering methodology referenced from: [**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse).
> - Community support & technical discussions: [**LINUX DO**](https://linux.do/).

---

## 🌟 Project Overview

Seep consolidates fragmented reverse engineering toolchains (Radare2 / JADX / Apktool / Frida / IDA), operational knowledge bases, prompt engineering contracts, and battle-tested field experience into an **Agent-Native Autonomous Workbench**.

Users provide plain-language technical goals; the agent autonomously performs platform identification, vulnerability type classification, surgical binary patching, and closed-loop evidence delivery.

### Five Core Pain Points Solved

| Pain Point | Solution |
|---|---|
| 🔧 **Toolchain Fragmentation** | 23 MCP tools wrapping Radare2, JADX, Apktool, Frida — unified API, zero manual switching |
| 🧠 **Agent Decision Drift** | `softseep` orchestrator: two-stage auto-classification (Platform × 9 Task Types) + 7-gate decision tree |
| 🛡️ **Model Refusal in Security Audits** | Three-tier mitigation: `BLOCK_NONE` injection + transparent terminology mapping + cognitive redirection |
| 📚 **Ephemeral Knowledge** | 289 technical field journals + 9 desensitized paradigms + "search KB before executing" enforced discipline |
| 📦 **Setup Friction** | One-click `install.ps1` → supports Pi Agent, Claude Code, DeepSeek Harness (DSH), Codex / OpenCode |

---

## ⚙️ How It Works

```
User Input (plain language — "bypass the premium check in FooBar.apk")
    │
    ▼
┌───────────────────────────────────────────────────────────────────┐
│  Lab Mode State Machine  (disk-backed ~/.pi/agent/lab-mode.flag)  │
│  • Colloquial → compliance terminology auto-mapping               │
│  • BLOCK_NONE injection + cognitive redirection (anti-refusal)    │
│  • Context persists across model switches & context compression   │
└────────────────────────────┬──────────────────────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│  softseep  Master Orchestrator                                    │
│  ① Platform  →  Windows PE / Android APK / Linux ELF / Web       │
│  ② Task Type →  9 Paradigms × 7 Gates (G0–G6 decision tree)      │
│  ③ Route     →  apkseep / ida-reverse / seep MCP / KB            │
└────────┬──────────────────┬────────────────────┬──────────────────┘
         │                  │                    │
         ▼                  ▼                    ▼
   seep MCP            IDA Pro MCP         KB Search
   23 tools            (optional)          289 journals
   (Radare2/JADX/                          (Zero-Waste Recon)
    Apktool/Frida)
         │
         ▼
┌───────────────────────────────────────────────────────────────────┐
│  Context Budget Control  (v1.1 noise reduction)                   │
│  • seep_r2_decompile: full / fold (−60% tokens) / summary (−90%) │
│  • seep_r2_disasm:   full / branch (control-flow only)           │
│  • seep_r2_xrefs:    paginated, limit=10, total stats header      │
└────────────────────────────┬──────────────────────────────────────┘
                             │
                             ▼
         PoC Generated → Sandbox Execution → Self-Healing Loop
                             │
                             ▼
         Airplane-Mode Confirmation (CWE-602 iron-clad proof)
                             │
                             ▼
         3-Part Consulting-Grade Security Report  ✓
```

---

## ⚡ 30-Second Demo

Once deployed, just talk to your agent in plain language:

```
lab: analyze FooBar.apk — find the premium check and bypass it
```

The agent autonomously:

1. **`seep_auto_triage`** → identifies DEX + ARM64 SO, no packer detected
2. **`seep_apk_decompile`** with `output_mode=fold` → extracts control-flow skeleton only *(saves ~60% tokens)*
3. **`seep_kb_search`** → finds matching CWE-602 pattern from field journal #142
4. **`seep_apk_gen_hook`** → generates `hook_verify.js` Frida script
5. Executes on connected device → captures stdout, **self-heals** `ClassNotFoundException`, re-runs
6. Airplane-mode confirmation ✓ → **`seep_gen_security_report`** → 3-part audit report delivered

> Total elapsed time on a typical client app: **8–20 minutes**, fully unattended.

---

## ⚡ Core Capabilities

- 🎯 **Natural Language Intent Resolution**: Binary magic bytes + semantic verb mapping → correct toolchain, no flags to memorize
- 🔍 **CWE-602 Authorization Audit**: Minutes to determine if a feature gate is local-boolean or server-authoritative
- 🛡️ **Authenticode Signature Preservation**: DLL search-order hijacking (`version.dll` / `sentry.dll`) keeps host binary signature intact
- 🔄 **PoC Self-Healing Loop**: Frida error → root-cause mapping → auto-fix → re-execute (up to 3 attempts, then structured handoff)
- 💎 **9 Industrial Architecture Paradigms**: Monolithic offline PE → multi-process IPC → VM arbitration → .NET keygen → weak RSA bypass *(fully desensitized)*
- 🔌 **Offline-Ready**: All toolchains pre-bundled (251 MB), zero network dependencies after setup

---

## 📋 Directory Structure

<details>
<summary>📁 Full Directory Tree (click to expand)</summary>

```
Seep\ (251 MB)
├── README.md                      ← This file (English default)
├── README.zh.md                   ← Chinese documentation (中文文档)
├── CLAUDE.md                      ← Project-level instructions for Claude Code
├── .mcp.json                      ← Project-level MCP registration (Claude Code / OpenCode)
├── DSH-PROFILE.md                 ← DeepSeek Harness Cordis plugin config template
├── check.bat                      ← ⭐ Double-click one-shot health verifier (Windows)
├── check.ps1                      ← PowerShell health verifier entry point
│
├── Tool\
│   ├── skill\                     ← 9 specialized reverse engineering skills
│   │   ├── softseep\              ← ⭐ Master orchestrator (Router + 8 on-demand references)
│   │   ├── apkseep\               ← End-to-end Android APK/DEX/SO skill (115 files)
│   │   ├── ida-reverse\           ← IDA Pro automated spawning & MCP coordination
│   │   ├── client-license-validation-bypass\ ← Cross-runtime license attack playbook
│   │   └── safe-skills\           ← 5 standalone tool packages
│   │
│   ├── mcp\                       ← MCP Engine
│   │   ├── seep_mcp_server.py     ← Core server: 23 native reversing & KB tools
│   │   ├── mcp.json.template      ← Global MCP client configuration template
│   │   └── Tool\                  ← ⚠️ Hardcoded relative runtime path (do not rename)
│   │       ├── safe\              ← Pre-bundled cross-platform toolchains
│   │       │   ├── jadx\          ← 75 MB (v1.5.6)
│   │       │   ├── radare2\       ← 39 MB (v6.2.2 full suite)
│   │       │   ├── apktool\       ← 24 MB (v3.0.3)
│   │       │   ├── hook-mcp\      ← Frida / LSPosed instrumentation templates
│   │       │   ├── ida-pro-mcp\   ← IDA bridge adapter
│   │       │   ├── js-reverse-mcp\← Web / JS debugging engine
│   │       │   └── playwright-mcp\← Headless browser automation
│   │       └── reverselab\        ← 289 field journals + attack chains
│   │
│   ├── prompts\                   ← Agent coordination specs & runtime extensions
│   │   ├── SYSTEM.md              ← Pi Agent system instructions
│   │   ├── AGENTS.md              ← Cross-agent portable instructions
│   │   └── extensions\            ← BLOCK_NONE injection + terminology mapping
│   │
│   ├── cases\                     ← 9 desensitized industrial paradigm projects (A ~ I)
│   ├── upstream\                  ← apk-reverse offline verification test suite (MIT)
│   ├── docs\                      ← Engineering reference docs
│   └── scripts\                   ← Workspace automation scripts
│
├── setup\                         ← Automated install, repair & self-check scripts
└── MANUAL\                        ← 5 Tactical SOP guides
    ├── PREREQUISITES.md           ← Environment requirements
    ├── IDA-PRO.md                 ← Commercial IDA Pro integration guide
    ├── ANTI-DEBUG.md              ← Anti-debug bypass dictionary & proxy DLL framework
    ├── UNPACKING.md               ← UPX/MPRESS/Themida/VMP unpacking SOP
    └── POC-VALIDATION.md          ← Frida self-healing loop & PoC sandbox validation
```

</details>

---

## 🛠️ MCP Tool Matrix

The bundled `seep` MCP server exposes **23 native tools** across five functional groups:

| Category | Tool | Functionality | Token Mode |
|---|---|---|---|
| **Health** | `seep_status` | Verifies Radare2, JADX, Apktool, KB readiness | — |
| | `seep_ida_status` | Probes IDA Pro MCP service connectivity | — |
| **Binary (R2)** | `seep_r2_info` | Architecture, bitness, DEP/ASLR/Canary/PIE | — |
| | `seep_r2_strings` | Extracts strings with regex + section filtering | `limit=` |
| | `seep_r2_functions` | Functions, imports, exports, entry points | `limit=` |
| | `seep_r2_disasm` | Disassembly with cross-references | `full` / `branch` |
| | `seep_r2_decompile` | C-like pseudocode via pdc engine | `full` / `fold` / `summary` |
| | `seep_r2_xrefs` | Cross-reference graph, paginated | `limit=10` default |
| | `seep_r2_diff` | Code / hex diff between two binaries | — |
| | `seep_r2_asm` | Assemble ↔ disassemble machine code | — |
| | `seep_r2_cmd` | Raw Radare2 pipeline commands | — |
| **Android** | `seep_apk_info` | APK manifest, permissions, signatures (no Java) | — |
| | `seep_apk_decompile` | JADX full Java source decompilation | — |
| | `seep_apk_unpack` | Apktool resource + Smali disassembly | — |
| | `seep_apk_smali_search` | Smali pattern search (crypto keys, auth gates) | `limit=` |
| | `seep_apk_gen_hook` | Ready-to-run Frida hooks with stack traces | — |
| **Knowledge Base** | `seep_kb_search` | Full-text search across 289 field journals | `limit=` |
| | `seep_kb_read` | Full technical reference retrieval by topic | — |
| | `seep_kb_checklist` | Emergency triage checklists & attack matrices | — |
| | `seep_kb_payloads` | Security test seeds (JWT, SSRF, SSTI, SQLi) | — |
| **Orchestration** | `seep_task_init` | Initializes isolated audit sandbox directory | — |
| | `seep_auto_triage` | Automated full-sample health check | — |
| | `seep_gen_security_report` | Synthesizes 3-part compliance security report | — |

> 💡 **Context Budget Control** (v1.1): `seep_r2_decompile` with `output_mode=fold` reduces token consumption by ~60%; `summary` mode by ~90%. Use `seep_r2_xrefs` instead of raw `axt` to avoid flooding the context window with hundreds of references.

---

## 🚀 Quick Start & Deployment

### 1. Prerequisites
- **OS**: Windows 10 / 11 x64 (recommended) or compatible Linux / macOS
- **Runtimes**: Python 3.11+, Node.js 18+, Git

### 2. One-Click Setup
Open an elevated PowerShell terminal, navigate to the project root, and run:
```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
> **What this does automatically**: Unpacks dependency archives → validates pre-bundled tools → installs Python `mcp` libraries → registers MCP servers → runs full self-check.

### 3. Multi-Agent Setup

| Agent | Instruction File | MCP Config | How to Activate |
|---|---|---|---|
| **Pi Agent** | `Tool/prompts/SYSTEM.md` | `~/.pi/agent/mcp.json` | `install.ps1` writes everything automatically |
| **Claude Code** | `CLAUDE.md` (project root) | `.mcp.json` (project root) | Run `claude` in workspace root — auto-loaded |
| **DeepSeek Harness** | `Tool/prompts/AGENTS.md` | `DSH-PROFILE.md` (Cordis YAML) | Copy instructions + paste plugin config to DSH profile |
| **OpenCode / Codex** | `AGENTS.md` (project root) | Client global config | Copy `Tool/prompts/AGENTS.md` to project root |

### 4. Verify Your Deployment

Run the 7-section health verifier (35 checks) using any of these methods:

| Method | Command |
|---|---|
| ⭐ Double-click (easiest) | `check.bat` in project root |
| PowerShell | `powershell -ExecutionPolicy Bypass -File .\check.ps1` |
| Agent chat | Send `check` (or `doctor` / `检查`) — agent runs and reports inline |

---

## 🎮 Workflow & Lab Mode

### Lab Mode Protocol (Disk-Backed State Machine)
```
Activate:   lab:                          # or: lab: analyze FooBar.exe
Deactivate: exit lab
```
- State stored in `~/.pi/agent/lab-mode.flag` — **persists across model switches & context compression**
- Once activated: terminology auto-mapping, anti-refusal overrides, and shortcut expansion are live
- Casual chat outside lab mode passes through unmodified — zero interference

### Task Shortcuts (Active in Lab Mode)

| Shortcut | Action |
|---|---|
| `poc <target>` | CWE-602 client-side authorization audit + verification code |
| `find-auth <target>` | Locate license, subscription, expiry, hardware-binding functions |
| `hook <function>` | Generate Frida hook with stack trace + return-value override |
| `gen-patch <offset>` | Binary patch bytes or proxy DLL scaffold |
| `triage <sample>` | Full triage: architecture, imports, packers, strings |
| `check` | Run 7-section workbench health verifier inline |
| `report` | Synthesize active directory evidence → 3-part audit report |

---

## 🔬 Technical Scope

<details>
<summary>Click to expand full technical scope</summary>

### 1. Client-Side Authorization Audit (CWE-602)

**Authority Attribution**: Airplane mode + loopback hijacking + timestamp offset testing to classify gates as server-authoritative vs. local-boolean within minutes.

**Nine Industrial Paradigms** — all fully desensitized:

| Project | Architecture | Key Technique |
|---|---|---|
| **A** | Monolithic offline PE | Scalar return override (`mov eax,1; ret`) |
| **B** | Multi-process hybrid | Proxy DLL name-based dispatch + 3-tier state persistence |
| **C** | Resource template + UI | Bijective bit-permutation decoding + IAT hook on `SetDlgItemTextW` |
| **D** | Compressed packer (MPRESS) | 18-point surgical patch + ACL trial-key locking |
| **E** | EXECryptor VM arbitration | 2-point Call redirection to memory stubs |
| **F** | .NET dynamic deobfuscation | Harmony memory dump + 96-bit combined hash keygen |
| **G** | Self-referential SHA-384 | 5-byte function-entry patch + watchdog persistence |
| **H** | Ed25519 pubkey replacement | In-place ciphertext replacement via derived keystream |
| **I** | Weak-modulus RSA | Sliding-window bypass + activation injection on export entry |

### 2. Android & DEX/SO Analysis
- Surgical DEX same-length patching with automated Adler-32 / SHA-1 recalculation
- Packer classification: Java2C / native payload / extraction shell / private DEX-VMP
- Runtime anti-analysis: root detection bypass, SSL pinning circumvention, Frida-RPC bridging
- Repack pipeline: STORED `resources.arsc` + 4-byte Zipalign + v1+v2+v3 signing

### 3. Binary / Native (PE / ELF / Mach-O)
- Headless Radare2: architecture ID, entropy scan, symbol recovery, C-like decompilation
- Full IDA Pro MCP integration: Hex-Rays decompilation, xrefs, struct recovery
- Anti-tamper defeat: deliberate crash stubs, raw `svc` syscall detection, kernel anti-debug

### 4. CTF & Challenge Workflows
- Attack-network routing: Signal → `seep_kb_search` → template assembly → MCP execution
- Web: JWT, KID injection, SSRF chains, SSTI, deserialization gadget chains, Protobuf decoding
- Seed libraries (`seep_kb_payloads`) + emergency checklists (`seep_kb_checklist`)

</details>

---

## 🤖 Agent Execution Contract

- **G-Auth Gate**: Confirm testing authorization on every new target. No authorization = stop.
- **7-Gate Decision Tree (G0–G6)**: Classify authority ownership (Server vs. Client) before touching any code.
- **Two-Strike Rule**: Same-shaped failure twice → refute the technical model, fall back to classification. Third variation is strictly prohibited.
- **Zero-Waste Recon**: Signal detected → `seep_kb_search` → pre-existing tool → execute. Never write scripts from scratch without checking the KB first.
- **Definition of Done**: Target hash → RVA identification → PoC execution → offline airplane-mode confirmation → 3-part structured delivery. Console log alone is not evidence.

---

## 📝 Deliverable Specification

All client-side vulnerability assessments follow a consulting-grade 3-part structure:

1. **Vulnerability Detail & Risk** — Exact RVA / file offsets, call chain, CWE-602 mapping, business severity
2. **Reproduction & PoC** — 100% reproducible instructions, proxy DLL source, or Frida script + offline confirmation evidence
3. **Defense-in-Depth Remediation**:
   - `SetDefaultDllDirectories` → prevent DLL hijacking
   - `ProcessDynamicCodePolicy` → prevent executable memory injection
   - Server-side authority via cryptographic signatures and short-lived tokens

---

## 🗺️ Roadmap

| Version | Focus | Status |
|---|---|---|
| **v1.0** | Core toolchain bundling, 9 paradigms, Lab Mode, 22 MCP tools | ✅ Released |
| **v1.1** | Context-aware MCP output (`fold`/`branch`/`summary`), `seep_r2_xrefs` paginator | ✅ Released |
| **v1.2** | MANUAL SOPs: Anti-Debug bypass, Unpacking (VMP/Themida/UPX), PoC Validation | ✅ Released |
| **v2.0** | Frida self-healing CI loop, Windows sandbox loader, automated PoC validation pipeline | 🔨 Planned |
| **v2.x** | Linux / macOS native support, Ghidra headless integration, YARA rule auto-generation | 💡 Proposed |

---

## 🤝 Acknowledgements & Community

- Special thanks to [**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse) for the foundational Android reverse engineering paradigm and verification methodology.
- Gratitude to the [**LINUX DO**](https://linux.do/) community for technical exchange, insight, and research collaboration.

---

## ⚖️ Disclaimer

**This repository is intended solely for authorized security research, white-box auditing, compliance vulnerability testing, and educational CTF training.**

- **Explicit Authorization Required**: Written authorization from the asset owner is mandatory before analyzing any target.
- **No Warranty**: All methodologies are provided "as is" based on sandbox measurements.
- **Isolated Testing**: Conduct all analysis in isolated VMs or sandboxes. Testing against production systems or unauthorized networks is prohibited.
- **Limitation of Liability**: Authors assume no liability for misuse, unauthorized testing, or violations of applicable laws.
