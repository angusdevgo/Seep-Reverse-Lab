# Four bytes of dex, and a control build that still failed the old way

## Metadata
| Field | Value |
|---|---|
| Context | an equal-length dex patch against a public crackme (`UnCrackable-Level1`), taken all the way to an installed, launched build whose blocking dialog is gone |
| Cost | one full pipeline re-run after the repository changed mid-pass; one false verification caused by a reused remote filename |
| Outcome | the end-to-end chain is measured, with a zero-change control through the **same** pipeline — which is what makes the four bytes, rather than the pipeline, responsible |
| Evidence | `references/evidence-summary.md` §The capability matrix (the B1 sections); the benchmark matrix (`references/evidence-summary.md` §The capability matrix) row B1 |
| Related | `references/byte-level-patching.md`, `references/patch-audit.md`, `references/repack-and-sign.md`, `references/verification.md` (the control-build rule) |

## Assertions and grade
| # | Assertion | Grade | Evidence |
|---|---|---|---|
| 1 | The shipped dex's `signature` field is stale while its `checksum` is correct | observed | `checksum field 7fb7d9fa` / `adler32(d[12:]) 7fb7d9fa` matches, while `sha1(d[32:])` does **not** match the stored signature |
| 2 | The edit site is the first arm of a three-way root `OR`, and the *fall-through* is the "continue" side | observed | `0x9d0 39000e00 if-nez v0 -> 0x9ec` preceded by `invoke-static …a()Z` / `move-result`, and `0x9ec` is `const-string "Root detected!"` |
| 3 | Branch polarity was pinned by the following instruction, not by the method name | observed | `expect_next` required `invoke-static …b()` (the *next* root check) after the branch — `polarity: expect_next satisfied` |
| 4 | The patch owns exactly 4 bytes and the header fields own 24; nothing else in the file moved | observed | whole-file diff offsets `['0x8','0xa','0xb','0xc'…'0x1f', '0x9d0','0x9d2']`, and both header fields recomputed from the written file |
| 5 | The signature was computed **before** the checksum | observed | `zlib.adler32(d[12:])` and `hashlib.sha1(d[32:])` recomputed on the output reproduce both stored fields, which is only possible in that order |
| 6 | `repack.py` reported `resources.arsc STORED and 4-byte aligned (OK)` for control and patched alike | observed | the alignment gate output, identical for both builds |
| 7 | Both builds signed with v1+v2+v3 and the same certificate digest | observed | `apksigner verify --print-certs --verbose --min-sdk-version 21` |
| 8 | The installed artifact is the built artifact | observed | device `base.apk` sha256 equals the local sha256, for control (`e5a9f335…`) and patched (`ad6a51ce…`) |
| 9 | The control build — same pipeline, byte-identical dex — **still shows** the blocking dialog | observed | four window-focus samples, 2 s apart: `Window{… Root detected!}` for original and control, `Window{… <PKG>/…MainActivity}` for patched |
| 10 | The patched build reaches its own UI without a dialog | observed | the screenshots: control/greyed-out input with the modal over it, patched with the input live, caret present, `VERIFY` enabled |
| 11 | A second, independently built patched APK from the one-command pipeline produced the **same** sha256 as the manual route | observed | `ad6a51cef4699b73ff052d4e049ca9efd64e9570900d19509f0b7a7c20f87e56` |
| 12 | The app's functional check compares the user's input against a decrypted plaintext, and the 16-byte AES key is a `const-string` in the dex | observed | `a.b` hook output: key `8d12…73cc`, data decrypts to `I want to believe`, `[a.a] REAL input="" -> false` |
| 13 | The input field cannot be driven by `adb shell input text` on this ROM | observed | 7 of 17 characters survived and every space was dropped, across three independent quoting routes; `uiautomator dump` after each attempt is what distinguished "the app said Nope" from "the input never arrived" |
| 14 | The success branch was reached by forcing the boolean, not by typing the secret | observed, and labelled as such in the evidence file | `evidence/09_success_branch/*.png` shows the app's own `Success! …` dialog |

## Execution chain (including the dead ends)
1. **Read the branch structure before editing.** The edit target was chosen because its fall-through
   continues into the next root check — not because of its name. That is the difference between a
   patch that removes one arm of an `OR` and a patch that removes the check.
2. Dry run first: the tool prints the site with the instructions before and after, and the polarity
   evidence. Nothing was written until `polarity: expect_next satisfied`.
3. Applied, then proved with a byte-level diff of the whole file rather than the tool's own report:
   four payload bytes and the two header fields, and nothing else.
4. Repack. **Dead end:** the documented default signing route failed with
   `error: signer jar not found: uber-apk-signer.jar`, and its own hint — "any zipalign+apksigner
   based signer works here" — pointed at a code path that did not exist yet. The working route was
   the supported `--no-sign` seam plus explicit `zipalign` → `apksigner`, and the repository changed
   mid-pass (another writer landed an `apksigner` route), so the pass recorded **both** states and
   re-ran the one-command form, which produced byte-identical output. The lesson kept with it:
   *a "this tool cannot do X" finding on a shared worktree has an expiry date.*
5. Install through the **root** path (`pm install -r -d`), because this ROM intercepts the streaming
   install (see case 5's sibling record for the `[-99]` shape).
6. Verify, in the order that matters: hash the installed `base.apk` against the local build; `am
   start -W`; then window focus sampled four times; then **look at the screenshots**.
7. Build a zero-change control through the identical pipeline and repeat steps 5–6. It still fails
   the old way, which is what closes the attribution.

## Pits
| Pit | Cost | What it was mistaken for |
|---|---|---|
| Scanning the method for a plausible name instead of reading the branch structure | would have patched an `OR` arm that changes nothing | a successful patch |
| Relying on the tool's own "self-verify: checksum_ok=True signature_ok=True" without an independent diff | the stale-signature starting state could have hidden a wrong header order | a correct header |
| Reusing the `--tag` value as the remote filename across runs | the final verification showed the **control** build's dialog, from the control run's leftover remote path | a patch that did not work |
| `adb shell input text` on a field that silently drops characters | two attempts read as "wrong secret" | a wrong secret |
| Trusting a screenshot alone | it cannot tell which build is installed | a verified patch |

## Reusable pattern
- **Equal-length byte patches are the cheap route; choose the site by branch semantics.** Nothing
  moves, so no offset, `try` block or debug pointer can be invalidated, and the diff is auditable
  down to the byte.
- **A patch needs a same-pipeline control that fails the old way.** "It installs and runs" and "the
  behaviour changed" are different claims, and only the second one is the deliverable.
- **Hash the artifact on the device, at the moment you observe it.** This is the guard that caught
  the reused-tag mistake, and it is one command.
- **Look at the screen, and look at more than one sample.** A modal that appears and is gone between
  samples is invisible to a single capture.
- **Re-derive the header yourself once.** Recomputing both fields from the written bytes is what
  proves the *order*, and the tool's own success message cannot.

## Write back to the repository
- [ ] `references/repack-and-sign.md` — if the `signer jar not found` message and its apksigner
      route are not already reconciled, that is a documented contradiction worth closing.
- [ ] `references/verification.md` — the control-build rule is the load-bearing part of this case;
      add the "hash the installed APK before observing" step if it is only implicit there.
- [ ] `references/precedents/README.md` — indexed as case 4; the row's grade stays `observed` end to
      end.
