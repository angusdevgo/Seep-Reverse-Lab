# Native Tamper Response — When the Library Kills Its Own Process

Load this when the process dies **without a Java stack trace**, when a build that passed every
static check crashes seconds after launch, or when you are about to neutralise a native check.

This file exists because of one specific, expensive mistake. Read §The rule before you edit a
single byte of a shell's native library.

## The rule

> **Never neutralise a terminate path by making it not return. Make it return.**

A terminate routine is reached from ordinary code paths. If you replace it with something that
**never returns** — an infinite loop, a self-branch, a stub that spins — the caller never resumes,
locks are never released, and every unrelated thread that touches those locks wedges. You have not
suppressed the check; you have frozen the process.

The distinction decides the outcome:

| Neutralisation | Effect on the caller | Result |
|---|---|---|
| `ret` / return a benign value | continues normally | check suppressed, process healthy |
| spin / self-branch / `while(1)` | never resumes | process freezes, watchdog or user kills it, symptom looks unrelated |

**Two failure shapes this produces, both of which have been misread as "the patch did not work":**

- The app hangs with no crash record at all, then disappears. Logs show nothing, because nothing
  crashed — it stopped.
- The watchdog or a system supervisor kills the frozen process, producing
  `Force stopping … from uid 0` or an app-restart loop. The uid-0 killer is a strong tell: an app
  cannot spawn a root-owned killer, so the executioner is **outside** the app, which means the app
  froze rather than failed.

Both are self-inflicted and both are avoided by returning instead of spinning.

### The corollary: do not touch normal-path symbols

A hardening library imports a lot of libc. Some of those symbols are terminate paths; most are not.

**Symbols that must stay untouched** — they are on ordinary code paths and freezing them breaks
everything:

`pthread_exit` · `exit` · `abort` · `android_set_abort_message` · `snprintf` · `closedir` ·
`__cxa_atexit` · `__stack_chk_fail`

A concrete case: a set of hand-made patches rewired five PLT stubs to self-branches on one
architecture and a different five on another. On the first architecture two of the five were
`snprintf` and `closedir` — a string formatter and a directory-close — so the app froze on the
first log line. On the second the five included `pthread_exit`, so every thread that finished
wedged. The patches were meant to suppress a suicide check and instead destroyed the process.

**Before touching a stub, resolve what symbol it belongs to.** Do not infer it from the stub's
position or from a comment. See §Resolving a stub to its symbol.

## How a hardened library terminates the process

Enumerate these before you patch anything. Each has a different signature and a different remedy.

| Mechanism | Log signature | Has tombstone? | How to neutralise |
|---|---|---|---|
| `kill(getpid(), SIGKILL)` | `Process N exited due to signal 9 (Killed)`, **no** exit code, **no** tombstone | no | patch the call site or make the `kill` stub return 0 |
| `exit()` / `_exit()` | process ends with an exit code, no signal | no | find the caller; usually one branch of a check |
| `abort()` | `signal 6 (SIGABRT)` + tombstone | yes | usually a genuine assertion — find what tripped it |
| **Deliberate crash** (see §Deliberate-crash stubs) | `signal 11 (SIGSEGV)`, tiny `fault addr` such as `0x4`, `Cause: null pointer dereference` | yes | nop the faulting store |
| `tgkill` / `raise` | same as kill/abort | varies | often not imported at all — check the import table before assuming |

**Distinguish these before patching.** "The app crashed" is not a diagnosis. The signal number and
the presence or absence of a tombstone split the space in half; getting this wrong sends you to the
wrong layer for hours.

### Deliberate-crash stubs

The most deceptive mechanism: the library does not call anything. It **arranges a fault** so the
death looks like an ordinary bug.

```asm
; arm64 shape observed in the wild
mov  x0, #4          ; load a small constant…
mov  w1, #1
str  w1, [x0]        ; …and use it as a pointer. fault addr = 0x4
```

Runtime shape: `SIGSEGV`, `SEGV_MAPERR`, `fault addr 0x4` (or `0x0`/`0x8`), `Cause: null pointer
dereference`, and — critically — **the register holding that small constant value**.

How to recognise it rather than treating it as a real bug:

1. The faulting address is a **small integer**, not a plausible pointer.
2. Disassembling backwards from the faulting `pc` shows the constant loaded **a few instructions
   earlier, in the same basic block**, with nothing in between that could produce a real pointer.
3. The block sits immediately before a function epilogue (canary check + `ret`), i.e. the normal
   exit is right there and this store is bolted on in front of it.
4. There is often a **delay loop just above it** — `sleep`/`usleep` repeated N times — because this
   is a *watchdog*: wait a while, then die if the condition still holds. That delay is why the crash
   is always "a little while after launch" rather than immediate.

**Neutralise it by nop-ing the faulting store**, leaving the surrounding arithmetic alone. The
thread then falls through into the epilogue and returns normally. Do not remove the whole block:
the two `mov`s are harmless and keeping them makes the diff minimal and reviewable.

**This is why patching `kill` alone is not enough.** A deliberate crash uses no imported symbol at
all, so every PLT-level fix — including a correctly implemented one — leaves it untouched.

### Find every instance, not the first one

Search the binary for the **byte pattern**, not with a linear disassembler. The exact encoding is
architecture-specific and must be derived from the crash you already have, then searched as bytes:

- Take the faulting `pc`, read the instruction bytes backwards until you have the full constant-then-
  store sequence.
- Search the whole file for that byte sequence.
- If the search returns more than one hit, patch each; if it returns exactly one, you have the
  complete set — record that fact, it is a real result.

A linear disassembler is the wrong tool here for a reason covered in §Scanner traps.

## Resolving a stub to its symbol

When a stub's target is a PLT entry, the symbol comes from the relocation table, **not** from the
stub's bytes or its neighbours. Two architectures encode this differently:

- **x86_64** — the stub is `jmp qword ptr [rip+disp32]` (6 bytes). The target address is
  `stub_addr + 6 + disp32`; look that address up in the PLT relocation map.
- **aarch64** — the stub is **four instructions / 16 bytes** (`adrp` → `ldr` → `add` → `br`). The
  GOT address is `page(adrp) + add_imm`. Do not assume a 4-byte stub: a 16-byte stub leaves room
  for a **two-instruction replacement** (`mov x0, #0` + `ret`), which is exactly what you need, and
  assuming 4 bytes pushes you into borrowing the neighbouring slot — which belongs to a different
  symbol and breaks it.

`scripts/elf_plt.py` does both architectures, including the relocation lookup.

**Never splice in a neighbouring stub's bytes.** Stubs are laid out back to back; the next one
along is a different function, and corrupting it produces a second, unrelated failure that you will
then spend hours attributing.

## Patching a terminate path correctly

Work in this order.

1. **Confirm the mechanism first.** Get the tombstone or the signal number. Do not patch on a
   guess about *how* it dies.
2. **Decide between call-site and stub.** Call sites are precise but you must find all of them.
   A stub covers every caller at once, including ones your scan missed — but it changes behaviour
   for every symbol user, so it is only safe when that symbol means "terminate" and nothing else.
3. **For a stub, return success, not failure.** Callers commonly inspect the return value. Returning
   **0** (success) lets the caller take its "already handled" branch; returning **-1** pushes it
   into an error path that may try a different termination method. Make the stub *succeed*.
4. **Preserve every byte you did not intend to change.** Record the original bytes so the patch is
   reversible and auditable.
5. **Re-verify the file after patching.** Length unchanged, only the intended offsets differ, and
   the normal-path symbols are byte-identical to the original. `scripts/elf_plt.py --diff` prints
   exactly that.

### What "faithful suppression" looks like

A library that decides "tampered" and then cannot terminate has an inconsistent state — it believes
it has killed the process and continues. That is **acceptable and usually harmless**, because the
terminate path is the end of the check; nothing downstream re-reads "did I die". But verify it
rather than assuming: after a successful suppression the app must reach its **normal UI and stay
there**, not loop through half-initialised states.

## ELF hardening you will meet in these targets

Hardening libraries are not normal ELF files. Assume the following until measured otherwise.

### Forged section headers

A shell may ship a library whose section header table is deliberately wrong — `.text` sized to a
handful of bytes, `.dynsym` truncated, sections overlapping. Tools that walk sections therefore
produce **confidently wrong** answers (a symbol list with one entry, an import table that is empty).

**Work from the program headers instead.** `PT_LOAD` gives you the real mapped segments and their
permissions; `PT_DYNAMIC` gives you the pointers you need, walked by hand:

```
DT_STRTAB(5)  DT_SYMTAB(6)  DT_STRSZ(10)  DT_SYMENT(11)
DT_JMPREL(23) DT_PLTRELSZ(2) DT_PLTREL(20) DT_PLTGOT(3)
```

Then translate any virtual address to a file offset through the `PT_LOAD` that contains it. A
library with forged sections that yields a full import list this way is a good sign; one that
still yields almost nothing means the hardening is deeper and you should say so rather than
reporting the truncated result as the truth.

### Function boundaries come from `PT_GNU_EH_FRAME`, not from prologue guessing

You will need "where does this function start". Two bad answers and one good one:

- **Reverse-decoding backwards from a call site does not work on aarch64.** Almost any 4-byte
  window decodes as *some* instruction, so a naive scanner reports hundreds of "function starts"
  that are all fiction.
- **Guessing at prologues** (`sub sp, sp, #imm` + `stp`) produces a plausible set with no guarantee
  of completeness.
- **`PT_GNU_EH_FRAME` is authoritative.** If the segment survives (it usually does, because
  unwinding is needed at runtime), parsing it yields the real function entry table — every entry,
  exactly. It is several lines of code and it removes an entire class of wrong conclusions.

**Check for it first.** If it is present, use it; if it is absent, say your boundary list is
heuristic.

### A function's entry is not where its logic is

Callers reach a routine through several routes: a direct branch, a cached table slot, or a function
pointer in writable data. Rewriting the entry point only covers the first. If a call resolves
through a cached pointer, your entry-point change is invisible to it — so before patching an entry,
scan for the other routes (`scripts/elf_plt.py`, or a byte-pattern scan for the address).

## Scanner traps

**A linear disassembler can stop silently.** Given a buffer whose start is not code, a decoder may
return a handful of instructions and then nothing, with no error. Concluding "there are no such
call sites in this library" from that output is a false negative with real consequences.

Guards, in order of preference:

1. **Byte-pattern search** for a sequence you already know (from a crash or a known call site).
   Fast, exhaustive, no decoder involved.
2. **Fixed-bit-pattern scans** for instruction classes whose encoding is regular — the branch
   instructions are the useful ones here (`BL`/`B` on aarch64, `call rel32` on x86_64). This finds
   every call site without depending on linear decoding.
3. **Resynchronising scan** — decode, and on failure advance by one instruction unit (4 bytes on
   fixed-width aarch64, 1 byte on x86_64) and retry. Slower, but it does not stop early.

Whichever you use, **state which one you used and what it can miss**. "No hits" from a scan whose
coverage you cannot describe is not evidence.

## Deciding whether a dynamic-resolution path matters

Hardening libraries frequently build a table of function pointers with `dlopen` + `dlsym` — often
40+ symbols including terminate calls. This raises an obvious worry: *a call through that table
bypasses the PLT stub, so my stub patch does nothing.*

**Measure it instead of assuming either way.** For each symbol of interest, find whether its table
slot is ever **read**:

- Locate the slot's address (the store from the `dlsym` return, or the table base + index).
- Search the code for instructions that load from that address (`adrp`+`add`+`ldr` on aarch64).
- **Zero readers means the entry is written and never used.** The table is a redundant fast path,
  not a bypass, and PLT-level patching is complete.

Real outcome from a hardened target: the `kill` slot had **zero** readers while the `exit` slot had
exactly one, inside a routine that was already suppressed — so no dynamic-resolution bypass existed
at all, and the expensive "patch `dlsym` itself" plan would have broken 40 unrelated symbols for
nothing.

**Do not blanket-patch a symbol resolver.** It feeds `open`, `read`, `mmap`, `dlopen` and more.
Changing its behaviour to reach one terminate symbol is a large blast radius for a problem you may
not have.

## What these checks actually detect — and why your environment changes the answer

A terminate path is not reading your patch. It is reading **the world around the process**, so what
trips it is environmental, and the same build can die in one setup and live in another.

| Signal | Typical probe |
|---|---|
| a debugger is attached | `ptrace`, `TracerPid` in `/proc/self/status`, `prctl` |
| the parent process was replaced | a cached `getppid()` compared against a fresh one |
| the process was suspended | wait status showing `SIGSTOP` / `SIGTRAP` |
| instrumentation is present | hook-framework artefacts: listening ports, thread names, unusual mappings |
| a "non-standard" environment | root binaries, emulator fingerprints, writable system paths, build props |

Two consequences decide whether your experiments mean anything at all:

1. **A pass under translation is not a pass on hardware.** Under an ARM-on-x86 translator the
   environment probes return different answers — in *both* directions. A check that fires natively
   may stay quiet here, and one that is quiet natively may fire. Emulator or translated results are
   a mid-task checkpoint, never the final verdict.

2. **Your own tooling can be the thing that trips it.** If the app only dies while you are attached,
   you are looking at a probe aimed at *you*, not at the app's ordinary startup path. Reproduce with
   nothing attached before you patch anything.

**Run the unmodified original through the identical conditions first.** If it dies the same way, the
check is firing on the environment rather than on your change, and every conclusion drawn from the
patched build's death is void. This is the same control-build rule as everywhere else in this skill,
and it is the single cheapest way to avoid chasing a detection that is not about you.

## Verification

A native suppression earns no credit until:

1. The process **survives the window in which it used to die** — and that window must be measured,
   not guessed. If the observed death was ~40 s after launch, a 30-second test proves nothing.
2. It then **keeps surviving** through real interaction, not just idling.
3. `crash`/`tombstone` buffers are clean, **and** the process id never changed (a restart with a new
   pid is a death even when nothing logged a crash).
4. The normal-path symbols are byte-identical to the original build.
5. A **control build** — same pipeline, no native patch — still dies the same way. Without the
   control you cannot tell suppression from an unrelated change in timing.

**Record the observed time-to-death before patching.** It is the only thing that later tells you
whether your patch worked or merely moved the window.
