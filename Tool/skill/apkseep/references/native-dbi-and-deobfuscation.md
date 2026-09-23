# Native DBI and deobfuscation

**Load this when static disassembly of a `.so` has stopped producing information** — an exported
function decompiles into a dispatcher loop and arithmetic soup, a symbol you need has no name, or you
must answer "what actually ran" instead of "what could run". This file covers instruction-level
dynamic tracing: what a trace can and cannot decide, how to record one with the scripts in
`scripts/`, and where it hands off to emulation and symbolic execution.

**Hand-off.** `native-and-so.md` owns the APK-side conclusions about a library — which `.so` is
loaded, which ABI is executing, whether a hook can observe anything, how to neutralise a terminate
path by returning. This file owns execution-level evidence. If the question is "did my patch cause
the death", that is `native-and-so.md` and `native-tamper-and-suicide.md`; if it is "which blocks did
this function really execute, and how often", it is here.

**Claim strength.** `measured` = an exact command and its output exist in
`references/evidence-summary.md` §The capability matrix. `inferred` = it follows from measured behaviour or
from documented behaviour of the tool. `unverified` = reported by someone else or reasoned from
first principles without a run. The distinction matters more here than usual, because the honest
result of this pass is that **the trace pipeline is unverified on the test device** — see.

## 1. Which obfuscation are you looking at

Obfuscator-LLVM ships three transforms, and one target usually carries all three. Identify by
**which one made static reading fail**, because each is undone by a different observation.

| Transform | Static shape | Dynamic signature | What removes it |
|---|---|---|---|
| **Control-flow flattening** | One dominator block at the top of the function, reached from everywhere; a state variable (register or stack slot) assigned a constant before each jump back; a `switch`/jump table dispatch; the original block order is gone | The dispatcher block dominates the execution histogram by a wide margin; real blocks appear between dispatcher entries; execution sequence looks like `D R1 D R2 D R3 D` | Trace histogram + the state variable's constants: each dispatcher entry is preceded by a store of the next real block's id |
| **Bogus control flow (opaque predicate)** | A branch whose condition is algebraically constant (`(x*x) >= 0`, `x*x % 2 == 0`), with a junk block on the impossible side; junk blocks reference unreachable names | The junk branch **never appears** in the trace at all: not once, at any input | Trace absence, and then dead-code deletion of the never-taken side. Absence in a trace is only evidence if the trace covers the input that would take it |
| **Instruction substitution** | Arithmetic that is correct but unrecognisable: add chains with negated constants, `xor`/`and`/`or` rewrites of a comparison, MBA identities | The function's **result** is still correct at its boundary, and the single-step value at a known point (e.g. the return register) matches the un-obfuscated expectation | Symbolic execution or a brute-force input sweep; a trace alone does not simplify arithmetic |

Worked example of the distinction: a flattened function with substituted instructions produces a
trace whose histogram has an obvious top, but the arithmetic between dispatcher entries still tells
you nothing. Flattening is a **control**-flow problem and the trace answers it; substitution is a
**data**-flow problem and needs.

**Reported, not verified here:** a community write-up of this exact pipeline — trace, aggregate,
solve with a symbolic executor, patch the binary — is
[基于动态指令追踪与符号执行对抗OLLVM控制流平坦化的工程化实践](https://cloud.tencent.com/developer/article/2721228)
(cloud.tencent.com/developer/article/2721228, published 2026-08-05). It reports, on a 2,800-block
x64 fixture: 15 s of tracing ≈ 220 MB of raw log, aggregation to 48 KB of block records, ~12 min of
parallel symbolic execution resolving 67 dispatcher targets, and 1.2 s of binary patching over 147
sites. **Those numbers are the author's, on a Windows x64 DLL, and were not reproduced here** —
treat them as an order-of-magnitude sketch for the data-reduction ratio (raw log to block table is
roughly 4000:1 there), not as a budget for an arm64 Android target. The article's code snippets are
illustrative rather than runnable: its `onReceive` handler indexes parsed events by field name
(`item.kind`, `item.start`), while `Stalker.parse(..., {stringify: false})` returns **positional
arrays**. Take the method from that article; take the API shape from this repository and from the
script header in `scripts/stalker_trace.js`.

## 2. Pick the observation before you pick the tool

| Question | Observation | Tool |
|---|---|---|
| Which blocks executed, and how often? | Block-level trace with execution counts | `scripts/stalker_trace.js` + `scripts/stalker_report.py` |
| Which functions inside the module call each other? | Call edges from the same trace | same pair (`call` events) |
| Which imported function does this stub reach? | Relocation table, not trace | `scripts/elf_plt.py` |
| Where did the process die, and did it look arranged? | Crash record, signal, fault address, backtrace split by owner | `scripts/native_crash.py` |
| What value must the state variable have to reach block X? | Constraint solving over the dispatcher | angr / Triton () |
| What is the value at a specific point for a specific input? | Deterministic per-instruction replay with memory operands | QBDI () |
| What does this code do with no device at all? | Emulation of the `.so` with a synthetic environment | unidbg / Unicorn / QEMU |

The first two rows are one run of one script — take both. `elf_plt.py` and `native_crash.py` are not
competitors here: they answer a symbol and a death respectively, and both work when no trace can be
taken at all.

## 3. Recording a trace with `scripts/stalker_trace.js`

Frida Stalker recompiles every basic block a followed thread executes and hands the events back to
JavaScript. It needs no symbols, no source and no disassembler on the host, which is exactly why it
works on stripped OLLVM output.

**Three rules, each one a failure mode if broken**

1. **Follow one trigger, not the whole process.** An unrestricted follow of a busy thread produces
   gigabytes and slows the target down until it dies.
2. **Filter to one module.** `targetModule` is the only module whose blocks are reported; call edges
   report when either end is inside it. Filtering happens on the device, not in post-processing,
   which is what keeps the log usable.
3. **Cap the volume.** `maxBlocks` stops the trace instead of letting the log eat the disk, and the
   `DONE` line records whether truncation happened.

**Configuration** (edit `CONFIG` in the script, or override at runtime through `rpc.exports.config`
/ `script.post({type:'cfg', payload:{...}})`):

| Key | Meaning |
|---|---|
| `targetModule` | the one `.so` whose blocks are reported |
| `trigger` | `{kind:'export', module, export}` — start on a named export (a JNI function is the classic); `{kind:'offset', module, offset}` — start at module-relative offset; `{kind:'java', cls, method}` — start at the Java→native boundary; `{kind:'main'}` — follow the thread right after load |
| `followMs` | hard stop, so a forgotten trace cannot kill the process |
| `maxBlocks` | event cap; the `DONE` line reports truncation |
| `events.compile` | first translation of each block — deduplicated block set in first-visit order |
| `events.block` | every executed block — the execution histogram |
| `events.call` | call edges |
| `events.exec` | **per instruction; enormous.** Enable only around a known point |
| `events.ret` | return edges |

**Customising what gets translated (`transform`).** Event flags shape *what you are told*; the
`transform` callback shapes *what runs*. It fires before a block is translated and receives the
instruction iterator, so it can rewrite the code Stalker is about to execute — inline a counter at one
call site, neutralise a logging call inside a hot loop, or substitute a value at the one address you
care about. Reach for it when the question is "is this site reached, and how often" rather than "which
blocks ran"; do not reach for it when the answer must be an observation, because a transform changes
the process's behaviour and stops being passive measurement. Two properties to respect: it can run
once per block per thread, so any rewrite must be idempotent, and the rewritten bytes are the DBI's
copy, so a crash inside them will not point at a file offset. `inferred`: `scripts/stalker_trace.js`
uses events and `onReceive` only; the transform route is documented here, not exercised by this
repository's pass.

**Running it.** With the bundled injector, which writes every event to a log file *and* stdout:

```
python scripts/run_probe.py scripts/stalker_trace.js 1 --pkg <pkg> --via usb --log trace.log
```

With any driver that speaks Frida's rpc, so no file edit is needed:

```js
script.exports.config({ targetModule: 'libapp.so',
                        trigger: { kind: 'offset', module: 'libapp.so', offset: 0x9f6c0 },
                        followMs: 3000, maxBlocks: 50000 });
script.exports.start(<tid>);   // follow this thread
script.exports.status();
script.exports.stop();
```

Pass `start(tid)` explicitly rather than relying on the default. **`Process.getMainThreadId()` is
not the Android main thread in practice**: on the measured run below, a process with pid `19938` was
followed on tid `25606`, and an idle-looking thread produced zero events. On Android the main thread
tid equals the pid, which is the value to start from.

**Output grammar** (one logical line per event; `scripts/stalker_report.py` parses it, including
logs where each line is wrapped by `run_probe.py` as `[host ts] [dev ts] TRACE ...`):

```
READY ...            config echo and module status; nothing works before it
MOD name base=0x.. size=.. path=..
BB <seq> <mod>+0x<offset>            block first translated (dedup'd skeleton)
BLK <seq> <mod>+0x<offset> [size=n]  block executed (histogram input)
CALL <depth> <from> -> <to>          call edge
DONE reason=timeout|trigger-leave|maxBlocks|stop-rpc blocks=n blk=n calls=n truncated=0|1
FATAL / TRIG-FAIL                    what did not install and why; the script keeps running
```

**Reducing the log**

```
python scripts/stalker_report.py trace.log --top 30 --skeleton 80 --edges 15 --json report.json
```

Four reductions, each answering a different question: the **execution histogram** (top of the list =
dispatcher candidate), the **first-visit order** (deduplicated block set ≈ CFG skeleton with the
flattening state machine stripped out), the **call-edge table** (module-internal communication with
no symbols), and the **collapsed execution sequence** (`block*N -> block -> ...`, which is where the
`D -> R -> D -> R` flattening rhythm becomes visible).

Diagnostics the report prints, and what they mean:

- `DONE ... truncated=1` — the trace hit `maxBlocks`. Ratios remain useful; **absolute counts do
  not**, and a claim about a dispatcher's multiplicity must be re-measured with a higher cap.
- `zero BLK with nonzero BB` — the thread was translated but executed nothing in-window: the window
  closed, or the trigger returned immediately.
- `zero BB and zero BLK with DONE present` — the module never ran on the followed thread. Change the
  thread or the trigger; do not tune the follow time.
- Everything zero **and no `DONE`** — the trace never started. Read the `READY` / `TRIG-FAIL` lines
  first; that is a plumbing problem, not an analysis result.

## 4. Stalker, QBDI, or emulation

| Situation | Choice | Why |
|---|---|---|
| Need block-level coverage and execution counts on a real device, no per-instruction semantics | **Stalker** | Cheapest to start, no host toolchain, works on code with no symbols |
| Need per-instruction values, memory operands, or a deterministic replay that can be re-run at a recorded PC | **QBDI** (QuarkslaB Dynamic Binary Instrumentation), via its Frida binding | An independent DBI engine with its own register/memory API; the trace is a program, not a log. It instruments at a different layer than Stalker, which matters on ART: Stalker translates the code it sees, QBDI exposes the instruction stream and its operands directly |
| Need to hurt the target as little as possible while instrumenting a hot path | **QBDI** | Deterministic, no reliance on the app's own JIT/AOT output |
| Need a result with **no device and no app process** — a hardened sample refuses to run, or the algorithm must be called thousands of times | **Emulation** (unidbg, Unicorn, QEMU) | Runs the `.so` in a synthetic environment with JNI stubs; completely different trade-off (environment fidelity for scale) |
| Need "what input reaches block X" rather than "what happened for input I" | **Symbolic execution** () | A trace is one path; a solver enumerates the condition |

**Stalker and ART do not compose for free.** The followed thread's code can be recompiled by ART's
JIT while Stalker has already translated it, and a block's address is only meaningful inside one
process lifetime. Practical consequences: keys in a log are `module+offset` and stay comparable
across runs only for code that is mapped from file; do not compare a `libart`-materialized block
address between two runs; and never place a follow/unfollow pair on a hot function (measured failure
in).

### The cost is not linear, and on arm64 it decides the tool choice

Two costs decide whether Stalker is the right tool, and neither is visible in the API:

- **Translation multiplier.** A followed thread pays a large constant factor on every translated
  block. Community reporting for arm64 puts it at **20-50x**; the mechanism is not controversial
  (every block is copied into the DBI's code cache and routed through a dispatcher), while the exact
  number is workload-dependent. This one is `inferred` — this repository has not measured the
  multiplier itself, only its consequences below.
- **What you let into the trace.** Every block of every library the thread touches is a candidate.
  Following into `libc` / `libart` / `libhwui` is how a four-second window becomes a device-wide
  event: measured here, one such run took the test phone's `load average` to `34.11` on 8 cores and
  destroyed a co-running job's attach ().

`Stalker.exclude()` is the control for the second cost, and it is not optional.
`scripts/stalker_trace.js` applies it before `follow()` from its `excludeModules` list and reports
what it actually excluded on one `EXCL` line — read that line before believing any trace, because a
module that was not loaded at follow time was **not** excluded. Exclude every system library you are
not studying; the target module is never excluded even if its name appears in the list.

Three failure shapes follow from ignoring this: deadlock, a watchdog `SIGABRT`, and the zero-event
trace. The deadlock and the watchdog shape remain community reports (`inferred`); the other two were
measured, **and the measurement splits the claim in two** — the split matters more than the summary:

| Arm — one device, one package, one module, 6 s follow | Outcome |
|---|---|
| attach + resume, **no follow** | process survives |
| follow, `excludeModules: []` | **process dies**, script destroyed |
| follow, 20 system modules excluded | process survives, **but `blocks=0 blk=0 calls=0`** |

Exclusion is what keeps the target alive — now `observed`, with the no-follow arm ruling out "it
would have died under frida anyway". But exclusion does **not** restore event delivery: the
zero-event trace survived the treatment arm unchanged. Treat those as two problems, and do not offer
`exclude` as the fix for a follow that delivers nothing. Commands and outputs:
`references/evidence-summary.md` §The capability matrix.

**arm64 also raises the floor.** PAC/BTI-bearing code gives a translator more ways to mis-handle a
block than armv7 did, which is one more reason a trace that works on an emulator is not evidence
about a device. Treat any arm64 result as needing a control run (a followed thread executing a known
loop, nonzero `BLK` lines) before it is interpreted.

**Emulation is a legitimate alternative, not a consolation prize.** When the target is a pure
computation inside a `.so` and its environment can be faked, a Unidbg/Unicorn trace can be both
faster and more stable than Stalker on a real arm64 device: no device load, no watchdog, no PAC, and
a deterministic replay. That inversion of the usual intuition is half the reason
`emulation-and-rpc.md` exists — decide with its decision table rather than by habit.

## 5. From a trace to a deobfuscated function (inferred)

This is the part the community write-up above also describes, and it is **inferred** here — the
trace end was not reproducible on the test device, so the steps below are a method, not a record.

1. **Find the dispatcher.** Rank by execution count. In a flattened function the dispatcher runs
   once per real block; loops multiply it further. A block that is (a) at the top by a wide margin,
   (b) entered from many distinct predecessors, and (c) followed by many distinct successors, is the
   dispatcher. `stalker_report.py` prints exactly the three items needed to check that.
2. **Find the state variable.** Disassemble the dispatcher entry window statically (the offset is in
   the trace, so no symbol is needed). Look for the register or stack slot written immediately
   before the indirect branch; in flattened output this is the value the dispatch table is indexed
   by. If more than one candidate exists, correlate: the state variable is the one whose written
   constants match the distinct block ids seen in the trace.
3. **Recover the real CFG.** Convert the flat sequence into edges: `dispatcher → real block →
   dispatcher`. The real blocks' order and repetition come from the trace; the state constants come
   from step 2; the mapping `state value → real block` turns the dispatcher into a jump table you
   can then remove in the binary (the LIEF step in the write-up).
4. **Solve what the trace did not cover.** A trace is one input's path. For a state value you never
   observed, symbolically execute the dispatcher **only** (a few tens of bytes: load the state,
   bounds-check it, index the table) rather than the whole function. This is where angr or Triton
   earns its cost: the entry point is the dispatcher offset the trace gave you, and the goal is the
   table index, not the program's semantics. Reported pitfall from the same write-up, worth repeating
   because it is structural: OLLVM inserts transitions that land outside the table, so prune states
   whose index exceeds the table bound instead of letting the solver chase them.
5. **Only then patch the binary.** Direct-branch rewriting must respect instruction length: an
   absolute jump needs more bytes than the `mov; jmp` pair it replaces, so pad rather than move
   anything. `scripts/elf_plt.py` is the tool that tells you what a rewritten site actually reaches
   (by relocation, not by position), and a byte-diff of two builds is how you prove your patch set is
   what you think it is.

## 6. Failure modes

**Zero events, follow installed (measured, cause unverified).** With host frida 16.7.19 and a
matching on-device frida-server 16.7.19 on Android 11 / arm64, `Stalker.follow` on a main thread for
4 s produced `blocks=0 blk=0 calls=0` on two different system processes, and an `export`-triggered
follow produced `reason=trigger-leave blocks=0` on every one of hundreds of firings. Every line
before that was healthy: `READY`, `TRIG following tid=…`, `MOD libc.so base=0x…`. The conclusion to
carry forward is narrow and should not be widened: **on that combination, follow installs but events
do not arrive in `onReceive`.** It is not a licence to assume Stalker is broken everywhere, and not
evidence about any other ROM, frida version or target. Validate the pipeline before trusting a zero
result: follow a thread you control executing a known loop, and confirm nonzero `BLK` lines.

**High-frequency follow/unfollow crashes the target (measured).** Using a hot libc export as the
trigger — every call starts a follow and every return ends it — a system UI process died with
`SIGSEGV` after hundreds of cycles; the crash record's frame `#00` sat in an anonymous region (the
DBI's code cache) and the return address led into `libart`. The process restarted under a new pid.
The lesson is not "Stalker is unsafe"; it is **do not use a hot function as a follow trigger**, and
do not build a follow/unfollow cycle per-call in a hot path. A single follow of a chosen thread for a
bounded window is the shape that works.

**The device becomes the experiment (measured).** While this pipeline was running, the test device's
`load average` reached `34.11` on an 8-core mid-range phone, and a co-running dynamic job on the same
phone (a dex-dumping attach belonging to another task) was destroyed mid-flight. On a shared device
these are not independent experiments: one heavy DBI run makes every other dynamic result
unattributable. Announce the window, keep `followMs` in the low seconds, cap `maxBlocks`, never spawn
when attach is enough, and treat a `script has been destroyed` in a *different* job as a signal that
your load — not that job's code — is the variable. This is `long-task-discipline.md` §single-variable
discipline applied to hardware.

**A trace of a VM is a trace of the interpreter.** If the target is a virtualized function (private
bytecode executed by a handler loop), Stalker will happily report the interpreter's blocks: a huge,
flat, repetitive histogram around one dispatch loop. That is a valid finding — it tells you the code
is virtualized — but it is **not** the guest program's control flow. Recovering that needs handler
identification and a private opcode table; see
`code-virtualization-and-custom-linkers.md`, and do not present an interpreter trace as the
deobfuscated function.

**Instrumentation was detected before you started.** If the process dies when you attach, refuses to
run under root, or the module you want is never loaded while attached, the problem is upstream of
this file: read the first section of `detection-and-anti-analysis.md` before escalating the trace,
because the cheap answer is usually to switch to static analysis with `elf_plt.py` and
`native_crash.py`, not to fight the detector.

## 7. Reporting what a trace proves

- A trace proves **what executed on the followed thread inside the followed window**. It does not
  prove absence: `BB` never appearing means it did not run *for that input, in that window* — which
  is meaningful for an opaque-predicate junk block only when the rest of the analysis says the input
  would have taken it.
- Counts are evidence only when `truncated=0`. State the cap.
- A dispatcher identification is a hypothesis about a block's role. Confirm it by disassembling the
  block and finding the table it indexes; a high count alone is also what a spin loop or a memory
  allocator's fast path looks like.
- Write the product's before/after into the evidence record condensed in `references/evidence-summary.md` §Where the full record lives, with the exact command, the
  module, the offsets, and the strength label. The next person's first question is "was the pipeline
  known to work when you got that zero", and the answer belongs in that record, not in a footnote.
