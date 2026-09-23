# Extension verification — Java2C identification and routing

Covers the 2026-09 extension pass that added `references/java2c-and-jni-sinking.md` and
`scripts/java2c_probe.py`. Strength labels as defined in this directory's README:
**observed** (exact command + output here), **inferred** (follows from observed facts,
step not executed), **unverified** (assumed or externally reported, not independently
confirmed).

Reference environment for this pass: Windows 11 host, Python 3.14.0, JDK 17,
build-tools (`d8`/`aapt2`) from a local Android 14 SDK, `gcc` from MinGW only.
**No Android NDK, no host `clang`, no `wsl` (HCS unavailable), and no device-side
`clang`/Termux.** A rooted Android 11 / API 30 / arm64-v8a `<DEVICE>` was attached and
reachable but **was not used at all** in this pass: every result below is static. No
package name, project name or device serial appears in this record.

Samples are identified by hash rather than by name. They are public MASTG training apps
(a no-native baseline, and two carrying a JNI sink), one VMP-labelled app taken from
`tools/_work/bench/repos/`, one real third-party aarch64 ELF already on the host, and one
locally synthesised Java2C-shaped dex.

---

## 1. The compile chain could not be closed — observed

The intended route was to build a real Java2C `.so` with `amimo/dcc` and probe it. `dcc`
is present at `tools/_work/bench/repos/dcc/` and its Python dependencies are satisfied.
The build stops at the C compiler, and every alternative was tried exactly once before
being written off (two-strike rule — no third variant was attempted):

```
$ which gcc clang
gcc.exe  C:\MinGW\bin\gcc.exe          # MinGW targets PE/COFF, not ELF
gcc/clang for Android: none

$ wsl -l -q ; wsl -e bash -lc "which gcc"
Ubuntu-E
(empty)  ->  exit 1 with: Wsl/Service/CreateInstance/CreateVm/HCS/HCS_E_SERVICE_NOT_AVAILABLE

$ adb shell "which clang clang++ gcc ; ls /data/data/com.termux"
(no output for which)
ls: /data/data/com.termux: No such file or directory
```

Related **observed** fact: the `dcc` checkout ships **no prebuilt binary at all** — a
recursive search for `*.so`, `*.apk`, `*.a` over the whole repo returns zero files. There
is no ready-made Java2C library to fall back on.

Consequence: **no ELF file anywhere in this pass was produced by a Dex-to-C compiler.**
Every Java2C-specific criterion in the reference document is therefore **inferred**.

## 2. Degenerate route A — `dcc` generates the C without an NDK — observed

`dcc.py` takes `--no-build`, and `dcc_main(..., do_compile=False)` writes the generated
sources and the JNI project *before* `build_project(project_dir)` would be called. With
`--no-build` and no `-o`, the apktool repack path is skipped entirely (it is guarded by
`if is_apk(apkfile) and outapk`). So the translation stage runs to completion on a machine
with no NDK.

```
$ cd tools/_work/bench/repos/dcc
$ python dcc.py <SAMPLE_DIR>/baseline.apk --no-build --dynamic-register \
      --source-dir <WORK>/dcc-out
# (emits only Python 3.14 SyntaxWarnings from the bundled androguard)

$ find <WORK>/dcc-out -type f
jni/Android.mk
jni/Application.mk
jni/nc/Dex2C.cpp                 jni/nc/Dex2C.h
jni/nc/DynamicRegister.cpp       jni/nc/DynamicRegister.h
jni/nc/ScopedLocalRef.h          jni/nc/ScopedPthreadMutexLock.h
jni/nc/well_known_classes.cpp    jni/nc/well_known_classes.h
jni/nc/compiled_methods.txt
jni/nc/Java_<PKG>_<Class>_<method>__<mangled-proto>.cpp
```

This is the mapping evidence the pass needed, and it is exact rather than imagined:

`compiled_methods.txt` is a one-line dex signature, and it produced exactly one C file
whose name is the same identifier in JNI long form:

```
L<PKG>/MainActivity;onCreate(Landroid/os/Bundle;)V
  -> Java_<PKG>_MainActivity_onCreate__Landroid_os_Bundle_2.cpp
```

The generated function opens with the parameter shape the reference document cites as the
`.so`-side signature of a translated method:

```c
/* L<PKG>/MainActivity;->onCreate(Landroid/os/Bundle;)V */
void Java_<PKG>_MainActivity_onCreate__Landroid_os_Bundle_2(JNIEnv *env, jobject thiz, jobject p2){
jobject v0 = NULL;
...
jclass cls0 = NULL,cls1 = NULL,cls2 = NULL,cls3 = NULL;
```

And the registration half is generated as real text, which is the strongest single piece
of evidence produced in this pass that the "no `Java_*` symbol to search for" path is not
hypothetical:

```c
// DynamicRegister.cpp
const char *dynamic_register_compile_methods(JNIEnv *env) {
jclass clazz;
clazz = env->FindClass("<PKG>/MainActivity");
if (clazz == nullptr)
    return "Class not found: <PKG>/MainActivity";
const JNINativeMethod export_method_0[] = {
{"onCreate", "(Landroid/os/Bundle;)V", (void *)Java_<PKG>_MainActivity_onCreate__Landroid_os_Bundle_2}
};
env->RegisterNatives(clazz, export_method_0, 1);
env->DeleteLocalRef(clazz);
return nullptr;
}
```

Two further facts read out of the generated `jni/Application.mk`, both **observed** and
both load-bearing for the JNI-boundary section of the reference document:

```
APP_STL := c++_static
APP_CPPFLAGS += -fvisibility=hidden
APP_ABI := armeabi-v7a arm64-v8a
```

`-fvisibility=hidden` means the shipped library can present as "exports no `Java_*`
symbol" **even when the translation used static naming** — the second, independent reason a
symbol search returns nothing. `c++_static` is the origin of the `libc++` string criterion,
and is also why that criterion is weak: it is an ordinary NDK setting.

## 3. The probe against real JNI-sinking targets — observed

This is the discriminating measurement the reference document is built on. The tool was
run unmodified:

```
$ python skills/apk-reverse/scripts/java2c_probe.py --apk <SAMPLE_DIR>/jni-a.apk
  classes.dex: 720084 B, 625 classes, 5081 methods, native 2 (0.04%),
               native-dominated classes 0, fully native 0
  libfoo.so: 14176 B, aarch64, dynsym 20 entries, Java_* 2, JNI_OnLoad False
  libfoo.so: 13948 B, arm, dynsym 26 entries, Java_* 2, ...
  libfoo.so: 13788 B, x86, dynsym 16 entries, Java_* 2, ...
  libfoo.so: 14440 B, x86_64, dynsym 16 entries, Java_* 2, ...
  verdict    : jni-sinking
  confidence : medium
```

```
$ python skills/apk-reverse/scripts/java2c_probe.py --apk <SAMPLE_DIR>/jni-b.apk
  classes.dex: 1934860 B, 1396 classes, 11182 methods, native 3 (0.03%),
               native-dominated classes 0, fully native 0
  libfoo.so (arm/arm64: 3 Java_* symbols, x86/x86_64: 3 Java_* symbols)
  verdict    : jni-sinking
  confidence : medium
```

Two independent real targets, and both give the same two results: **native density three
orders of magnitude below the Java2C shape**, and **an exact 1:1 between the dex native
declarations and the exported `Java_*` symbols** (2:2 and 3:3, across four ABIs each).

That 1:1 is the point. It is *not* a Java2C signal on its own — both shapes produce it —
which is why the density measurement and the native layer must be read together. A tool
that reported on either alone would misroute one of these two samples.

Baseline control, same command, no native code at all:

```
$ python skills/apk-reverse/scripts/java2c_probe.py --apk <SAMPLE_DIR>/baseline.apk
  classes.dex: 5528 B, 7 classes, 15 methods, native 0 (0.00%), ...
  verdict    : no-hardening-signal
  confidence : medium
```

## 4. The probe against a Java2C-shaped dex — observed

No Java2C library could be built, so the dex half of the shape was synthesised. A Java
source declaring two classes whose methods are almost entirely `native` (plus one mixed
class, standing in for an ordinary JNI boundary) was compiled with `javac --release 8` and
assembled with `d8 --min-api 19`:

```
$ javac --release 8 -d classes src/<PKG>/Calc.java     # exit 0
$ d8 --min-api 19 --output out classes/<PKG>/*.class   # exit 0
out/classes.dex   1752 B   sha256 59e0b1d34f00578e1343ee5f344d0e58829f482b643a7843c8ad280311ce9457

$ python skills/apk-reverse/scripts/java2c_probe.py --dex out/classes.dex
  classes.dex: 1752 B, 3 classes, 29 methods, native 24 (82.76%),
               native-dominated classes 2, fully native 1
  verdict    : java2c-suspect-needs-so
  confidence : low
```

The low confidence is the correct answer, not a shortcoming: the tool refuses to claim
Java2C from the dex alone, and says so in its route block. That refusal is the guard
against the misdiagnosis this pass exists to prevent.

Combining that dex with a real library that registers dynamically makes the `java2c` branch
reachable, which is what proves the branch is not dead code — the input is composite and is
labelled as such:

```
$ python skills/apk-reverse/scripts/java2c_probe.py --dex out/classes.dex \
      --so <WORK>/libandroid.so
  verdict    : java2c
  confidence : medium
  evidence: (strong) native layer: dynamic registration in libandroid.so
            (JNI_OnLoad exported, zero Java_* symbols)
```

## 5. The JNI boundary — why `RegisterNatives` cannot be found — observed

The reference document claims a symbol search fails silently and that looking for a
`RegisterNatives` symbol is structurally unable to work. Both are measured here.

A real 273,120 B aarch64 system library pulled from one of the samples exports a JNI entry
point and no `Java_*` symbols, and the probe flags it as dynamic registration — the
affirmative check that does work:

```
  libandroid.so: 273120 B, aarch64, dynsym 504 entries, Java_* 0,
                 JNI_OnLoad True, RegisterNatives-import False
  (strong) native layer: dynamic registration in libandroid.so
           (JNI_OnLoad exported, zero Java_* symbols)
```

Independent confirmation that the absence is real and not a parser gap — the same check run
outside the script:

```
$ python -c "d=open('gadget.so','rb').read(); [print(k, d.count(k.encode())) for k in
             ['JNI_OnLoad','RegisterNatives','Java_','Dex2C','libc++_shared.so','frida']]"
JNI_OnLoad 0
RegisterNatives 0
Java_ 0
Dex2C 0
libc++_shared.so 0
frida 311
```

A 25.8 MB real third-party aarch64 ELF with 311 occurrences of its own name contains zero
`JNI_OnLoad` and zero `Java_`. The probe reported the same (0 `Java_*`, `JNI_OnLoad False`),
so the two readings agree and the probe is not reporting a parse failure as an absence.

**Why the `RegisterNatives` search cannot fire** `[observed]`: the library above registers
dynamically and contains **zero literal `RegisterNatives` symbols**. The cause is a
documented property of the NDK C++ headers `[inferred]`: `jni.h` declares `RegisterNatives`
as an inline member of `JNIEnv` that dispatches through the function table, so a call site
emits no external symbol. The observed half is the missing symbol; the explanation is
inferred from the mechanism.

## 6. Coverage of the probe's code paths — observed

| Path | Exercised by | Result |
|---|---|---|
| dex header + class_defs + class_data (ULEB128) | 5 real dex images + 1 synthetic | Parsed; header size match reported |
| `direct_methods` / `virtual_methods` decoding | the synthetic fixture (has both) | Correct after the defect in §7 |
| native density, native-dominated classes | all six | 0.03–0.04 % real vs 82.76 % synthetic |
| no-`code_item` and trivial-body ratio | all six | 0 on the fixture, 4–5 % on the real apps |
| ELF header, arch, section table | 10 real ELFs (4 ABI variants of two `libfoo.so`, 2 app libs, 1 gadget) | aarch64/arm/x86/x86_64 all identified |
| `.dynsym` parse, `Java_*` extraction | real `libfoo.so` ×8 | 2 and 3 symbols, matching the dex exactly |
| `JNI_OnLoad` export detection | real system library | True |
| dynamic-registration verdict | same library | Fired |
| string-signature scan | 25.8 MB ELF, all samples | Weak hits only (`dcc` ×6 on the gadget); no false strong hit |
| `--json` | synthetic fixture | Valid JSON, metrics block parses |
| `--dir`, `--apk`, `--dex`, `--so` | all four modes | OK |
| `--help` | direct | OK |

The string scan produced exactly one class of hit across every sample: the weak `dcc`
substring (6 occurrences inside a 25.8 MB binary, i.e. coincidental). **No strong marker was
ever produced by any real sample**, which is why the Java2C verdict rests on structure
rather than on strings.

## 7. Not exercised — and why the Java2C verdict stays inferred

- **A real Java2C `.so`.** Never produced; the compile chain is dead (§1). Everything about
  how a *compiled* Java2C library presents — whether the generated functions keep their
  names under `-fvisibility=hidden`, whether `Dex2C` runtime strings survive into `.rodata`
  — is **inferred** from the generated sources and the build flags, not observed.
- **The runtime claim that no dex bytecode exists in memory.** This is the mechanism the
  whole document turns on and it is **inferred from the translation model**. No live Java2C
  app was run. It is falsifiable and cheap to test on a live sample; that test is named in
  the reference document.
- **VMP identification by static dex metrics.** One VMP-labelled sample (sha256
  `76e3fa8119cf8b7c4b4768be557d71863433a8ae4d2ad40901eae6bb829349bc`, a 2,984,841 B APK
  from the local bench repos, identified by hash only)
  was measured and reported **`jni-sinking`**: its static dex has 23,603 methods of which 7
  are native, with a 4 % stub ratio, and the archive contains no additional encrypted
  payload. **This is a recorded boundary, not a success**: whatever hardening that sample
  carries is applied at runtime, and a static dex probe is structurally unable to see it.
  Do not read this row as "the sample is unhardened".
- **Anything on a device.** The `<DEVICE>` was not used; there is no dynamic evidence in
  this record.

## 8. Two defects this pass found in its own tool — observed

Both were found by running the tool against the synthetic fixture and checking the numbers
by hand, and both are fixed in the shipped script.

1. **`direct_methods` and `virtual_methods` were decoded as one continuous run.** They are
   two independent encoded lists; each one's first `method_idx_diff` is relative to 0.
   Walking them as one run mis-attributed every virtual method to the following class. The
   fixture exposed it as `Codec: 5 methods` where the source declares 4. Fix: decode them as
   two passes. After the fix the per-class counts match the source exactly (Calc 20/21
   native, Codec 3/3, Helper 1/2).

2. **The "whole class is native" criterion was unreachable.** `javac` — and, per the
   generated output, a translation pass — always leaves `<init>`/`<clinit>` behind, so no
   class is ever literally all-native unless a constructor is counted as native. The
   fixture showed `fully native 0` while two of its classes were plainly native-shaped. Fix:
   constructors are excluded and the test is now ">= 70 % of >= 3 named methods native",
   reported alongside the literal count. After the fix: `native-dominated classes 2,
   fully native 1`.

Both defects produced *plausible* output — a wrong count and a zero that reads as "nothing
found" — which is the failure shape this whole repository is organised against. Recording
them here because a reader relying on either number would have drawn a wrong conclusion.
