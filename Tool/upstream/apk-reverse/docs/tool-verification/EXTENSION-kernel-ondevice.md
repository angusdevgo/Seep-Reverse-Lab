# Extension verification — kernel/environment hardening + on-device tooling

Covers the 2026-09 extension pass that added `references/kernel-and-environment-hardening.md`,
`references/on-device-tooling.md` and `scripts/mt_mcp_probe.py`. Strength labels as defined in
this directory's README: **observed** (exact command + output here), **inferred** (follows from
observed facts, step not executed), **unverified** (assumed or externally reported, not
independently confirmed).

Reference environment for this pass: rooted physical device, Android 11 (API 30), arm64-v8a,
kernel **4.14.186**, Magisk alpha + Zygisk, LSPosed v1.9.2 activated, Zygisk-Assistant v2.1.4
and MoveCertificate v1.6.2 installed (pending reboot merge), MT Manager 2.26.9 installed.

---

## 1. MT APK MCP probe — measured

### 1.1 `scripts/mt_mcp_probe.py` runs and reports correctly

`--help` works (argparse, three options). Observed:

```
$ python skills/apk-reverse/scripts/mt_mcp_probe.py --help
usage: mt_mcp_probe.py [-h] [--url URL] [--timeout TIMEOUT] [--json]
```

Full **observed** output of the probe in the service-down state, with the port forward in place:

```
$ adb forward --list
<serial> tcp:8787 tcp:8787
<serial> tcp:8651 tcp:8651
<serial> tcp:65534 tcp:65534

$ python skills/apk-reverse/scripts/mt_mcp_probe.py
[waiting] MCP server is not answering at http://127.0.0.1:8787/mcp
The MT APK MCP must be started by hand in the MT UI (adb cannot start it):
  1. On the phone: MT Manager -> side drawer -> Tools -> APK MCP -> Start
  ...
exit code 2
```

The failure was localised to the service (not the transport) on the device side — **observed**:

```
$ adb -s <serial> shell "su -c 'netstat -tln | grep 8787 || echo NOT_LISTENING'"
NOT_LISTENING
```

So at pass time: port forward alive, device reachable, MT's MCP service not started in the MT UI
(it requires a manual start that adb cannot perform). The script's designed degraded-mode
behaviour (waiting instructions + exit 2) is therefore **verified by observation**; the online
path (initialize handshake → grouped `mt_apk_*` inventory) is **unverified on this device** — it
was not exercised because the service was never started during the pass. The JSON-RPC shape
(initialize with `protocolVersion 2024-11-05`, `notifications/initialized`, `tools/list`,
`Accept: application/json, text/event-stream`) follows the MCP Streamable HTTP specification and
MT's documented transport; treat the exact response parsing as inferred until a live run.

### 1.2 What was deliberately not done

No attempt was made to start MT's MCP from adb (documented as impossible), and no scripted
tap-driver was built to press the UI button — that is a human step. The probe script doubling as
a "wait until up" check (exit 2 → retry after manual start) is the supported loop.

## 2. Phone-module environment — observed earlier, cited here

These facts were measured in the prior configuration pass and archived in
`tools/_phone-modules/README-手机模块环境.md` and `README-MCP与网络环境.md`; this pass cites them
rather than re-measuring. They count as **observed** (exact commands and outputs exist in those
archives):

- LSPosed v1.9.2 (7024) activation: log lines `ZygiskCompanion: welcome to LSPosed!`, version
  banner, `lspd` daemon running as system, manager UI reporting activated.
- Zygisk requires one reboot after enable before `/data/adb/zygisk` exists; modules install to
  `/data/adb/modules_update/` and merge into `/data/adb/modules/` only on reboot.
- Shamiko v1.2.5 kept as backup, **not** installed — documented conflict with Zygisk-Assistant
  (both do root hiding); Zygisk-Assistant chosen because it does not depend on DenyList
  enforcement.
- mcp-termux / stackplz eBPF route closed on this device: requires kernel 5.10+, device has
  4.14.186; its bundled kmodules ship only 5.10/5.15/6.1/6.6/6.12 variants.
- MT Manager 2.26.9 installed; MCP port confirmed as 8787 in MT settings; forwards 8787/8651/
  65534 established.

## 3. Kernel-level content — unverified / inferred, with sources

No kernel-level mechanism in `kernel-and-environment-hardening.md` was executed, on this device
or any other. Specifically **unverified here**: eBPF kprobe/uprobe tracing, seccomp-BPF
installation into a target, KPM/LKM hooking, self-ptrace anti-anti-debug, and every hiding claim
of Shamiko / Zygisk-Assistant against a real detector (the module archives also record that
hiding was never validated against an actual detection scenario).

The **inferred** claims that carry external sources (fetched 2026-09, URLs in the reference
file):

| Claim | Source |
|---|---|
| KernelSU: kernel-based su, official support GKI 2.0 = kernel 5.10+ (Android 12-era), backport to 4.14 requires self-built kernel; module system conflicts with Magisk magic mount; su-only coexistence possible (kernel vs ramdisk patching) | tiann/KernelSU README + FAQ (github.com) |
| APatch: KernelPatch patches stock boot.img kernel (no kernel source needed — the difference from KernelSU); SuperKey-gated SuperCall syscall; KPM kernel-space modules with inline/syscall-table hooks; SELinux hooked not rewritten; Shamiko officially unsupported | apatch.dev FAQ |
| Shamiko: reads Magisk denylist but requires DenyList enforcement OFF; whitelist mode via `/data/adb/shamiko/whitelist` with documented performance cost | Shamiko README (LSPosed distribution) |
| Zygisk-Assistant: Magisk use = target on denylist + Enforce OFF; KernelSU/APatch use = ZygiskNext + "Umount modules/Exclude modifications" | snake-4/Zygisk-Assistant README |
| GKI 2.0 starts at android12-5.10; eBPF extension docs target GKI kernels | source.android.com (kernel architecture section) |

The version gate consequence (eBPF row closed on 4.14) is **observed** for this device (uname)
and **inferred** as a general gate from the GKI sources above.

## 4. Not run / open items

- Live MCP handshake: blocked on a human UI action (start APK MCP in MT). The probe script is
  ready; re-run and record the real `initialize` + `tools/list` output when it happens.
- Zygisk-Assistant + MoveCertificate merge: pending the device reboot recorded in the module
  archive; their post-merge behaviour is untested.
- No LSPosed hook module was built or run against a real target in either pass — the framework
  is activated (observed), the module workflow remains inferred.

## 5. Reproduction one-liners

```
python skills/apk-reverse/scripts/mt_mcp_probe.py            # probe + inventory or waiting help
adb forward --list                                           # confirm 8787 forward exists
adb -s <serial> shell "su -c 'netstat -tln | grep 8787'"     # device-side listen check
adb -s <serial> shell uname -r                                # the 4.14 kernel gate, observed
```
