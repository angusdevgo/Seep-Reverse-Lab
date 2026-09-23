# Extension verification — kernel-level weapons (templates, gates, and a closed door)

Covers the extension pass that added `scripts/kernelsu_syscall_mask.py` and the `§4a` section of
`references/kernel-and-environment-hardening.md`. Strength labels as defined in this directory's
README: **observed** (exact command + output here), **inferred** (follows from observed facts,
step not executed), **unverified** (assumed or externally reported, not independently confirmed).

Reference environment: Windows 11 host, Python 3.14.0; `<DEVICE>` = rooted Android 11 (API 30)
arm64-v8a, Magisk alpha, no APatch/KernelPatch.

**Headline: the generator, the gate table and the userspace module skeleton are measured. No
kernel-side artifact was compiled or loaded anywhere, and every route is closed on the reference
device. That is the deliverable — a template plus a measured statement of the door.**

---

## 1. Kernel gate, measured on the device — observed

```
$ adb shell 'uname -r; cat /proc/version'
4.14.186+
Linux version 4.14.186+ (nobody@android-build) (Android (6443078 based on r383902) clang version
11.0.1 (https://android.googlesource.com/toolchain/llvm-project b397f81060ce6d701042b782172ed13bee898b79),
LLD 11.0.1 (/buildbot/tmp/tmp6_m7QH ...)) #1 SMP PREEMPT Wed Mar 30 23:32:42 CST 2022
```

4.14.186 is below the 5.10 GKI gate for the eBPF route, and the device carries no
KernelPatch-patched image. Read-only query; no device lock was needed and no state was changed.

## 2. Host toolchain probe — observed

```
$ python skills/apk-reverse/scripts/kernelsu_syscall_mask.py gates
== kernel-side routes and their gates ==

  eBPF tracepoint/kprobe       GKI kernel 5.10+ (Android 12+)
                               why:  Android's BPF/tracing support as bpftrace-class tooling and
                                     stackplz expect it is a GKI-era feature; BTF is required for
                                     CO-RE style probes.
                               check: uname -r  ->  expect 5.10.x or newer; ls /sys/kernel/btf/vmlinux

  KernelPatch / APatch KPM     KernelPatch-patched boot image + kpm toolchain
                               why:  KPMs load through kpimg injected into the kernel image's
                                     payload segment; building one needs a bare-metal ARM64
                                     compiler (aarch64-none-elf-gcc), not the NDK.
                               check: ls /data/adb/ | grep -i apatch ; which aarch64-none-elf-gcc

  Out-of-tree LKM              Kernel source matching the device's exact version + vermagic
                               why:  A module built against a different kernel revision is refused
                                     at load time on a mismatched vermagic, and the device's kernel
                                     source is frequently not published at all.
                               check: uname -r ; look for a matching kernel source tree for the device

  seccomp-BPF (for contrast)   any modern kernel, but it is not this route
                               why:  seccomp can make a syscall FAIL (SECCOMP_RET_ERRNO/TRAP); it
                                     cannot rewrite the CONTENT a successful read returns. It closes
                                     doors, it does not paint them -- which is the whole requirement
                                     for a spoofed /proc read.
                               check: n/a -- this is a capability ceiling, not a version check

== host probe (what can be checked from here) ==

  bare-metal ARM64 compiler: NOT FOUND
     the KPM route cannot be built from this host as configured
  ndk-build:   NOT FOUND
  make:        NOT FOUND

  A kernel source tree, a patched boot image and the device's own kernel headers cannot be
  checked from the host; they are device facts.
```

The three `NOT FOUND` lines are the measured reason the KPM route cannot be built from here, and
they are also consistent with `ENV.md`'s record that the machine has no Android NDK. The LKM route
additionally needs kernel source that does not exist for this device.

## 3. `generate` — observed

```
$ python skills/apk-reverse/scripts/kernelsu_syscall_mask.py generate \
      --out tools/_work/t5-vmp/sysmask --package '<PKG>'
generated module scaffold in tools/_work/t5-vmp/sysmask
  module.prop                      165 B
  customize.sh                     166 B
  post-fs-data.sh                  830 B
  service.sh                       467 B
  uninstall.sh                     298 B
  config/syscall_mask.json        1079 B
  kpm/syscall-mask.c              8096 B
  kpm/Makefile                     880 B
  lkm/syscall-mask.c              2434 B
  ebpf/syscall_mask.bpf.c         4338 B
  README.md                       3752 B

STATUS: the userspace module is installable; every kernel-side file is an UNVERIFIED template.
        No kernel code was compiled or loaded.
```

`module.prop`, as generated (the package identity is the `<PKG>` placeholder by design — this file
carries no real package name):

```
id=syscall-mask
name=Syscall Mask
version=0.1.0
versionCode=1
author=apk-reverse
description=config-driven syscall return masking (openat/read/stat on /proc/self/*)
```

The configuration table rendered into the KPM template from `config/syscall_mask.json`, so the
rule set is data rather than hand-edited C:

```
static const struct mask_rule rules[] = {
    { "/proc/self/maps", 0, MASK_DENY, -2, 0 },
    { "/proc/self/maps", 0, MASK_FAKE_SIZE, -2, 0 },
    { "/proc/self/status", "TracerPid", MASK_FILTER_LINE, -2, 0 },
    { "/proc/self/status", "TracerPid", MASK_FILTER_LINE, -2, 0 },
};
```

And the KPM lifecycle surface, which is the part an interface drift would break first:

```
int kfunc_def(strncpy_from_user)(char *dst, const char __user *src, long count);
/* fp_hook_syscalln(__NR_openat, before_openat, 0, 0);    */
/* fp_hook_syscalln(__NR_newfstatat, before_newfstatat, 0, 0); */
/* fp_hook_syscalln(__NR_read, before_read, 0, 0);        */
KPM_INIT(mask_init);
KPM_EXIT(mask_exit);
```

Those names (`KPM_NAME` / `KPM_INIT` / `KPM_EXIT`, `kfunc_def`, `fp_hook_syscalln`,
`hook_fargs4_t`, `syscall_argn`, `args->skip_origin`, `args->ret`) are taken from a public KPM
development write-up rather than invented — blackr0ck, *APatch KPM 开发：绕过 DirtySepolicy /
Duck Detector 的 SELinux Root 检测*, [bbs.kanxue.com/thread-291665.htm](https://bbs.kanxue.com/thread-291665.htm),
fetched 2026-02. **They are still `unverified` here**: nobody compiled against a `kpmodule.h` in
this pass, and the generated template says so in its own header for exactly that reason.

The registration calls are left **commented out** in the template. A generated file that arms a
kernel hook by default is a file that arms a kernel hook the first time somebody runs `make` in a
hurry.

## 4. `verify` — observed

```
$ python skills/apk-reverse/scripts/kernelsu_syscall_mask.py verify --dir tools/_work/t5-vmp/sysmask
== verifying tools/_work/t5-vmp/sysmask ==
  module.prop: author=apk-reverse, description=config-driven syscall return masking
               (openat/read/stat on /proc/self/*), id=syscall-mask, name=Syscall Mask,
               version=0.1.0, versionCode=1
  config: 4 rule(s), actions=['deny', 'fake_size', 'filter_line']
  kpm  target present: Makefile, syscall-mask.c
       status: UNVERIFIED TEMPLATE -- not compiled, not loaded
  lkm  target present: syscall-mask.c
       status: UNVERIFIED TEMPLATE -- not compiled, not loaded
  ebpf target present: syscall_mask.bpf.c
       status: UNVERIFIED TEMPLATE -- not compiled, not loaded
  kpm/syscall-mask.c: KPM_* lifecycle macros present, kfunc_def not extern

== 0 problem(s): structure is consistent ==
   (this says nothing about whether the kernel side compiles or loads)
```

`verify` is deliberately read-only and deliberately narrow: it checks `module.prop` fields, the rule
JSON, and the one static trap in the KPM template that has a documented consequence (an `extern`
`kfunc_def` becomes `*UND*` and the loader refuses the module). It states on its last line what it
does **not** establish, because "0 problems" on a template is the easiest sentence in this file to
over-read.

### 4a. A false positive this check produced, and its fix — observed

The first run reported:

```
== 1 problem(s) ==
  - syscall-mask.c declares kfunc_def with `extern`, which the loader rejects as an unknown symbol
verify rc=1
```

The template does not declare it with `extern` — its comment *explains* why `extern` is forbidden,
and the check's own regex ran from that prose across to the real declaration's semicolon. A linter
that reads comments as code produces reports nobody can act on. The fix strips `/* */` and `//`
comments before any token check (`_strip_c_comments`). Both the false positive and the fix are
recorded here rather than quietly repaired, because the failure mode — a check that fires on its
own documentation — is one a reader will meet again.

## 5. The userspace module's ceiling — observed by construction, and worth stating plainly

`post-fs-data.sh` and `service.sh` in the generated skeleton do not load anything. That is not an
omission: a KernelSU/Magisk/APatch-userspace module runs as root in the normal world and cannot
change what a syscall returns. The generated `README.md` says this in its first paragraph, and
`post-fs-data.sh` carries the reasoning in a comment:

```
# The kernel side (if you built and loaded one) owns the syscall table; this
# script's whole job is to make the configuration visible to it and to leave a
# record that the module actually ran. Do not put a syscall hook here: this is
# userspace, and nothing here can change what openat/read/stat return.
```

The uninstall hook likewise refuses to unload a kernel module, because a silent unload during
package removal is how a device ends up in a boot loop.

## 6. eBPF route — gate table and the capability ceiling

| Route | Gate | Check on the device | Status here |
|---|---|---|---|
| eBPF tracepoint/kprobe | GKI 5.10+ with tracing/BTF | `uname -r`; `ls /sys/kernel/btf/vmlinux` | **closed** — device is 4.14.186 |
| seccomp-BPF | any modern kernel | n/a | not this route: it can only fail a syscall, not rewrite a successful read |
| KernelPatch / APatch KPM | patched boot image + `aarch64-none-elf-gcc` | `ls /data/adb/ \| grep -i apatch`; `which aarch64-none-elf-gcc` | **closed** — neither present; patch-the-boot-image risk declined |
| Out-of-tree LKM | kernel source matching vermagic | `uname -r` + a matching source tree | **closed** — no source for this device |

The probe template (`ebpf/syscall_mask.bpf.c`) is a `sys_enter_openat` tracepoint observer with a
uid filter map and a ringbuf event, and it documents two dead ends in the file itself:
`bpf_override_return()` only applies to `ALLOW_ERROR_INJECTION` functions, which raw syscall
entries are not, and a tracepoint cannot rewrite a result at all. **A tracepoint observes; it does
not spoof.** The honest eBPF shape for this job is therefore observation — which is still worth
having, because `§5` of the reference file requires you to establish whether the target uses a raw
`svc` or a libc call *before* designing any spoof.

## 7. What was not done

- **No kernel-side code was compiled.** Not the KPM, not the LKM, not the eBPF program. No
  `kpmodule.h`, no kernel headers, no `bpftool`, no bare-metal ARM64 compiler on this host.
- **Nothing was loaded, flashed or activated on `<DEVICE>`.** No boot-image patch, no module load,
  no kernel modification. The task forbids it for good reason: a kernel module that faults takes
  the device down before it can report why.
- **The KPM API surface is `unverified`.** The macro and helper names follow a public write-up; the
  argument arity of `fp_hook_syscalln` in particular is marked `TODO(verify-on-device)` in the
  generated source rather than guessed, because a wrong arity in a hook registration is a
  load-time failure at best.
- **The struct-stat size offset is a TODO, not a value.** The `newfstatat` handler deliberately does
  not carry a magic offset: it is ABI-specific and copying one from a different architecture is how
  a spoof corrupts an unrelated field.
- **`verify` establishes structure, not capability.** Its own output says so.
