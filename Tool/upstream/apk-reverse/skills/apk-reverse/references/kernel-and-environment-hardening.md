# Kernel-level and environment hardening — where to go when userspace hooking is not enough

Load this when you have already concluded, via `detection-and-anti-analysis.md`, that the target
genuinely detects your instrumentation — and that the check cannot be neutralised from userspace
because it runs before your hook, or bypasses the layers a userspace hook can reach. This file is
the **escalation map**: what the next layer down actually is, what it costs, and when it is the
wrong answer.

Division of labour, so the two files never duplicate:

- `detection-and-anti-analysis.md` owns **identifying** detection and the **cost decision**
  (work around / change route / accept and report). Read it first; its Step 0 still applies.
- This file owns **the routes below userspace** — root-implementation hiding properties, kernel
  interception options, and the syscall-level realities that decide whether "just hook it" was
  ever going to work.

**This repository does not do kernel development.** Everything in the kernel section is a map of
externally documented mechanisms with sources, labelled `inferred` — none of it was executed here.
That is deliberate: the purpose is to stop you from spending a day rediscovering the version
gate () or the conflict (), not to teach kernel hacking.

**Extension pass, read the next paragraph before relying on it.** This file now has a companion
generator — `scripts/kernelsu_syscall_mask.py` — which emits a loadable userspace module skeleton
plus kernel-side **templates** for the three routes in. The generator, its userspace output and
its own consistency check are `measured`; **the kernel-side code has never been compiled or loaded
anywhere**, and every generated kernel file says so in its own header. A template is a starting
point that removes the blank page, not a weapon that has been fired.

## 1. The attack-surface timeline — why "just hook it" fails

An app process initializes in a fixed order, and every anti-analysis check you will meet lives at
one of these stations:

```
linker (ld-android/inker)          -> relocations resolved, DT_INIT run
  .init_array of each loaded .so   -> constructors: earliest native code that runs
    JNI_OnLoad                     -> packers and RASP SDKs hook here
      Application.onCreate         -> first Java-level check
        first frame                -> UI-visible checks (and the end of "early")
```

The later your tool attaches, the more of this timeline has already executed and taken its
decision. Frida in attach mode arrives after all of it; spawn mode arrives at zygote fork, which
is why `dynamic-frida.md` prefers it — but a constructor in `.init_array` can still run before
the Frida agent finishes injecting, and a check placed there fires once and stores its verdict.

What those checks actually look for, and why each one is out of reach of a naive userspace hook
(the identification side belongs to `detection-and-anti-analysis.md`; this is the *mechanics* of
why the hook does not land):

| Detection mechanism | Why a userspace hook misses it |
|---|---|
| Inline `svc #0` syscalls (bypassing libc) | PLT/GOT hooks only intercept calls that go through the PLT. Hand-written `svc` instructions in the target's own `.so` never touch libc, so there is no PLT entry to redirect. |
| `/proc/self/maps` scan for foreign mappings | The read can be done with raw `openat`+`read` syscalls (same svc trick), and the thing being detected — your injected agent's mapping — exists in the process regardless of what you hook. |
| Named pipes / thread-name probes for known agents | Frida's runtime creates identifiable threads (`gum-js-loop` etc.) and (older versions) a linjector pipe. Renaming helps only if you control the runtime's identity, not the probe. |
| Code-page checksums of the target's own `.so` | An inline hook *is* a modification of the pages being checksummed. The check catches the hook by construction; the only userspace answer is to also neutralise the checksum, which recursively has the same problem if *that* code is checksummed too. |
| `/proc/self/status` `TracerPid` read | The field is written by the kernel. A userspace hook on the reader works only until the reader uses raw syscalls (row 1). See. |

The structural lesson: **userspace hooking and userspace anti-hooking are the same layer.** A
detection routine that lives in the same process as your hook, and that is willing to use raw
syscalls and self-verification, can always in principle race you. The routes below win by moving
to a layer the check cannot see from userspace — or by not being in the process at all.

## 2. Root implementations and what each one exposes

The root method you run decides which artefacts a detector can find *outside* the target process
(manager app, daemon, mount layout, SELinux contexts). Facts below are from the projects' own
documentation (sources at the end of the section); none were re-measured here — `inferred`.

| | **Magisk** | **KernelSU** | **APatch** |
|---|---|---|---|
| How su works | Patches the ramdisk/init; a `magiskd` runs in userspace; the manager app requests su through it | `su` handled **inside the kernel**; a manager app talks to the kernel via a driver/interface. Kernel modification. | Kernel modification via **KernelPatch**: patches the existing `boot.img` kernel — no kernel source needed (the difference from KernelSU) |
| Kernel version gate | None (works on old kernels — this is why the 4.14 test device runs it) | Official support = GKI 2.0, kernel **5.10+** (in practice: shipped with Android 12). Backported to 4.14 but you must build the kernel yourself | Same GKI-era expectation; needs only the stock `boot.img` to patch |
| Access control | Manager grants per-app; denylist for hiding | Manager + **App Profile** (constrain what a rooted app can do) | **SuperKey**: KPatch installs a new syscall (SuperCall); callers must present the SuperKey credential |
| SELinux | Modifies contexts (magiskpolicy) | Kernel-side handling | Hooks/bypasses SELinux rather than rewriting contexts — threads can be rooted in app context without `libsu`/IPC |
| Module format | Magisk modules (magic mount) | Magisk-compatible modules; `/system` modification needs a metamodule (overlayfs) | APM (Magisk-compatible) plus **KPM** — kernel-space modules with inline-hook and syscall-table-hook capability |
| Zygisk | Built-in | None built-in; add ZygiskNext | None built-in; add ZygiskNext / ReZygisk / NeoZygisk |

**What this means for hiding** (`inferred`):

- **Manager identity is the shared weak point.** All three ship a manager app the detector can
  enumerate by package or by scanning for its UI. All three support "randomise/repackage the
  manager" — use it, and do not assume the default package name is safe.
- **KernelSU/APatch remove the userspace su daemon** the detector could otherwise find as a
  process or a socket. But they add a kernel-level surface of their own; a detector cannot see it
  from an unprivileged app — which is the point.
- **Magisk on an old kernel is not a disadvantage for hiding**; it is a constraint of the device.
  Do not switch root schemes to win a detection race — that is §7's stop signal.
- **Module ecosystems interoperate but do not merge**: KernelSU's module system conflicts with
  Magisk magic mount (per KernelSU FAQ, running both means one stops working); su-only coexistence
  is possible because KernelSU patches the kernel while Magisk patches the ramdisk.

Sources: KernelSU README + FAQ (github.com/tiann/KernelSU), APatch FAQ (apatch.dev, project
originally at github.com/bmax121/APatch), fetched 2026-09. Device facts (Magisk alpha on kernel
4.14.186) are `observed` on the reference device used for this pass.

## 3. Environment-hiding modules: Zygisk-Assistant vs Shamiko

Both are Zygisk modules that hide root + Zygisk from target apps. **Do not install both** — they
overlap in function (mount-namespace handling, trace wiping) and interfere; this is documented in
the module ecosystems and was the deciding fact on the reference device (`observed`: Shamiko kept as a backup zip and uninstalled there).

The practical difference is their **denylist dependency** (from each project's own README,
`inferred`):

| | **Shamiko** | **Zygisk-Assistant** |
|---|---|---|
| Reads the Magisk denylist | Yes — but **requires DenyList enforcement to be OFF** (it takes over the handling itself) | Magisk: add the target to the denylist, **Enforce DenyList OFF**. KernelSU/APatch: enable the manager's "Umount modules/Exclude modifications" for the target app |
| Extra modes | Whitelist mode via `/data/adb/shamiko/whitelist` (empty file); docs warn of performance/memory cost, test-only | — |
| On APatch | Officially unsupported ("Shamiko is proprietary software, we cannot adapt it" — APatch FAQ) | Works via ZygiskNext |
| Version gates | Newer Shamiko requires recent Magisk/KernelSU bases | Current |

Selection rule (`inferred`): on Magisk, either works alone — pick one, configure its denylist
dependency correctly, and verify on the actual target. On KernelSU/APatch, Zygisk-Assistant (+
ZygiskNext) is the supported path. The denylist/enforcement settings are the part people get
wrong: **enforcement off, list populated** is the working combination for both.

Verification status: neither module's hiding effect was tested against a real detector on the
reference device — treat every
"this hides X" claim above as documented-but-unproven here.

## 4. Kernel-level interception — the map, and the version gate

When you need to observe or alter what a target does *at syscall level* — e.g. it reads
`/proc/self/status` via raw `svc`, and you want that read to return a spoofed page — userspace is
structurally the wrong layer. The options below exist; **none of them were executed in this
repository** (`unverified`), and each has a hard prerequisite worth checking before you read any
further:

```
uname -r            # on the device. The gate for most of this section is 5.10+
```

- **Why 5.10**: Android's GKI (Generic Kernel Image) programme starts at android12-5.10; the
  kernel-BPF ecosystem for tracing (bpftrace-class tools, kprobe/uprobe attachment as the tooling
  expects it) targets GKI kernels. Source: the Android kernel architecture documentation on
  source.android.com (GKI and eBPF pages). On the reference
  device (kernel **4.14.186**) this entire row is **closed** — `observed` (the version), with the
  consequence that eBPF-based tooling
  (stackplz, mcp-termux's tracing half) is unavailable there. Write the one-line environment fact
  per `detection-and-anti-analysis.md` Step 5 and do not revisit it.

| Route | What it gives you | Prereqs | Strength |
|---|---|---|---|
| **eBPF kprobes/uprobes** | Fire a BPF program on kernel or userspace function entry; observe syscall arguments/results system-wide, invisible to the target process | GKI 5.10+ kernel with the BTF/tracing config; root; toolchain (bpftrace or a custom loader) | `inferred` — documented upstream, not run here |
| **seccomp-BPF filter** | Per-process syscall allow/deny — can make a syscall **fail**, and seccomp can be installed by the app on itself (no root needed for self-filtering) | Any modern kernel; but a filter you install into the target requires ptrace/zygisk injection first | `inferred`. **Key limitation**: seccomp can reject or error a syscall (SECCOMP_RET_ERRNO/TRAP); it cannot rewrite the *content* of what a successful read returns. It closes doors; it does not paint them. |
| **Kernel module hooking** (KPM on APatch; out-of-tree LKM elsewhere) | Inline hooks and syscall-table hooks in kernel space — the layer that *can* rewrite what a `/proc` read returns | APatch (KPM) or a self-built kernel/LKM load path; kernel-dev skills | `inferred`. This is genuine kernel development — out of scope for this skill () |
| **Zygisk injection** (not kernel, but below the target's defences) | Run code in the target's process from zygote fork, before `.init_array` of the app's own libs | Magisk/KernelSU+ZygiskNext + a Zygisk module; no ptrace involved | `measured` as a framework (LSPosed runs this way on the reference device); a purpose-built module for a given target is `inferred` here |

The row that matters most in practice: **Zygisk is the cheap "below userspace" route** — it is in
the process earlier than any userspace tool can be, needs no ptrace (so it does not trip
`TracerPid`), and its ecosystem is maintained by other people. A custom kernel module that
rewrites one `/proc` read is a research project; a Zygisk module that hooks the target's
constructor is a build task.

### 4a. From "no weapon" to "template + gate": what the extension pass added

The gap this closes is specific. §4 above was a map with no artefact behind it: a reader told
"Kernel module hooking — inline hooks and syscall-table hooks in kernel space — the layer that *can*
rewrite what a `/proc` read returns" had nowhere to go next. `scripts/kernelsu_syscall_mask.py`
produces the artifact; this subsection states its boundary, because the boundary is the part that
matters.

**The correction worth internalising first: a KernelSU module cannot do any of this.** A KernelSU
(or Magisk, or APatch-userspace) module is a *userspace* module whose scripts run as root in the
normal world. `module.prop`, `post-fs-data.sh` and `service.sh` cannot change what `openat`
returns — not because of a version gate, but because nothing in that format is ever in the kernel's
return path. Detectors of the kind §2 and §3 discuss are not defeated by a module of that shape.
The generator emits that skeleton anyway, because it is the right carrier for the configuration and
the metadata, and it says in its own README what the skeleton cannot do.

What *can* reach the return path is one of three artifacts, and each carries a gate that has to be
checked on the actual device:

| Artifact | What it is | Gate | Status of the shipped template |
|---|---|---|---|
| **KPM** (KernelPatch / APatch) | A relocatable `.kpm` loaded by kpimg injected into the kernel image; replaces syscall-table pointers (`fp_hook_syscalln`) or rewrites prologues (`hook_wrapN`) | A KernelPatch-patched boot image, plus a **bare-metal** ARM64 toolchain (`aarch64-none-elf-gcc`) — not the NDK | `unverified` — template only, never compiled |
| **Out-of-tree LKM** | An ordinary kernel module that reaches `sys_call_table` and swaps a pointer | Kernel source matching the device's exact vermagic, and on ≥5.7 a way around `kallsyms_lookup_name` no longer being exported | `unverified` — template only; rated last of the three on cost |
| **eBPF probe** | A BPF program on a syscall tracepoint or kprobe | GKI 5.10+ with the tracing/BTF machinery | `unverified` — template only; the version gate alone closes it on most older devices |

The eBPF row carries a capability ceiling that is easy to miss and is stated in the generated file
as well: **a tracepoint can observe a syscall, not rewrite its result.** `bpf_override_return()`
only applies to functions flagged `ALLOW_ERROR_INJECTION`, which raw syscall entries are not —
so "eBPF to spoof a `/proc` read" is, on most kernels, an observation plan wearing a rewrite
plan's clothes. Observation is genuinely useful (it tells you which syscall the check uses, which
`§5` requires you to know anyway); it is not spoofing.

**Field notes on the KPM route, from a public KPM development write-up** (`inferred` here — the
author's measurements, not this repository's; source: blackr0ck, *APatch KPM 开发*,
[bbs.kanxue.com/thread-291665.htm](https://bbs.kanxue.com/thread-291665.htm), 2026-06). These are
recorded because each one is a day of somebody's time:

- **An inline hook can install cleanly and never fire.** On a GKI kernel with LTO, the exported
  symbol is frequently not the call site — the callee was inlined into its only caller, so
  replacing instructions at the symbol's address intercepts nothing. The reported symptom is
  "module loaded, callback never ran". Pointer replacement in the syscall table does not have this
  failure mode, because the syscall entry path must go through the table.
- **The instruction-sequence length in a module header is a trap of its own.** The reported cause
  of a hard-to-diagnose load failure: declaring a resolved kernel function with `extern` makes the
  compiler emit an undefined reference (`*UND*`) instead of allocating the slot, and the loader
  refuses the module with `unknown symbol`. Letting it be a tentative definition allocates `.bss`
  and the loader fills it in. The generated template states this rule in the code, and
  `verify` checks for it.
- **Per-syscall callbacks run on every syscall of that number, system-wide.** The reported
  incident: a `write` hook that did not first reject `fd <= 2` intercepted the framework's own log
  output tens of thousands of times and the device rebooted. **Performance is correctness here** —
  the first statement in every callback is a filter that rejects the common case.
- **Which hook point survives is kernel-specific, and the cheap way to find out is to start at the
  syscall layer.** The same write-up reports that modifying the SELinux internal function they
  first targeted crashed the kernel under every combination tried (before/after, argument,
  return value, skip-origin), while a syscall-table hook on `write` proved stable and sufficient.
  Treat the syscall layer as the default and move inward only with evidence.

**Measured on the reference device, and why every template here is labelled the way it is.**
`<DEVICE>` runs kernel **4.14.186+** (`adb shell 'uname -r; cat /proc/version'` →
`4.14.186+`, `Linux version 4.14.186+ (nobody@android-build) (Android (6443078 based on r383902)
clang version 11.0.1 ...) #1 SMP PREEMPT Wed Mar 30 23:32:42 CST 2022`). On that device the two
remaining gates answer themselves:

- **eBPF**: 4.14 is far below the 5.10 gate. Closed, as §4 already recorded.
- **KPM**: no KernelPatch-patched image is present, and the host has no
  `aarch64-none-elf-gcc` (`kernelsu_syscall_mask.py gates` reports `NOT FOUND`, along with no
  `ndk-build` and no `make`). Installing APatch means patching the boot image — a bricking risk
  that this repository does not take on an APK task.
- **LKM**: no kernel source for the device, so no matching vermagic is possible.

So on this machine the honest answer to "do you have a kernel-level weapon" is: **you have a
template, a gate table and a measured statement that the gate is closed here.** That is a route
decision, not a failure — and it is the same shape of answer §6 gives for the whole escalation
ladder. Do not let the existence of the template change what you claim about it: `unverified` is
still `unverified`.

## 5. The syscall-level realities that survive every hook

Two facts decide a lot of "unexplainable" behaviour, and both belong to the kernel's design
rather than to any tool:

1. **`TracerPid` is written by the kernel, not by a library.** Anything that ptraces the target
   (classic Frida attach, debuggers) makes `/proc/self/status` show it, and the only readers that
   miss it are the ones you broke. Ways out, in escalating cost:
   - attach-free operation: **Zygisk** (injection at fork; no ptrace) or Frida **spawn** (still
     ptrace-based but only during injection — verify for your version) or a memory patch applied
     before detach (`scripts/spawn_patch_detach.py`, `measured`);
   - kernel-level hiding of the field (KPM/eBPF rewrite of the proc read) —, `unverified`;
   - **self-ptrace**: the target ptraces itself so nothing else can (classic anti-anti-debug);
     works because only one tracer is allowed — but it constrains your tooling to non-ptrace
     routes anyway. `inferred`.
2. **A raw `svc` cannot be intercepted from userspace at all.** No PLT, no libc, no hookable
   symbol. Every plan that says "hook open/read and spoof the maps" silently assumes the target
   calls libc; a hardened target does not. Verify which one you have before building the spoof:
   disassemble the check's `.so` and look for `svc #0` (AArch64) / `int 0x80`-era equivalents in
   the check path (`inferred`; `scripts/native_crash.py`-style capstone disassembly applies).

## 6. What the reference environment chose (and why it generalises)

On the 4.14-kernel reference device, the escalation ladder terminates early — and that is the
honest outcome (`observed` on that device):

| Layer | Status on a 4.14 Magisk device |
|---|---|
| LSPosed (Zygisk) module hooking | available — framework activation verified by log (`welcome to LSPosed!` lines, `lspd` daemon process) |
| MT Manager on-device editing/repack/sign | available (`on-device-tooling.md`) |
| eBPF tracing | closed (kernel gate) |
| KPM / kernel module route | closed on this device — no KernelPatch image, no kernel source, no bare-metal ARM64 toolchain; the **template and gate table** are shipped (§4a) |
| Frida with disguised server | available (a renamed server binary was present on the device from prior work) |

The generalisable rule: **enumerate the ladder for *your* device once, write the one-line
environment facts, and stop re-deriving them mid-task.** A closed rung is a route decision, not a
failure.

## 7. When to stop escalating — the decision table

This extends `detection-and-anti-analysis.md` Step 2 with the kernel rung. The repo's stance:
R3 (never ship or claim an unverified artifact) outranks winning the arms race; a detector you
defeated with a custom kernel module is not a deliverable anyone can install.

| Situation | Do this | Not this |
|---|---|---|
| Check is userspace, hookable, single-site | Neutralise at the site (`native-tamper-and-suicide.md` rules) | Building a hide stack |
| Check runs before your userspace tool (init_array) | Zygisk-route module, or static patch of the check itself | Earlier userspace attach racing the constructor |
| Check uses raw syscalls | Static patch of the check; or LSPosed/Zygisk module hooking the consuming code | "Hook libc open/read" (does nothing) |
| Check detects the *environment* (root/emulator), not your patch | `detection-and-anti-analysis.md` A/B/C — usually a different device or route | Kernel work |
| You are about to write a kernel module / patch a kernel | Stop. State what is blocked and the evidence; propose the static/module route | Kernel development (out of scope for this skill) |
| You have the kernel template and want to load it on a 4.14/Magisk device | Read `§4a`'s gate table, confirm the gate is closed, and say so | Patching a boot image to obtain a kernel route, on an APK task |
| A kernel-side template exists, so it feels like a weapon | It is `unverified` until a device with the matching gate compiles and loads it | Presenting a template as a working capability |
| Escalation effort exceeds the user's actual ask | `detection-and-anti-analysis.md` stop signal — switch to static | One more layer |

## Checklist

- [ ] `detection-and-anti-analysis.md` read first; A/B/C chosen deliberately
- [ ] Check located on the timeline () before choosing a counter-layer
- [ ] Root scheme's artefacts enumerated (manager/daemon/mounts) before blaming the target
- [ ] Hiding module: exactly one of Shamiko / Zygisk-Assistant; denylist configured to its spec
- [ ] Kernel rung checked against `uname -r` — one line recorded if closed
- [ ] Kernel-side template treated as `unverified` until a device with the matching gate
      actually compiles and loads it (`§4a`); the userspace module skeleton is a carrier for
      configuration, not a kernel capability
- [ ] Raw-syscall vs libc-call distinction verified by disassembly before building any spoof
- [ ] No kernel development undertaken as part of an APK deliverable
