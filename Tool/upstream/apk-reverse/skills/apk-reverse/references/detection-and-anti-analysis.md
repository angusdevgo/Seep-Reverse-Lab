# Detection, anti-analysis, and when to stop fighting it

Load this when the app fights back: it dies or misbehaves after you attach, refuses to run on your
device, detects root/emulator/hook/debugger, or when your dynamic tool simply will not work on the
environment you have.

This file is a **decision** file, not a bypass catalogue. The expensive mistake it exists to prevent is
spending hours escalating against a detection layer when a cheaper route — usually static — was
available the whole time.

## Step 0: the cheapest decision in this file

**Dynamic analysis is a convenience, not a prerequisite.** Everything that ends in an installable
artifact is decided statically: you edit a file and repackage. Dynamic work is how you *find* things,
and it is often the fastest way — but when it is blocked or unavailable, the correct move is usually to
switch to static, not to escalate.

So before doing anything clever, ask:

1. Is the thing I still need to learn actually discoverable statically? (Strings, code structure,
   call sites, comparisons — usually yes.)
2. Do I need the process to run *to verify*, or only to *find*? Verification can often be done by
   observing the shipped artifact's behaviour, which a hostile process still exposes.

If either answer allows a static path, take it and stop reading this file.

## Step 1: is it detection, or is it your environment?

Detection has a distinctive shape: **it is reproducible, tied to your instrumentation, and absent in the
same app run without it.** Everything else that looks like detection is usually one of these:

| Looks like detection | Usually is | How to tell |
|---|---|---|
| app dies right after attach | hook timing, a bad script, or a genuine RASP layer | run the same app with **no** hooks: alive? then it is your instrumentation or a hooking detector |
| app refuses to start at all | ABI mismatch, missing native lib for this device, install problem | check the live mapping (`scripts/lib_map.py`) and that a clean unmodified build starts |
| app exits on this device only | emulator/root detection, **or** a device-state problem | run preflight; try the same build on a different device class |
| app hangs forever | a frozen thread from a bad patch, or a real ANR | `pitfalls.md` P7 and the "never make it not return" rule |
| dynamic tool "cannot attach" | **the tool cannot work on this environment at all** | see Step 4 — this is the one people waste days on |

**Rule: reproduce with the control first.** Instrumentation-free run, then instrumented run, same
build. That single comparison separates "the app detects me" from "my tooling is broken", and it takes
one round.

## Step 2: if it *is* detection, decide by cost, not by pride

Three legitimate outcomes. Pick one deliberately and say which you picked.

**A. Work around it — only when the workaround is small and stable.**
Worth it when the detector is a simple, localised check you can neutralise in one place, and the
workaround lives in *your* environment rather than in the shipped artifact. Examples of the class:
running on a device the app does not object to, using a build that satisfies the check, or a single
one-line gate in a helper. Also legitimate: naming the artefact differently, using a different device
profile, or simply doing the work on a device that the app accepts.

**B. Change route.** When the workaround is a moving target, switch to static analysis and stay there.
This is the right answer more often than it feels like. Hooking-detection especially tends to escalate:
each hide provokes a stronger check, and you end up maintaining a cat-and-mouse setup that is worth
nothing at delivery time.

**C. Accept and report.** If the detection blocks the *deliverable* rather than your analysis — for
example, the app verifies something the user's device will not have — then the honest output is a
statement of what is blocked, with the evidence. Do not ship a build whose only purpose is to defeat a
detector you were not asked about.

**Signal to stop escalating:** you have spent more effort on the analysis environment than on the
change the user asked for. That is the drift this skill treats as most expensive, in its runtime form
(`long-task-discipline.md` §the most expensive drift).

## Step 3: locating the check — the order of search

Step 2 decides *whether* to fight. This step is the part the two steps around it do not provide:
**once you know a check fired, in what order do you look for it?** The order matters because the
cheap probes answer most cases and the expensive ones only pay off after a cheap probe has already
narrowed the field. Every stage below names its input signal, the smallest action that answers it,
the evidence that makes it true rather than plausible, and where to go when it does not.

Two shaping notes before the stages.

**Order is the whole content here.** Reading this as a menu and starting at the middle is how a
session becomes an arms race: each probe you add changes the process further, so the later probes are
measuring a target you already modified. Do them in order and stop as soon as one answers.

- **Stage order is a funnel, not a checklist.** Stage 1 is five minutes and rules out whole classes of
  problem; Stage 5 requires the offsets Stage 2 produced. Skipping forward costs more than it saves.
- **Every stage ends in `observed` or in a stated negative.** "No hook fired" is only a fact once you
  have shown the hook can fire on this target (`pitfalls.md` P25/P26 in tool form).

**Strength note.** The stages are a restatement, for judgement purposes, of a six-phase
anti-instrumentation pipeline published in `index-login/MobileRE-Skill`
(`https://github.com/index-login/MobileRE-Skill`, retrieved 2026-09). That project's phase *modules*
are not vendored here and none of its scripts are used; what is taken is the **order** and the
branch conditions, which are the parts that transfer. Stages 2, 3, 5 and 6 are **observed** as
mechanisms on this repository's own device (evidence and exact commands:
`references/evidence-summary.md` §The capability matrix). Stage 4's kill path was reached once and
is unstable across runs, so treat its detail there as `observed`-once, not reproducible.
Stage 1 is `observed` and is the one that most often ends the investigation without an escalation.

### Stage 0: rule out the two non-detection causes first

Before hooking anything: is the process alive at all, in what state, and does it die the same way
with nothing attached?

```bash
adb shell 'cat /proc/<pid>/status | head -4'   # state matters: D is uninterruptible sleep
adb shell 'cat /proc/<pid>/stat  | cut -d" " -f3'
```

**Observed failure that looks exactly like detection:** a target in **`D` (uninterruptible disk
sleep)** makes an attach hang and then fail, and makes a second attach report *"process not found"* —
while the process is still in `ps`. No detector is involved; a userspace attach needs the process to
run. On the measured run this was the actual cause, and it was read as "the app refuses
instrumentation" for one round. Check state before you blame the target, and check **whether attach
works on any other process on the same device** — that one-line control separates a broken toolchain
from a hostile target in a single command.

### Stage 1: a benign probe, to establish that your pipeline can fire at all

**Input signal:** nothing yet. **Action:** load an *observer-only* probe
(`scripts/anti_detect_probe.js`) that patches nothing. **Evidence it worked:** the probe's own
`armed` line and its environment self-report — `TracerPid`, which of your artefacts are visible in
the process's own maps, whether it can read `/proc/net/tcp` at all. **If nothing arrives:** the
problem is plumbing or liveness, not detection. Re-read Stage 0; do not escalate.

**The self-report is the cheapest half of this file's whole subject, and it is usually skipped.**
Before asking "does it detect frida", ask "is frida visible to this process". Measured on the test
device, a probe spawned into a target read 4 frida-named mappings in the target's own
`/proc/self/maps` before any check ran — so "was it detectable" was never in doubt, and the
remaining question was only which check reads it.

**Stream, do not batch, on a target that self-destructs.** A probe that reports only at the end of a
window reports *nothing* when the target dies inside the window — precisely the run that mattered.
Measured: three spawn-and-probe arms of one target; one delivered a full event sequence ending in a
self-destruct, the next two lost the script before its first timer fired. Emit a heartbeat and stream
each first hit. The heartbeat's absence at time *T* is itself the datum: it separates "the target was
quiet" from "the script was gone before *T*".

### Stage 2: name the detector, by caller offset

**Input signal:** Stage 1's environment events. **Action:** hook the path-access and process-control
surface (`open`/`openat`/`fopen`/`access`/`stat`/`readlink`, `dlopen`/`dlsym`, `pthread_create`,
`kill`/`tgkill`/`exit*`) and report, for each call, the **caller module + offset**. **Evidence:**
`libX.so+0x1cef8` — a named module and an address. **If no caller resolves:** you are on a runtime
that cannot unwind here; record the module and move to Stage 6's static path instead of adding a
third unwinding strategy.

This stage's product is a **name**, and everything after it is cheaper. Two branch conditions decide
which Stage 4 branch you take, so they are worth reading off explicitly:

| What Stage 2 shows | Branch | Why |
|---|---|---|
| the check runs on a thread the detector created itself (`pthread_create`/`clone` caller is the detector module) | **block at creation** | the polling loop never exists to fire |
| the check runs inline inside a library constructor, and the calls you can see are only libc wrappers | **Stage 3** | under that ordering a libc hook is the wrong layer |
| the detector is a *shell* library that also decrypts | **do not patch broadly** | the same module carries load-bearing work; scope to named offsets |

### Stage 3: if it fires before your hooks exist, take the constructor order

**Input signal:** the death happens before or during first library load, or Stage 2's caller offsets
all sit in a constructor path. **Action:** find the constructor dispatcher and hook it *before*
constructors run. **Evidence:** the module's `init_array` entries are visible and their addresses
map to the checks. **If the device's linker does not expose the symbol:** switch to the static route
(`scripts/svc_scan.py` on that library) rather than guessing an address.

```bash
# the symbol name is mangled; grep for the substring, not the bare name
readelf -sW <linker64> | grep call_constructors
```

**Measured:** on this repository's device the symbol exists as
`__dl__ZN6soinfo17call_constructorsEv` at `0x4a258` — a **mangled** name. A search for a bare
`call_constructors` export reports "absent" and sends the analyst to an offset-guessing path that
was never necessary. Confirm presence/absence before building either route.

**The measured cost of getting this stage wrong:** do not clear a module's whole `init_array`. A
shell library's constructor does payload decryption as well as detection; emptying it converts a
detectable app into a non-running one, which is a worse result than the detection was. Scope to
functions you have a reason to suspect — a per-function static scan for the syscall form in Stage 6
is how you get that reason.

### Stage 4: keep the process alive — deliberately, and with a stop condition

**Input signal:** every attempt shows events up to a point and then the process is gone. **Action:**
make the termination observable (record path and caller) and, if necessary, prevent it. **Evidence:**
the death is attributed to a module and an offset, not to "the platform". **If attributing it costs
more than three arms, stop attributing and switch to static.**

Two measured shapes, and they need opposite treatment:

- **A libc-visible kill.** Measured on a clean MASTI-style target: a probe saw
  `strstr("frida")` at ~300 ms and then the process was gone, with **no** tombstone, no crash and no
  ANR record — a clean self-exit. The abort path itself surfaced once as a libc `raise`/signal call;
  it did not surface on the later arms that died sooner. That instability is the finding: **on a
  fast detector the observable window is sub-second and not reproducible**, so a single successful
  attribution is not a pipeline.
- **A libc-invisible kill.** If a module issues `svc #0` itself, no libc-level hook can see it, and
  the absence of an event beside a death is the signal to go static (Stage 6).

**`exit_blocker`-style keepalive has a failure mode that looks like success.** Blocking the exit
turns a clean death into a spinner: the process stays alive, stops responding, and you can no longer
tell "the check is neutralised" from "the app is wedged". Keep the blocked-call count, a timeout, and
one behavioural check — does the UI still reach the state you care about — or the keepalive is
measuring itself.

### Stage 5: shellcode and runtime-generated code

**Input signal:** Stage 2's loader stream shows executable mappings appear that were never loaded
from a file. **Action:** watch allocation with execute permission and read-only-executable
transitions; disassemble around the allocation's caller. **Evidence:** an `mmap`/`mprotect` call with
execute permission whose caller offset is in the detector module. **If the region is unreadable:**
stop; the offsets from Stage 2 are all a static session needs.

A target can make itself harder to look at without doing anything exotic: on one measured run the
recovered caller chain sat inside `jit-cache`, i.e. **Java code the runtime had JIT-compiled**, not a
shipped library. A crash frame in JIT output cannot be mapped to a file offset. Expect it on any
API where the framework compiles reflection at runtime, and treat "the frame has no file" as a fact
about compilation, not as a hidden module.

### Stage 6: the precise stop, and the static alternative to it

**Input signal:** a named module + offset from Stage 2, Stage 3 or Stage 5. **Action:** neutralise
that site — or decide not to. **Evidence:** a fresh control run with the site left alone dies where
it died before, and the patched run does not. **If the offset came from a trace you could not
reproduce:** do not patch it; go to the static route below.

The static route is often strictly better than the dynamic one and needs no live process:

```bash
python scripts/svc_scan.py /data/local/tmp/libDetect.so
```

**Measured discriminator.** A module that contains **no** inline `svc` site for a termination syscall
cannot be bypassing libc for its kill — so a missing exit event is then a finding about your hook,
not about the target. Measured on this device: the ROM's `libc.so` carries exactly 4 termination
sites (`exit`, `exit_group`, `kill`, `tgkill`), and those are libc's *own* exported implementations —
so hooking `exit`/`kill` really does see callers that go through libc. A shell library on the other
hand showed 21 byte-scan "svc sites" that were all **data**, with no call-number load anywhere near
them: a byte scan for `svc` matches inside data, so read the neighbours before believing a count.
That distinction — structural absence vs. observed absence — is what Stage 6 is for.

### The routing chain, on one page

```
Stage 0  process state + does attach work on ANY process?     -> D-state / broken toolchain, not detection
Stage 1  observer-only probe + environment self-report        -> what the target can see
Stage 2  path/loader/thread/kill hooks with caller offsets    -> a module+offset name
   |-- caller is a created thread        -> block at creation (Stage 4, branch A)
   |-- death precedes hooks, or the checks are in a loader ctor -> Stage 3, or static (Stage 6)
Stage 3  constructor order / mangled symbol check             -> the check is reachable at all
Stage 4  attribute the kill, then decide whether to block it  -> attributed death, or "unreproducible"
Stage 5  executable mappings not backed by a file             -> shellcode / JIT, often a dead end
Stage 6  NOP one site, or prove statically that libc is enough -> observed before/after
```

## Step 2B: two boundaries this file adopts

**(a) Observers and interceptors are separate modules and stay separate.** An observation module must
not change behaviour, and an intervention module must not double as a monitor. This is the discipline
the pipeline above is built to survive: Stage 1's value is that its output describes the *original*
process, and the moment the same script also blocks an exit or NOPs a function, every later
observation belongs to a target that no longer exists. The practical version: a probe that watches
and a patch that neutralises are two files, loaded in two runs, and the runs are the experiment.
`scripts/anti_detect_probe.js` is the observer half and patches nothing by contract.

Be honest about the leak in that contract: **hooking is itself observable.** Attaching changes
timing, and on a hardened target the first event the probe recorded was a `dlopen` of the target's
own code followed within ~50 ms by a check — i.e. the act of being watched is part of the
environment the target is reacting to. Separation makes runs comparable to each other; it does not
make them a description of the untouched process.

**(b) Name the cost before you add another module, and know when to leave.** Each avoidance module
is another thing the target can notice and another reason a later result is unattributable, and the
detection is not standing still: a check that was a string compare becomes an inline syscall becomes
a native check in a module you have not looked at. Track three numbers, and stop when two of them
are true: how many bypass modules are loaded, whether the run needs a keepalive to stay up at all,
and whether the target only behaves under the full stack of modules. **When they are true, switch to
static** — that is the same conclusion as Step 2B, reached with a threshold instead of a judgement
call, and it is the exit this whole step needs so that Stage 6 does not become a permanent home.

## Step 4: when the tool cannot work here at all

Some environments cannot run a given dynamic tool, and no amount of trying will change that. Recognise
it and move on — this is a *finding about the environment*, and recording it prevents the next person
from repeating the attempt.

**The instructive class: an emulator that executes a different architecture than it reports.** A device
may advertise one ABI while the process runs libraries of another through a translation layer. This
shows up as a tool that reports the device is fine, then fails to attach, attach-and-die, or attach and
see nothing. Symptoms worth treating as a hard signal:

- the tool's own attach path fails with an error that mentions tracer, ptrace, or a debugger — on an
  environment where translation is in play;
- attaching kills the process immediately, repeatedly, with no Java stack;
- the tool attaches but **no** hook ever fires, including hooks on code you know runs.

**Do not spend the session proving it is impossible.** Establish it once, with one clean reproduction,
write the environment fact down, and switch to static.

**What to do instead:** the entire static toolchain is architecture-agnostic — string tables, code
structure, call-site counts, byte-level patching. None of it needs the app to run. If your verification
also needed the app to run, use the device-level observables instead: does the UI change, do the logs
fall silent, does a file appear or stop appearing. Those are properties of the shipped artifact, and they
do not care that you could not attach.

## Step 5: what a detection layer means for the deliverable

Two distinct questions — keep them separate, because conflating them produces either a broken artifact
or an unnecessary retreat.

1. **Does it block your analysis?** → handle with Step 2/3/4. This is your problem, and it is temporary.
2. **Will it block the patched build on the user's device?** → this is a property of the artifact. A
   root check that merely requires an unrooted device is usually irrelevant to a repackaged APK. A
   **self-integrity or signature check** is a different matter entirely, and it belongs to
   `references/native-tamper-and-suicide.md` and `references/signature-derived-keys.md`.

Ask explicitly: *does this check fire because of how the app is built, or because of where I am running
it?* Only the first kind follows your build into delivery.

**Root is an environment fact, not a defeat.** "Runs only on a rooted device" is a legitimate analysis
environment and an illegitimate deliverable when the request was an installable build for a normal phone.
Say which one you actually have.

## Step 6: keep a one-line environment fact

When you conclude that something cannot be done in this environment, write one line in the task record:

```
cannot: <tool/technique>  in <environment>   because: <observed failure>   route taken: <alternative>
```

That single line is what saves a future round. It is also the difference between "we could not attach,
so we did X" and an unqualified "dynamic analysis is impossible", which is a claim you have not earned
and which will mislead the next reader.

## Checklist

- [ ] **Located before escalating:** Stage 0 state check, an attach control on another process, then the
      stages in order — and stopped at the first stage that answered
- [ ] **Observer and interceptor are not in the same script**, and the observation run was kept free of
      any patch
- [ ] Detector named as **module+offset**, or the negative stated ("no caller resolvable on this runtime")
- [ ] **Cost measured, not felt:** bypass-module count, whether a keepalive is required, whether the
      target only runs under the full stack — two of three true means switch to static
- [ ] Controlled the comparison: same build with and without instrumentation
- [ ] Preflight run, so device state is excluded before blaming a detector
- [ ] Classified: detection vs environment vs my own tooling
- [ ] Chose A/B/C deliberately and can say which, and why
- [ ] If the tool cannot work here: established it **once**, recorded the fact, switched route
- [ ] Separated "blocks my analysis" from "blocks the deliverable"
- [ ] Nothing in the shipped artifact exists solely to fool a detector
- [ ] Recorded the one-line environment fact if a route was closed
