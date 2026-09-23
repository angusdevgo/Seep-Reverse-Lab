# dexlib2 method-level patcher

The **preferred** way to change app behavior. It replaces only a target method's
implementation and writes a new dex, leaving every other class, method, string and
reference untouched.

Why not whole-tree smali round-trip: `baksmali` → `smali` rebuilds misrepresent R8's
synthetic access bridges. The class table still looks perfect — same class count, zero
`ACC_INTERFACE` mismatches — but at runtime you get
`IncompatibleClassChangeError: Found interface X, but class was expected`.
See `../../references/pitfalls.md` P3.

## Build

Needs the same eight jars `smtool.py` uses:

```
smali-2.5.2.jar  antlr-runtime-3.5.2.jar  stringtemplate-3.2.1.jar
baksmali-2.5.2.jar  util-2.5.2.jar  jcommander-1.64.jar
guava-27.1-android.jar  dexlib2-2.5.2.jar
```

```bash
# point at your jars (or reuse ../smali_cp.txt)
CP=$(cat ../smali_cp.txt | grep -v '^#' | tr '\n' ';' | sed 's/;$//')

javac -encoding UTF-8 -cp "$CP" PatchMethod.java
```

**Always pass `-encoding UTF-8`** if the source has non-ASCII comments — `javac`
otherwise reads them with the platform default encoding and fails.

## Run

```bash
java -cp "$CP;." PatchMethod <in.dex> <out.dex> <descriptor> <methodName> <returnType>

# example: make Lx6;->d(...)V a no-op
java -cp "$CP;." PatchMethod classes7.dex out.dex 'Lx6;' d V
```

`PatchMethod` replaces the body with `return-void`. It scans **both** `directMethods`
and `virtualMethods` — a method you cannot find is often in the other list
(`static`/`private`/`<init>` are direct; everything else, including `public final`,
is virtual).

Use `PatchMethodExample.java` as the template for anything non-trivial (returning a
constant, emitting a fixed value from a Flow lambda, applying **several** edits to the
same dex in one pass).

## Rules that decide success

1. **One dex, one write pass.** Never chain two patchers over the same dex — the second
   serialization drops metadata and ART then refuses to start the process
   (`Failure starting process`, no Java stack). Combine all edits into one program.
2. **Preserve the register count.** `registers` must be `>=` the parameter register
   count. With `registers = N` and `k` parameters (counting `this` for non-static),
   `p0 = N - k`. For `(Ljava/lang/Object;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;`
   on an instance method, `k = 3`, so with `registers = 6` you get `p0=3, p1=4, p2=5`.
3. **`const-wide` needs the 64-bit instruction form** (`ImmutableInstruction51l`), not
   the 32-bit one.
4. **`invoke` operand order in `35c`** is `(opcode, registerCount, regC, regD, regE, regF, regG, ref)`.
   `invoke-static {v1, v2}, ...` → `registerCount=2, regC=1, regD=2`.
5. **End every body with a return of the correct type.**
6. **Check the blast radius first** — `../find_refs.py`. A generic helper with dozens of
   callers is not your patch point (`../../references/pitfalls.md` P6).

## Verify

```bash
python ../dex_classdiff.py <original.dex> <patched.dex>
python ../smtool.py d <patched.dex> <tmp_tree>     # confirm it parses
# then read the target method in tmp_tree to confirm it says what you intended
```

Expect `only_in_A=0`, `only_in_B=0`, `ACC_INTERFACE mismatch: 0`. Then install and
launch — table checks cannot see code-item damage, so runtime verification is
mandatory (`../../references/verification.md`).
