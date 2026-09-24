<p align="center">
  <img src="app_logo.svg" alt="Seep Reverse Lab Logo" width="128" height="128">
</p>

<h1 align="center">Seep Reverse Lab</h1>

<p align="center">
  <strong>Agent-Native Multi-Platform Reverse Engineering · Authorization Audit (CWE-602) · Autonomous Security Workbench</strong>
</p>

<p align="center">
  <a href="https://github.com/angusdevgo/seep-reverse-lab"><img src="https://img.shields.io/badge/Release-v1.0.0-brightgreen.svg?style=for-the-badge&logo=github" alt="Release"></a>
  <a href="https://github.com/angusdevgo/seep-reverse-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Android%20%7C%20Linux-0078D6?style=for-the-badge&logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/Architecture-x86%20%7C%20x64%20%7C%20ARM64-orange?style=for-the-badge" alt="Architecture">
  <img src="https://img.shields.io/badge/MCP%20Tools-22%20Integrated-purple?style=for-the-badge&logo=fastapi" alt="MCP Tools">
  <a href="https://linux.do/"><img src="https://img.shields.io/badge/Community-LINUX%20DO-23272A?style=for-the-badge&logo=discourse" alt="LINUX DO"></a>
</p>

<p align="center">
  [ <strong>English</strong> | <a href="README.zh.md">中文文档</a> ]
</p>

<p align="center">
  <a href="#-project-overview--problem-statement">Overview</a> •
  <a href="#-core-capabilities-what-it-is-good-at">Capabilities</a> •
  <a href="#-directory-structure">Structure</a> •
  <a href="#-technical-scope">Scope</a> •
  <a href="#️-mcp-tool-matrix">MCP Matrix</a> •
  <a href="#-quick-start--deployment">Quick Start</a> •
  <a href="#-agent-execution-contract">Agent Contract</a> •
  <a href="#-acknowledgements--community">Community</a> •
  <a href="#-disclaimer">Disclaimer</a>
</p>

---

> 🔗 **Attribution & Reference Sources**:
> - Core mobile reverse engineering and verification methodology referenced from the upstream benchmark project: [**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse) (full upstream mirror and offline verification test suite bundled under [`Tool/upstream/apk-reverse/`](./Tool/upstream/apk-reverse/)).
> - Community support & technical exchange: [**LINUX DO**](https://linux.do/) (Genuine, Friendly, United, Professional Technical Community).

---

## 🌟 Project Overview & Problem Statement

Seep consolidates fragmented reverse engineering toolchains (Radare2 / JADX / Apktool / Frida / IDA), operational knowledge bases, prompt engineering contracts, and battle-tested field experience into an **Agent-Native Autonomous Workbench**.

Users provide plain-language technical goals; the agent autonomously performs platform identification, vulnerability type classification, surgical binary patching, and closed-loop evidence delivery.

### Five Core Pain Points Solved:
- 🚀 **Toolchain Fragmentation**: Traditional reverse engineering requires manual switching across 7+ disparate tools scattered across different paths. Seep bundles core toolchains and exposes them via a unified Model Context Protocol (MCP) server.
- 🧠 **Agent Decision Drift**: Confronted with obfuscated binaries or unknown APKs, LLMs frequently get trapped in trial-and-error rabbit holes. The `softseep` orchestrator implements automatic two-stage classification (Platform: Windows/Android/Linux/Web × Task Type: 9 categories) for deterministic routing.
- 🛡️ **Model Refusal in Security Audits**: Authorized white-box audits and reversing tasks frequently trigger provider safety filters. Seep implements a three-tier mitigation architecture: request-level `BLOCK_NONE` payload injection, transparent colloquial-to-formal security terminology mapping, and reasoning-level cognitive redirection.
- 📚 **Ephemeral Knowledge & Lack of Memory**: Most reversing tasks start from scratch. Seep bundles 9 desensitized industrial architecture paradigms (Project A through Project I) and 289 technical field journals, enforcing the discipline: *search knowledge base before executing commands*.
- 📦 **High Environment Setup Friction**: Manual toolchain configuration for new machines or interns is error-prone. Seep provides an automated one-click installation script supporting **Pi Agent**, **Claude Code**, **DeepSeek Harness (DSH)**, and **Codex / OpenCode**.

---

## ⚡ Core Capabilities (What It Is Good At)

- 🎯 **Natural Language Intent Resolution & Two-Stage Auto-Classification**: Users do not need to memorize flags or menus. Commands like "analyze license validation", "locate card-key check", or "suppress ad gating" are mapped using binary file signatures (magic bytes, PE headers, imports) and semantic verbs to automatically converge on the correct toolchain.
- 🔍 **Client-Side Authorization Audit (CWE-602)**: Determines within minutes whether a feature gate is driven by local booleans/timestamps or by server-authoritative signatures and remote asset delivery. Prevents the classic "fake VIP trap" where forcing local booleans leads to blank screens or unhandled exceptions when requesting missing server-side data.
- 🛡️ **Authenticode Digital Signature Preservation**: For signed Windows binaries, disk-level hex patching is strictly prohibited. Seep routes through DLL search-order hijacking (proxying system libraries like `version.dll` or `sentry.dll`) to apply in-memory patches during the loading phase, keeping the host binary's Authenticode signature 100% intact.
- 💎 **Comprehensive Coverage of 9 Industrial Paradigms**:
  - In-memory patching of monolithic offline binaries
  - IPC message filtering in multi-process architectures
  - Display-layer string forgery via IAT hooking (`SetDlgItemTextW`)
  - MPRESS packing analysis, 18-point surgical patching, and Windows ACL trial-period freezing
  - EXECryptor VM concentrated arbitration bypass via 2-point Call redirection
  - .NET dynamic IL extraction via Harmony memory dumping and 96-bit combined hash keygen reconstruction
  - Self-referential hash check bypass and startup watchdog guards
  - In-place Ed25519 public key ciphertext replacement
  - Sliding-window validation bypass on weak-modulus RSA
- 🔌 **Pre-Packaged Offline Execution**: Core tool suites (Radare2, JADX, Apktool, Playwright engine, IDA bridge adapter) are pre-bundled on disk, ready to run inside fully isolated sandboxes with zero external network dependencies.

---

## 📋 Directory Structure

Seep enforces strict progressive disclosure and modular separation of concerns:

```
Seep\ (251 MB)
├── README.md                      ← Global architecture and documentation (Default: English)
├── README.zh.md                   ← Chinese documentation (中文文档)
├── CLAUDE.md                      ← Project-level native instructions for Claude Code
├── .mcp.json                      ← Project-level MCP server registration (Claude Code / OpenCode)
├── DSH-PROFILE.md                 ← DeepSeek Harness Cordis plugin configuration template
│
├── Tool\                          ← Core workbench assets
│   ├── skill\                     ← 9 specialized reverse engineering skills
│   │   ├── softseep\              ← ⭐ Master orchestrator skill (Router + 8 on-demand reference guides)
│   │   ├── apkseep\               ← End-to-end Android APK/DEX/SO reverse engineering skill (115 files)
│   │   ├── ida-reverse\           ← IDA Pro automated spawning, headless probing, and MCP coordination
│   │   ├── client-license-validation-bypass\ ← Cross-runtime license / card-key validation attack playbook
│   │   └── safe-skills\           ← 5 standalone tool packages (General RE / APK diff / Radare2 / JS RE / IDA)
│   │
│   ├── mcp\                       ← Tool service layer (MCP Engine)
│   │   ├── seep_mcp_server.py     ← Core MCP server exposing 22 low-level reversing & KB tools
│   │   ├── mcp.json.template      ← Global MCP client configuration template
│   │   └── Tool\                  ← ⚠️ Hardcoded relative runtime path required by seep MCP
│   │       ├── safe\              ← Pre-bundled cross-platform reversing toolchains
│   │       │   ├── jadx\          ← 75 MB (v1.5.6 clean optimized build)
│   │       │   ├── radare2\       ← 39 MB (v6.2.2 full binary suite)
│   │       │   ├── apktool\       ← 24 MB (v3.0.3 runtime environment)
│   │       │   ├── hook-mcp\      ← 331 KB (Frida / LSPosed dynamic instrumentation templates)
│   │       │   ├── ida-pro-mcp\   ← 28 MB (IDA bridge adapter dependencies)
│   │       │   ├── js-reverse-mcp\← 61 MB (Web / JS dynamic debugging engine)
│   │       │   └── playwright-mcp\← 8.8 MB (Headless browser automation runtime)
│   │       └── reverselab\        ← Security knowledge base (687 files, including 289 field journals)
│   │
│   ├── prompts\                   ← Agent coordination specifications and runtime extensions
│   │   ├── SYSTEM.md              ← Pi Agent system instructions (Lab state machine, anti-refusal rules, SOP)
│   │   ├── AGENTS.md              ← Cross-agent portable instructions (Codex, OpenCode, DSH)
│   │   └── extensions\            ← Runtime interceptors (BLOCK_NONE injection, automatic term mapping)
│   │
│   ├── cases\                     ← 9 desensitized industrial paradigm reference projects (Project A ~ I)
│   │   ├── Project A\ (Offline PE) ├── Project B\ (Multi-Process) ├── Project C\ (Resource Template & IAT Hook)
│   │   ├── Project D\ (Packer/ACL) ├── Project E\ (VM Redirect)   ├── Project F\ (.NET Reversible Keygen)
│   │   ├── Project G\ (Self-Ref)   ├── Project H\ (Pubkey Repl)   ├── Project I\ (Weak RSA Entry Patch)
│   │
│   ├── upstream\                  ← Upstream verification layer (apk-reverse offline test suite)
│   ├── docs\                      ← Engineering reference docs (MCP setup, download origins, dependency map)
│   └── scripts\                   ← Workspace automation scripts (Case initialization, signing, IDA spawning)
│
├── setup\                         ← Automated installation, dependency setup, and self-check scripts
└── MANUAL\                        ← Infrastructure prerequisites and commercial licensing guide (IDA Pro, etc.)
```

---

## 🔬 Technical Scope

Seep categorizes software protection, virtualized execution, and authorization schemes into four core technical domains:

### 1. CTF & Challenge Workflows
- **Attack-Network Routing**: Driven by the integrated `reverselab` framework: *Signal Detection → Knowledge Base Search (`seep_kb_search`) → Template Assembly → MCP Tool Execution*.
- **Web Targets & Non-REST Protocols**: JWT signature attacks, KID injection, SSRF chains, SSTI, prototype pollution, deserialization gadget chains, and schema-free Protobuf decoding.
- **Automated Competitions**: Standardized exploit seed libraries (`seep_kb_payloads`) and emergency triage checklists (`seep_kb_checklist`) eliminate hand-writing repetitive verification scripts under competition pressure.

### 2. Client-Side Authorization & License Auditing (CWE-602)
- **Authority Attribution Model**: Differentiates server-authoritative gates from client-side boolean checks using airplane mode isolation, loopback hijacking (`netsh interface ipv4 add address`), and timestamp offset testing.
- **Nine Architectural Paradigms**:
  - **Project A (Monolithic Offline)**: Scalar return value override (`mov eax, 1; ret`).
  - **Project B (Multi-Process Hybrid)**: Sub-process name-based proxy DLL dispatching and three-tier state persistence across UI and background services.
  - **Project C (Resource Template & UI Forgery)**: Bijective bit-permutation mask decoding and IAT hooking on `SetDlgItemTextW`.
  - **Project D (Compressed Packer & Multi-Strategy)**: MPRESS unpacking, 18-point binary patching, digital certificate directory truncation, and Windows ACL trial-key locking.
  - **Project E (Virtualized Arbitration)**: Bypass EXECryptor VM verification via 2-point Call redirection to memory stubs.
  - **Project F (.NET Dynamic Deobfuscation)**: Harmony-assisted memory dumping of decrypted IL, 96-bit combined hash recovery, and offline keygen generation.
  - **Project G (Self-Referential Verification)**: Identifies self-referential SHA-384 payload hashing and applies 5-byte function-entry patching with login watchdog persistence.
  - **Project H (In-Place Public Key Replacement)**: Replaces embedded Ed25519 public key ciphertext within binary using derived keystreams to sign arbitrary payloads.
  - **Project I (High-Order Digital Signature Bypass)**: CNG structure analysis, weak-modulus RSA sliding window identification, and activation injection on export entry points.

### 3. Android & DEX/SO Deep Analysis
- **Surgical DEX Patching**: Same-length byte patching (avoids method rebuilding and offset shifts) and automated recalculation of DEX header Adler-32 checksum and SHA-1 signatures.
- **Packer Diagnostics**: Clear classification tree distinguishing Java2C, native payload shells, extraction shells (trivial-body ratio metric), and private DEX-VMP bytecode.
- **Runtime Anti-Analysis Defeat**: Root detection bypass, multi-layer SSL Pinning circumvention, Native-layer Frida hooking, and Frida-RPC service bridging.
- **Repack & Align Pipeline**: Automated repacking enforcing `resources.arsc` STORED status, 4-byte Zipalign boundary alignment, and v1+v2+v3 digital signing.

### 4. Binary Disassembly & Native Reverse Engineering (PE/ELF/Mach-O)
- **Multi-Platform Static Analysis**: Headless Radare2 execution for architecture identification, section entropy scanning, symbol recovery, and C-like decompilation. Full IDA Pro MCP integration for Hex-Rays decompilation, cross-references, and struct recovery.
- **Anti-Tamper & Suicide Logic Defeat**: Analysis of deliberate crashes (e.g. `fault addr 0x4` null-pointer stubs), raw `svc` syscall detection, and kernel-level anti-debugging. Enforces the rule: *neutralize termination paths by returning clean exit codes, never by hanging execution in infinite loops*.

---

## 🛠️ MCP Tool Matrix

The bundled `seep` MCP server exposes **22 native tools** across five functional groups:

| Category | Tool Identifier | Functionality |
|---|---|---|
| **Health Checks** | `seep_status` | Verifies readiness of Radare2, JADX, Apktool, and local knowledge base |
| | `seep_ida_status` | Probes connectivity to the remote IDA Pro MCP service |
| **Binary Analysis (R2)** | `seep_r2_info` | Reads binary architecture, bitness, endianness, and security mitigations (DEP/ASLR/Canary/PIE) |
| | `seep_r2_strings` | Extracts printable strings with regex and section filtering |
| | `seep_r2_functions` | Enumerates binary functions, import/export tables, and entry points |
| | `seep_r2_disasm` | Generates disassembly listings with cross-references and line markers |
| | `seep_r2_decompile` | Invokes decompiler engine to produce C-like pseudocode |
| | `seep_r2_diff` | Computes code-level or hex-level differences between two binaries |
| | `seep_r2_asm` | Assembles assembly instructions to machine code or disassembles raw hex |
| | `seep_r2_cmd` | Executes arbitrary low-level Radare2 pipeline commands |
| **Android RE** | `seep_apk_info` | Parses APK manifest, declared components, permissions, and signatures without Java |
| | `seep_apk_decompile` | Orchestrates JADX engine to output deobfuscated Java source projects |
| | `seep_apk_unpack` | Disassembles APK resources and Smali code trees via Apktool |
| | `seep_apk_smali_search`| Rapidly searches for crypto keys, API routes, or gate checks in Smali |
| | `seep_apk_gen_hook` | Generates ready-to-run Frida hooks with stack traces and argument overrides |
| **Knowledge Base** | `seep_kb_search` | Full-text searches across 289 field journals, returning actionable code and attack chains |
| | `seep_kb_read` | Retrieves full technical reference documents by topic |
| | `seep_kb_checklist` | Outputs emergency operational checklists and attack matrixes |
| | `seep_kb_payloads` | Retrieves security test payload seeds (JWT, SSRF, SSTI, SQLi, deserialization) |
| **Orchestration** | `seep_task_init` | Initializes an isolated, audit-compliant sandbox directory for new targets |
| | `seep_auto_triage` | Performs automated full-sample health check on unknown binaries |
| | `seep_gen_security_report`| Synthesizes collected findings into a 3-part structured compliance security report |

---

## 🚀 Quick Start & Deployment

### 1. Prerequisites
- **Operating System**: Windows 10 / 11 x64 (Recommended) or compatible Linux / macOS.
- **Runtimes**: Python 3.11+, Node.js 18+, Git.

### 2. One-Click Setup
Open an elevated terminal (PowerShell as Administrator on Windows), navigate to `setup/`, and run:
```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
> **What the script does automatically**: Unpacks pre-compressed dependency archives (`node_modules.zip` / `venv.zip`) → Validates pre-bundled Jadx/R2 tools → Installs Python `mcp` protocol libraries → Registers MCP servers in the agent client → Performs full environment self-checks.

### 3. Multi-Agent Setup Guide

| Agent Platform | Instruction File | MCP Configuration | Setup Procedure |
|---|---|---|---|
| **Pi Agent** | `Tool/prompts/SYSTEM.md` | `~/.pi/agent/mcp.json` | Running `install.ps1` automatically writes user configs and registers skills |
| **Claude Code** | `CLAUDE.md` (Project root) | `.mcp.json` (Project root) | Run `claude` in the workspace root; native project-level config loads automatically |
| **DeepSeek Harness (DSH)** | `Tool/prompts/AGENTS.md` | `DSH-PROFILE.md` (Cordis YAML) | Copy generic instructions to workspace root and paste plugin config into DSH profile |
| **OpenCode / Codex** | `AGENTS.md` (Project root) | Client global config | Copy `Tool/prompts/AGENTS.md` to project root |

---

## 🎮 Workflow & Lab Mode Protocol

### 1. Lab Mode Protocol (Disk-Backed State Machine)
To maintain a strict boundary between normal casual conversation and sensitive reverse engineering audits, Seep uses a disk-backed state machine independent of LLM context window limits:
- **Activate Lab Mode**: Send the following command to the agent:
  ```
  lab:
  ```
  *(or combine with a task: `lab: analyze target binary FooBar.exe`)*  
  The agent generates a local state marker (`~/.pi/agent/lab-mode.flag`), activating security terminology translation, cognitive redirection, and anti-refusal overrides. **You do not need to repeat this prefix in subsequent messages.**
- **Deactivate Lab Mode**: Send `exit lab`. The agent immediately unlinks the state file and returns to normal conversation mode.

### 2. Task Shortcuts (Active in Lab Mode)
- `poc <target>`: Triggers client-side authorization audit (CWE-602) and outputs verification code.
- `find-auth <target>`: Searches for license, subscription, expiration, and hardware-binding functions.
- `hook <function>`: Generates Frida hooks with stack tracing and return-value replacement.
- `gen-patch <offset>`: Outputs binary patch byte sequences or proxy DLL scaffolding.
- `triage <sample>`: Runs initial triage covering architecture, imports, packers, and strings.
- `report`: Synthesizes evidence in the active directory and exports a standardized 3-part audit report.

---

## 🤖 Agent Execution Contract (How an Agent Consumes This)

This workspace is structured as a set of **executable gates and strict operational constraints**:

- **Mandatory Gate Sequence (G-Auth & G0–G6)**: On any new target, the agent's first step is to confirm testing authorization. It then applies the *Four Core Questions* to determine authority ownership (Server vs Client) and deliverable form (Patch / Memory Hijack / Keygen / Relay / Payload Carving). If any gate fails, execution stops immediately.
- **Two-Strike Rule**: If an assumption, patch, or exploit path fails twice in the same manner, the agent must treat its technical model as refuted and fall back to classification. A third variation of a twice-failed hypothesis is strictly prohibited.
- **Zero-Waste Recon**: When signals appear (packers, JWT, crypto, drivers, self-referential checks), the agent must query `seep_kb_search` and map to pre-existing MCP tools rather than writing scripts from scratch.
- **Strict Definition of Done**: A clean console log is not evidence of success. "Done" requires a complete evidence chain: Target hashes → RVA identification → PoC execution → Offline airplane-mode confirmation (proving zero server dependency) → 3-part structured delivery report.

---

## 📝 Deliverable Specification

Client-side vulnerability assessments must be delivered using a consulting-grade three-part report structure:

1. **Vulnerability Detail & Risk**: Exact instruction RVA / file offsets and call chain context. Root cause analysis mapping to CWE-602, OWASP MASVS, and business severity ratings.
2. **Reproduction & PoC**: 100% reproducible instructions, proxy DLL source code, or Frida scripts. Documented offline/airplane-mode verification evidence confirming that feature restrictions were bypassed locally without server verification.
3. **Defense-in-Depth Remediation**:
   - **Loading Phase**: Restrict DLL search directories via `SetDefaultDllDirectories` to prevent search-order hijacking.
   - **Runtime**: Enable `ProcessDynamicCodePolicy` to prevent executable memory manipulation.
   - **Architecture**: Enforce server-side authority using cryptographic signatures and short-lived tokens for privileged actions.

---

## 🤝 Acknowledgements & Community

- Special thanks to [**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse) for the foundational Android reverse engineering gating paradigm and verification methodology.
- Gratitude to the [**LINUX DO**](https://linux.do/) community for technical exchange, insight, and research collaboration.

---

## ⚖️ Disclaimer

**This repository, including all documentation, rules, scripts, and sample projects, is intended solely for authorized security research, white-box auditing, compliance vulnerability testing, and educational CTF training.**

- **Explicit Authorization Required**: Users must possess written authorization from the asset owner before analyzing any target binary, client, or system.
- **No Warranty**: All technical methodologies and research notes are provided "as is" based on sandbox measurements, without warranty of fitness for any specific environment.
- **Minimum Impact**: Analysis must be conducted in isolated virtual machines or test sandboxes. Testing against production systems or unauthorized networks is prohibited.
- **Limitation of Liability**: Authors and contributors assume no liability for misuse, unauthorized testing, or violations of applicable laws and regulations.
