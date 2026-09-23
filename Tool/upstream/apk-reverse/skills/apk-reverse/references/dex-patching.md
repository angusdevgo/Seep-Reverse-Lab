# Dex patching — choosing and executing the surgical edit

The single most important decision in a patch task. Get this wrong and you produce an APK that assembles perfectly and dies at runtime.


**Load this when:** you have located the class and method to change and must choose the edit technique. It gives the least-destructive-first order and the signal that says a byte patch is not enough.

## Pick the least destructive technique that can express your change

Ordered from safest to most dangerous.

| # | Technique | Expresses | Structure risk | Use when |
|---|---|---|---|---|
| 1 | **dexlib2 method-level rewrite** | Replace a method's implementation (return a constant, no-op, emit a fixed value) | **Lowest** — only the target `code_item` changes | Default choice. Any behavior change that can be expressed as "this method now does X instead" |
| 2 | **Byte-level string constant patch** | Change a string literal to another of **equal length** | Medium — must preserve `string_ids` ordering (see P2) | Renaming a path/key/protocol token |
| 3 | **Resource / asset edit** | Change a config file, JSON, image, or bundled jar | Low (no dex change) | The behavior is data-driven |
| 4 | **Manifest edit** | Disable a component, drop a permission, flip a flag | Low, but re-signing required | Turning off a service/receiver/activity |
| 5 | **Whole-tree smali round-trip** | Arbitrary code edits | **High** — breaks R8 output (see P3) | Last resort, and verify by running |

**Do not reach for #5 because it is familiar.** It is the most likely to produce a broken build.

## Where to patch: pick the layer, not the symptom

Ads and gates can be suppressed at several layers. Higher in this list = smaller blast radius.

| Layer | What it looks like | Example | Risk |
|---|---|---|---|
| **SDK initialization** | A single helper that calls `Sdk.init()` | `AdHelper.k(Application)` | Low — SDK never starts, nothing else depends on it |
| **Feature entry point** | The app method that shows the thing | `AdHelper.showSplash()`, `showReward()` | Low–medium — must preserve callbacks the caller awaits |
| **Data consumption** | Where a server list is filtered/rendered | filter out a `position` before it reaches UI state | Medium — must not break sibling data |
| **Renderer** | The composable/view for a **specific** element | a dedicated ad card composable | **High** — generic components are shared (see P6) |
| **Transport** | Blocking/repointing an endpoint | `/app/adverts` → dead path | **Very high** — shared endpoints take screens down (see P5) |

**Rule:** prefer the highest layer (closest to the SDK/feature) that produces the required effect. Never go to the transport layer to hide a UI element.

## Before you patch a method: blast-radius check

```bash
python scripts/find_refs.py <smali_tree|dex|dir|apk> 'Lcom/pkg/Helper;->methodName(args)RetType'
```

Read the `[scanned]` line before the count. It reports how many inputs were actually opened, and
`[scanned] 0 file(s)` exits 2 with the reason: an unsupported path, a typo, or a directory of archives
is **not** the same answer as "read 2 dex files and found nothing", and the two once printed
identically — which put a false zero on exactly the decision this check exists to protect. A dex input
is decoded directly (`dexutil.py`), so baksmali is not required.

- **1–3 callers, all in the same feature area** → safe to patch.
- **Many callers, or callers across unrelated packages** → it is a general utility. Do not patch it. Go one level up and patch the specific caller instead.
- **Look at the parameters too.** If the signature mentions `Modifier`, `ContentScale`, `ColorFormat`, `Shape`, `View`, or a content-generic model type, it is not specific to your target.

Real example: a composable `(AdModel, ColorScheme, Modifier, Function0, ContentScale, Shape, Composer, II)V` looked ad-specific because of its first parameter. It was actually the shared image-card renderer; neutering it removed all cover art and broke playback.

## Technique 1: dexlib2 method-level rewrite (preferred)

Concept: load the dex, find the target class, replace **only** the target method's implementation, write a new dex. Nothing else is touched.

See `scripts/dexpatch/` for a working Java implementation and build instructions.

Shape of the code:

```java
DexFile dex = DexFileFactory.loadDexFile(new File(in), Opcodes.forApi(API));
List<ClassDef> out = new ArrayList<>();
for (ClassDef cd : dex.getClasses()) {
    List<Method> direct  = new ArrayList<>();  for (Method m : cd.getDirectMethods())   direct.add(m);
    List<Method> virtual = new ArrayList<>();  for (Method m : cd.getVirtualMethods())  virtual.add(m);
    boolean touched = false;
    // ... for the target class: find the method, build new instructions, list.set(i, newMethod)
    out.add(touched
        ? new ImmutableClassDef(cd.getType(), cd.getAccessFlags(), cd.getSuperclass(), cd.getInterfaces(),
                                cd.getSourceFile(), cd.getAnnotations(), cd.getStaticFields(),
                                cd.getInstanceFields(), direct, virtual)
        : cd);
}
DexFileFactory.writeDexFile(out, new ImmutableDexFile(Opcodes.forApi(API), out));
```

### Practical details that decide success

- **`direct` vs `virtual`.** `static`, `private`, and constructors live in `directMethods`; everything else (including `public final`) lives in `virtualMethods`. **Scan both** when searching. A "method not found" that is actually "in the other list" wastes a lot of time.
- **Preserve the register count.** Keep `m.getImplementation().getRegisterCount()`. `registers` must be `>= parameterRegisters`, and parameter registers are the **highest-numbered** ones: with `registers = N` and `k` parameters (including `this` for non-static), `p0 = N - k`.
- **Method parameters** come from the prototype. For `(Ljava/lang/Object;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;` on an instance method, `k = 3` → `p0=3, p1=4, p2=5` when `registers = 6`.
- **`const-wide` needs the 64-bit instruction form.** `ImmutableInstruction51l`, not `31i`.
- **Instruction register operands in `35c` form** (invoke) are `(opcode, registerCount, regC, regD, regE, regF, regG, ref)`. `invoke-static {v1, v2}, ...` → `registerCount=2, regC=1, regD=2`.
- **Every method body must end with a return of the right type.**
- **One dex, one write pass.** If you need two edits to the same dex, do them in the same program (see P4).
- **Null `tryBlocks` / `debugItems` on the rewritten method is fine** — you are replacing the whole body.

### Common rewrites

**Return a boolean constant** (`Z`):
```
const/4 v0, 0x1
return v0
```
`registers` = original count is fine; `const/4` needs a 4-bit register (`v0`–`v15`).

**No-op** (`V`):
```
return-void
```

**Return an object/empty collection**: build the constant, then `return-object`. For `java.lang.Long`, `const-wide` + `Long->valueOf(J)` + `move-result-object`.

**Coerce a suspend/Flow lambda to always yield a fixed value** — this is what "make a local flag permanently true" usually looks like in practice. See the worked example below.

### Worked example: permanently "not expired" without touching a shared helper

**Situation.** A local preference (`<key>_expires_at`) gates a promo popup. Writing a large value into the datastore works on the current device but is **runtime data**, so a fresh install loses it (see P11). The read path is a Flow built at construction time, so the getter cannot be patched meaningfully, and the generic `Long.valueOf` wrapper has 30+ callers (see P6).

**Target.** The dedicated map lambda, e.g. `feature/data/SomeStore$currentX$$inlined$map$1$2`:

```
.method public final emit(Ljava/lang/Object;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;
    iget-object v0, p0, L<same class>;->b:Lkw2;   # downstream collector
    const-wide v1, <big value>
    invoke-static {v1, v2}, Ljava/lang/Long;->valueOf(J)Ljava/lang/Long;
    move-result-object v1
    invoke-interface {v0, v1, p2}, Lkw2;->emit(Ljava/lang/Object;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;
    move-result-object v0
    return-object v0
.end method
```

Note the shape: the lambda class holds the downstream collector in a field (here `b:Lkw2;`). Always read that field name from the actual smali — do not assume.

This class has exactly one purpose, so patching it is safe.

## Technique 2: byte-level string patch

Only for **equal-length** replacements. Must preserve `string_ids` ordering.

```bash
python scripts/dex_strpatch.py <in.dex> <out.dex> "<old>" "<new>"
```

The script:
1. requires `len(new) == len(old)`,
2. requires exactly one occurrence,
3. looks up the entry's neighbours in `string_ids` and **rejects** the replacement unless `prev < new < next`,
4. recomputes `signature` (SHA-1 over bytes from offset 32) and `checksum` (adler32 over bytes from offset 12).

If a candidate is rejected, try another string that sorts inside the same interval. `/app/noadver` was rejected (`n > c` against neighbour `/app/configs/`); `/app/blocked` was accepted.

**Do not** use this technique to change behavior. Strings are renamed, not logic.

## Technique 3: smali tree editing (only when you must)

Use when the change cannot be expressed as a single-method rewrite (adding a field, restructuring control flow).

Tools: `scripts/smtool.py` (baksmali/smali with a bundled classpath) and `scripts/patch_smali.py` (method-body replacement by signature).

```bash
python scripts/smtool.py d <in.dex> <out_tree>
python scripts/patch_smali.py <tree> <patch.json> [--dry-run]
python scripts/smtool.py a <tree> <out.dex>
```

Then **must** verify (P3 will bite otherwise):

```bash
python scripts/dex_classdiff.py <original.dex> <rebuilt.dex>
```
Expect: same class count, `only_in_A=0`, `only_in_B=0`, `ACC_INTERFACE mismatch=0`.

If the class table is clean but the app crashes with `IncompatibleClassChangeError` / `VerifyError`, the round-trip damaged code items that table comparison cannot see. Fall back to technique 1.

Patch spec format for `patch_smali.py`:

```json
[
  {
    "file": "com/pkg/Helper.smali",
    "method": ".method public final showAd(Landroid/app/Activity;)V",
    "registers": 3,
    "body": ["return-void"],
    "note": "why this is safe"
  }
]
```

## Finding the call site

Reverse-lookup from a smali tree or a set of disassembled dex:

```bash
python scripts/find_refs.py <tree> 'Lcom/pkg/AdHelper;->showSplash(...)V'
```

Search strategies that work:
- Search the **string table** first (`scripts/dex_strings.py`). API paths, keys, and SDK class names are usually string literals, and they are unique.
- Search for the **SDK's entry class** (`Sdk.init`, `Sdk.show`). The app's wrapper is almost always the only caller.
- When the decompiler is confusing, trust the **byte offsets** — `grep` the dex for the literal and note where it sits relative to other strings of the same family.

## Order of operations for a real patch task

1. Identify every place the behavior is produced (`recon` + `find_refs`).
2. Pick the highest safe layer per the table above.
3. Write all edits for a given dex into **one** dexlib2 program.
4. Patch each dex **once**.
5. `dex_classdiff` every patched dex against the original → expect zero structural drift.
6. Repack, sign, install, launch, exercise, read logcat.
7. If anything is off, revert that dex to the original and re-verify the control build.
