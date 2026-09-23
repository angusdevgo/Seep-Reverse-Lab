# Desensitization and leak scans — what must leave, and what must stay

A skill repository is published, and the material feeding it is real work: device transcripts,
packet captures, `ps` listings, log excerpts, an hour of shell history. Target identity leaks
into that material one line at a time — a bundle id in the middle of a `pm path` output, a
device serial echoed before a `dumpsys`, an SDK key pasted while debugging a download — and
**no structural check can see it.** `check_repo.py` validates layout, `check_refs.py` validates
anchors; both pass on a file that names a live app and a real phone.

The failure this file prevents is two-sided, and the second side is the one that gets
forgotten:

- **Under-redaction**: a published repository carries a target's identity, a device serial, or
  a credential, and nobody notices until someone greps for it a year later. This is what
  happened here once, by hand, after a pass had already been committed.
- **Over-redaction**: the same pass strips the *reusable* material along with it — the tool
  names, the hardening-product names, the public crackme names, the protocol field names — and
  the document stops being able to teach anything. A repository that has been scrubbed into
  uselessness has failed at the same job from the other side.

A rule that only handles the first side produces "a document about nothing". A rule that only
handles the second produces a leak. Both get fixed by the same artifact: an explicit list of
what is *exempt*, in code, that can be read and argued with.


**Load this when:** you are about to publish anything derived from real work -- an evidence file, a transcript, a README -- or a leak scan reports a hit. It gives the must-leave/must-stay split and the scanner's exit semantics.

## Strength labels

- **observed** — a command was run here and its output is quoted in the text or recorded in
  the evidence record condensed in `references/evidence-summary.md` §Where the full record lives.
- **inferred** — follows from an observed fact or from documented mechanism; the step itself
  was not executed.
- **unverified** — assumed, or reported elsewhere, and not reproduced in this repository.

Claim strength in this file means *how well the statement about desensitization was measured*,
not how confident the writing sounds.

## The two rules, stated so they can be argued with

**1. Redact what identifies the target; keep everything that identifies the technique.** A
bundle id, a device serial, a host user path, an appkey, a live token, a non-loopback endpoint
are identity. A tool name, a library name, a function name, a protocol field name, a CVE id, a
hardening product name, a public crackme name and its URL are *technique* — they are how the
document transfers skill, and they are exactly what a naive redaction pass deletes first.

The test that separates them: **would removing this string make the sentence less able to
teach?** `frida`, `apktool`, `libjiagu`, `UnCrackable-Level1`, `com.stub.StubApp`,
`RegisterNatives`, `proto3` all fail the test — removing them costs knowledge and protects
nothing, because they name a product, a tool or a public fixture. `<PKG>`, `<DEVICE>`,
`<APPKEY>` pass — they carry the sentence's structure and none of its identity. And
`com.<redacted>.app` also passes the test, which is why a scanner must *report* the reverse
domain shape and let a human see what it is; it cannot decide.

**2. A finding is reported with limited context, not a line number.** A report that says
`foo.md:412` makes the fixer reopen the file, read around the line, and decide what to delete —
per finding. A report that quotes ~48 characters either side means the decision is made from
the report itself. This is the same argument `verification.md` §Reporting makes for logs: an
artifact that does not contain the decisive information sends its reader back to the source.

## What must be kept — the do-not-anonymize list

Every entry here has been observed in this repository's own documents, and every one of them
is a wrong answer from a shape-only scanner. The list is materialized in
`scripts/scan_leaks.py` as `BENIGN_PACKAGE_PREFIXES`, `PUBLIC_TARGET_PREFIXES`,
`BENIGN_IP_PREFIXES` and the `CODE_IDENTIFIER_HINTS` table, so it can be extended with a
one-line edit and audited with `--show-exempt`.

| Category | Examples | Why it is exempt |
|---|---|---|
| Tool and library names | `frida`, `apktool`, `jadx`, `libart.so`, `libfoo.so` | naming a tool is the content; the name is public and identical for every reader |
| Function and symbol names | `RegisterNatives`, `findExportByName`, `pthread_mutex_lock`, `JNI_OnLoad` | API vocabulary, not identity — and a large fraction of the reverse-engineering technique is exactly these names |
| DEX/ELF constant identifiers | `findExportByName`, `ImmutableDexFile`, `installPackageLI`, `LoadPackageParam` | 16-character camelCase runs that a serial-shaped regex matches; they are code constants |
| Protocol field names | `proto3`, `varint`, `packed repeated`, `length-delimited` | wire-format vocabulary |
| CVE identifiers | `CVE-2024-31317`, `CVE-2021-44228` | public advisory ids; redacting them destroys the reference |
| Hardening product names | `com.stub.StubApp`, `libjiagu.so`, `libDexHelper.so`, `com.secneo` | a *product* signature. It is what lets a reader recognise a shell, and it names no target |
| Public crackme / benchmark targets | `UnCrackable-Level1.apk`, `sg.vantagepoint.uncrackable3`, MASTG and its URLs | deliberately published fixtures; their package names are part of the published exercise |
| Platform and SDK packages | `com.android.settings`, `com.google.android.gms.ads`, `com.qq.e.ads.PortraitADActivity`, `androidx.work.WorkManager` | inventory. "Which SDK does this app carry" is a finding; the SDK's own name is not a secret |
| This repository's own fixtures | `com.example.*`, `probe.synthetic.*`, a probe module's package | synthetic by construction |
| Placeholders | `<PKG>`, `<DEVICE>`, `<serial>`, `<hash>`, `<work>`, `<user>`, `C:\Users\<user>\...` | the redaction mechanism itself; a scanner that reports these is unusable |
| Loopback / unspecified / emulator addresses | `127.0.0.1:27042`, `0.0.0.0:8080`, `10.0.2.2:8080`, `169.254.169.254` (as a documented endpoint) | the frida and ADB idioms are these addresses; they identify nothing |

**Deliberately *not* exempt, and observed as a finding here**: the RFC 5737 documentation
ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`). They are the correct way to write
a synthetic address, so a hit there is a signal rather than noise. Suppressing the range outright
would also hide the case where someone pastes a real address that happens to look synthetic.

This repository pays for that decision with the *only* findings it produces, and the price is
recorded rather than argued away: **four `endpoint/weak` hits and nothing else**, measured on the
tracked surface with file count 129. Three of the four are the three blocks named in the sentence
above — this file stating the decision is itself the hit — and the fourth is
`scripts/tls_check.py`'s own usage example, a benign context the report makes obvious in one line.
Every other category is at zero. That ratio is why the gate's pass condition lives in
`--fail-on` and not in an exemption table: the documentation of the decision *is* the residue, so
a gate that failed on it would be failing on its own rationale. The transcript is in
`references/evidence-summary.md` §The capability matrix.

**What is a leak here, in contrast** — the shapes worth reporting: `package="…"` in a manifest
line, a bundle id after `pm path` / `pidof` / `ps -A` / `component=`, a 16-character
`[A-Z0-9]` run standing alone or beside a device word, `github_pat_…`/`ghp_…`, an inline
`APPKEY`/`appSecretKey`/`SECRET_KEY` assignment with a literal value, a non-loopback `IP:port`,
and `/home/<name>/`, `/Users/<name>/`, `C:\Users\<name>\`.

## What a scan can and cannot decide

Decide in code: whether *this shape* is present, and whether a known-benign pattern explains
it. Never decide in code: whether the surrounding document is identity-bearing.

Three consequences, each observed by writing the scanner for this repository:

- **A range of four digits separated by dots is an IP address only if nothing nearby says
  "version".** `JDK 17.0.4.1`, `build-tools 34.0.0` and `frida 16.7.19` are the shapes the first
  version of the scanner reported twenty times across the evidence record condensed in `references/evidence-summary.md` §Where the full record lives. Context
  (`jdk`, `python`, `frida`, … immediately before the match) separates them.
- **A 16-character uppercase token is a device serial only if it carries a letter.** Stack
  addresses from a tombstone (`0000000040001000`) and hex protocol fixtures
  (`0807060504030201`) are all-digit and were reported until that rule was added.
- **A reverse-domain string preceded by `args.` is a property lookup.** `args.package.split(".")`
  in a script — observed in `scripts/spawn_patch_detach.py` — is not a bundle id, and the
  exemption needs the *line*, which is why the exemption function takes it.

Each of those is a **false positive that a reader would have had to investigate**. Three of them
were found by running the scanner against this repository, not by reasoning about it — which is
the argument for making the scan a gate rather than a document.

## The scanner, and where it belongs in the pipeline

`scripts/scan_leaks.py` — standard library only, `--root` explicit or defaulting to its own
repository, categories `package` / `device` / `token` / `appkey` / `endpoint` / `path`, text and
JSON output, and a fixed exit-code contract:

| Exit | Token | Meaning | What a script does |
|---|---|---|---|
| 0 | `RESULT=clean` | nothing outside the exemption list | continue |
| 0 | `RESULT=leaks_found_strong_only` | findings exist, but every one of them is `weak` (an address from the documented range) | continue, and read the report — it is the publish-time checklist |
| 1 | `RESULT=leaks_found` | at least one `strong`/`certain` finding, or any finding under `--fail-on any` | fail the job and print the report |
| 2 | `RESULT=error` | bad usage, unreadable root, or a read error with no findings | fail the job as an infrastructure fault, not a content fault |

The token is the machine-readable line; the exit code is the interface. Keeping them separate
matters because a wrapper that only greps stdout cannot distinguish "clean" from "the scanner
never ran", and a wrapper that only checks `$?` cannot explain itself in a log.

Which findings fail the gate is chosen by `--fail-on`, and the two settings are two different
questions:

- `--fail-on strong` (default) — only `strong`/`certain` findings fail. This is the maintenance
  habit's setting, and it exists because of the RFC 5737 decision above: if the documented ranges
  are reported on purpose, this repository is never `clean`, and a gate that is red on its own
  rationale is a gate people learn to disable.
- `--fail-on any` — every finding fails, `weak` ones included. This is the publish-time setting,
  and the one to run against the file you are about to publish rather than the tree you are
  working in.

Neither setting changes what is *reported*: weak findings are printed under both, and only the
exit code differs. The strict pass is therefore a decision recorded in a command, not a surprise.

Placement, and the reasoning is about *when* the wrong answer is cheap:

- **Not in the pre-commit hook alone.** A commit-time gate is the cheapest place to catch a
  leak, but this repository's evidence files are written by long passes that commit once at the
  end; a hook would fire on a tree nobody has finished writing.
- **In the maintenance gate, next to the other two checkers.** The habit that already exists is
  `python check_repo.py && python check_refs.py` before a commit; a third line costs nothing and
  runs at the moment the material is about to become permanent. Its exit 1 is a *content*
  finding to read, not an error to retry — unlike the two checkers, whose failures are
  mechanical.
- **Before publishing an evidence file**, once, by hand, with `--show-exempt`. The exemption
  audit is where the interesting mistakes are: a value suppressed for the wrong reason looks
  exactly like a value that was never there.
- **On the report itself, after it is written and before it is published.** A report that quotes
  the hits in order to be concrete is a *copy* of the leak, in a file that is tracked and read.
  This is not hypothetical here: the first version of the desensitization extension record did
  exactly that, and the scanner flagged its own evidence file on the next run. Run the scan on
  the artifact you are about to ship, which for an evidence file means the file itself.
- **In CI, on the published tree only.** A scanner run over a git-ignored work area will report
  the work area — which is where the target identity legitimately lives — and a gate that cries
  wolf on every run is a gate that gets disabled. `tools/` is excluded by default for exactly
  this reason; a caller who points `--root` at it means it, and gets the findings.

**What the scan does not replace.** It cannot see identity that is *described* rather than
*quoted* ("a mid-size Flutter app with a 360 shell"), and it cannot see a value that has been
partially masked on purpose. Neither is a defect to fix by adding patterns: the first is why
this repository's evidence files open with a statement that target identity is absent, and the
second is a judgement call a human makes once and writes down.

## Failure modes

| Symptom | Mechanism | What to do |
|---|---|---|
| The scanner reports a hundred hits, none of them a leak | shape-only rules against a document full of legitimate identifiers (versions, hashes, symbol names) | Do not widen the exemption list one hit at a time. Run `--show-exempt`, group the reasons, and fix the *rule* — a context-free regex is the bug |
| The scanner reports nothing and you believe it | a root that excluded the directory the leak was in; a text file with an extension the walker skips; a value inside a fenced block the reader never scrolled to | Read the header line — it prints the file count and the root. Then point `--root` at one directory and confirm the count is plausible |
| A real leak was suppressed | an exemption matched a substring (`<pkg>` inside something else), or the benign-prefix list is too broad (`com.`-prefixed platform list catching a target that starts with the same two segments) | `--show-exempt` prints the *reason* per suppressed hit. An empty or vague reason is the defect |
| Same hit reported twice on one line | two rules whose scopes overlap (`SECRET_KEY=` is both a token and an appkey) | Expected, and left in deliberately: two independent rules naming one value is corroboration. Exact duplicates (same rule, same value, same line) are collapsed |
| The gate is green in CI and the leak is in the tarball | CI scans the tree; the artifact was built from a work area, or from a branch that was never scanned | Scan the directory the artifact is built from, with the same exclusions the build uses |
| A `<PKG>`-style placeholder is reported | the placeholder uses a different bracket, or no brackets at all | Add the token to `PLACEHOLDER_TOKENS`. This is the one exemption class that should grow freely — placeholders cannot leak |
| The published report contains the leak it was written about | the report quotes each hit value in order to be concrete, and the report is the published artifact — a report is a copy of what it found | Never quote a hit value in a published document. Keep rule, category, strength, position and count, and describe the value by shape (`<reverse-domain>.<n>`, `16×[A-Z0-9]`, `24×[0-9a-f]`) or with a placeholder. Scan the file you are about to publish, not the file you started from |

## The entry-point surface

A published skill is not only read by an agent; its **entry files are read as instructions**.
`SKILL.md`, a `README.md`, and the front-matter of any reference are the parts a host process
loads *before* it decides anything, and a repository assembled from third-party material — a
borrowed reference file, a contributed script — carries whatever those files say. This
repository's convention, observed in its own history: content reproduced from elsewhere is
summarised as prose with the source named, never quoted verbatim in a way that would land in an
instruction position, and a contributed file is read before it is linked.

The practical consequence for redaction is the same as for the rest of this file: **the
redaction must not be reversible by asking the file.** A placeholder that is defined next to
its own value, a "sample transcript" that still carries the serial in a comment, or a finding
report pasted into a document that later becomes an entry point all reintroduce the identity
that a scanner would have caught — because the scanner ran before the report was written. Run
the scan on the file you are about to publish, not on the file you started from.

## Cross-references

- `references/long-task-discipline.md` §Keep a live record, not a log — the record is written
  during the work, so it is where identity lands first, and the file most likely to be published
  by accident.
- `references/verification.md` §Reporting — the evidence/report split this file mirrors: what
  ships is neutral and mechanical, what identifies the target stays in the analysis.
- `references/precedents/README.md` — the case library; its "write back to the repository"
  checklist is where a desensitization finding becomes an index line.
- `references/third-party-builds.md` — the same do-not-anonymize reasoning applied to a sample
  you did not produce, where the identity is someone else's.
