# Runtime data — DataStore, SharedPreferences, SQLite, protobuf

Sometimes the cheapest fix is not code at all, but a value in app data. And sometimes that is exactly the wrong fix, because it does not survive a fresh install (`pitfalls.md` P11).


**Load this when:** the cheapest fix looks like a stored value rather than code -- DataStore, SharedPreferences, SQLite, a protobuf cache, a token. It gives how to edit each safely, and how to tell a value the app rewrites from one it keeps.

## Decide first: data or code?

| Question | Answer |
|---|---|
| Does the deliverable need to work after a clean install? | Then it must be **code**, not data |
| Are you iterating on your own device? | Data edits are a fast way to test a hypothesis **before** writing the patch |
| Is the value written by the app itself (a token, a cache, a counter)? | Data — and the server may re-assert it |

**Recommended workflow:** use a data edit to *prove the hypothesis* (cheap), then implement the same effect in code (durable), then verify with a clean install.

## Where app data lives

```
/data/data/<pkg>/                     (== /data/user/0/<pkg>)
├── files/
│   ├── datastore/*.preferences_pb    AndroidX DataStore (protobuf)
│   ├── mmkv/<name>                   MMKV (Tencent) — one file per named store
│   └── ...
├── shared_prefs/*.xml                SharedPreferences
├── databases/*.db                    SQLite (Room, etc.)
└── <sdk caches>/                     crash logs, download state, ad configs
```

Read with root:
```bash
adb shell "su -c 'ls -la /data/data/<pkg>/files/datastore/'"
adb shell "su -c 'xxd /data/data/<pkg>/files/datastore/<name>.preferences_pb | head -20'"
```

## AndroidX DataStore (protobuf)

Format:
```proto
PreferenceMap { map<string, Value> preferences = 1; }
Value {
  oneof value {
    bool boolean = 1; float float = 2; int32 integer = 3; int64 long = 4;
    string string = 5; StringSet string_set = 6; double double = 7; bytes bytes = 8;
  }
}
```

**Encoding an entry requires TWO tag levels:**
```
outer (map field 1, wire type 2) : 0A <len(inner)>
inner (one map entry)            : 0A <len(key)> <key>  12 <len(value)> <value>
value payload (e.g. int64)       : 20 <varint>        # field 4, wire type 0
value payload (e.g. int32)       : 18 <varint>        # field 3, wire type 0
value payload (e.g. bool)        : 08 <0x00|0x01>     # field 1, wire type 0
value payload (e.g. string)      : 2A <len> <utf8>    # field 5, wire type 2
```

Omitting the **outer** tag produces a file the app cannot deserialize, and the failure is usually a **stack-less crash** (`pitfalls.md` P8). Use `scripts/datastore_inject.py` rather than hand-rolling it.

Procedure:
1. `am force-stop <pkg>` (DataStore caches in memory and writes back)
2. Write the file (as root), preserving ownership — `cp -f` over the existing file keeps its owner
3. `restorecon` if SELinux is enforcing
4. Start the app and observe

Verify by reading the file back with `xxd` before launching.

## SharedPreferences (XML)

Simple XML. Edit with the app stopped. Types are explicit (`<boolean>`, `<int>`, `<long>`, `<string>`). Same ownership rules.

## MMKV (Tencent)

Common in apps whose SDK stack is Chinese-market. One file per named store under `files/mmkv/`,
with a `.crc` companion. It is **not** a database and **not** XML — it is a small custom binary
format:

```
offset 0   uint32   actual_size    size of the data region
offset 4   uint32   crc32          over the data region
offset 8   data region            repeated: varint key_len, key, varint val_len, value
```

Files are preallocated, so trailing zeroes are normal; `actual_size` is what matters.

Parsing is mechanical, and no library is needed:

```python
import struct

def parse(blob):
    size = struct.unpack_from('<I', blob, 0)[0]
    pos, end, out = 8, 8 + size, []

    def varint(p):
        v = s = 0
        while True:
            b = blob[p]; p += 1
            v |= (b & 0x7F) << s
            if not b & 0x80:
                return v, p
            s += 7

    while pos < end:
        klen, pos = varint(pos); key = blob[pos:pos + klen]; pos += klen
        vlen, pos = varint(pos); val = blob[pos:pos + vlen]; pos += vlen
        out.append((key, val))
    return out
```

Writing a change back means rebuilding the region and **recomputing both header fields**:

```python
import struct, zlib

body = new_region_bytes
blob = bytearray(capacity)                 # keep the original file length
struct.pack_into('<I', blob, 0, len(body))
struct.pack_into('<I', blob, 4, zlib.crc32(body) & 0xFFFFFFFF)
blob[8:8 + len(body)] = body
```

Cautions:

- **A wrong crc32 makes the library throw the whole store away.** The visible symptom is "my
  edit did nothing" or "the app reset every setting", never an error.
- **Values are raw bytes**, not always text. JSON is common; a serialized protobuf or a small
  encrypted payload is also common (`scripts/blob_decode.py` searches the framing).
- **The in-memory copy wins until the process restarts.** `am force-stop` before editing and
  re-launch after, or the running app overwrites your change on exit.
- **Do not delete the `.crc` companion.** Leave it in place when hand-editing the store; it is
  validated and regenerated by the library.

## SQLite

```bash
adb shell "su -c 'sqlite3 /data/data/<pkg>/databases/<db>.db \".tables\"'"
adb shell "su -c 'sqlite3 ... \"select * from <table> limit 5;\"'"
```
Useful for: auth sessions (tokens), user profile caches (often a raw JSON blob), and any server state the app persists. A JSON column often contains the exact server payload — the fastest way to learn field names.

## Ownership — the silent killer

The app runs as its own uid. A file written by root with the wrong owner is unreadable, and directory permissions are `drwx------`.

```bash
uid=$(adb shell "dumpsys package <pkg> | grep userId=" | tr -dc '0-9')
adb shell "su -c 'chown -R $uid:$uid /data/user/0/<pkg>'"
adb shell "su -c 'restorecon -R /data/user/0/<pkg>'"
```
Symptom of getting this wrong: crash in a database-init path right after launch, often `Cannot open database ... Directory ... doesn't exist`.

Note: after every reinstall the app's uid **increments**, so a restored data directory needs this again.

## Introducing a value that does not exist yet

If the key is absent, the app uses a default. Two options:

1. **Add the key** with the exact protobuf shape above.
2. **Confirm the default first** — sometimes removing a key already yields the behavior you want (e.g. clearing an expiry so it reads as "not set").

## Making the fix durable

If the effect must ship inside an APK, move it into code. Patterns, in order of preference:

- **Patch the read path** so the value is always the desired one. Find where the Flow/getter is built and make it emit a constant.
- **Patch the decision**, not the data: find the comparison that consumes the value and make it resolve the way you want.
- **Do not patch the generic encoder/boxer** used by the whole app (`pitfalls.md` P6).

Reference case: a promo popup was gated by `<key>_expires_at`. Writing a large value via DataStore suppressed it on the test device, but a fresh install lost it. The durable fix replaced the dedicated map-lambda that produces the value so it always yields a far-future timestamp — a single-purpose class, safe to patch, no effect on the shared serialization helpers.

## When the app rewrites your edit

A very common sequence: you change the value, relaunch, and the value is **back** — often byte for
byte identical to what it was before. That is not a failed write. It is the app re-establishing the
value from a source of truth you have not touched yet.

Two causes look identical and need different fixes:

| Cause | How to tell | Fix |
|---|---|---|
| The app **re-fetches from the server** and re-persists | take the app offline and relaunch: does your value survive? | lock the file, block the refresh request, or move the change into code |
| The app **rewrites the file on every start** from its own defaults | your value does not survive even with the network down | the value is not authoritative — patch the read path instead |

Do the offline test first. It costs one launch and separates the two cases.

### Making a data edit stick (in order of durability)

1. **Immutable file attribute** — the reliable, reversible way to stop a rewrite:
   ```bash
   su -c "chattr +i <path/to/prefs.xml>"
   su -c "lsattr <path/to/prefs.xml>"      # expect the 'i' flag, e.g. -----i-------
   # to undo:
   su -c "chattr -i <path/to/prefs.xml>"
   ```
   Verify with `lsattr`, not by assuming the command worked.

   **Why permissions do not achieve this.** Tightening the mode or changing the owner looks like the
   obvious move and does not work, because the app does not open-and-write the existing file — it
   **deletes the file and creates a new one**. The new file is created by the app, with the app's own
   mode and owner, so a restrictive `chmod` or a `chown root` is simply not inherited. The immutable
   attribute is enforced by the filesystem against the delete itself, which is why it holds.

2. **Keep the app offline** so the refresh source is unreachable. Effective for a test, and
   sometimes acceptable in use — but be explicit about it, because a fix that only works offline
   fails the "works under normal conditions" constraint. See the deliverable-drift section in
   `long-task-discipline.md` before presenting this as a result.

3. **Block the refresh request** at the runtime or network layer — durable while your instrumentation
   is running, and requires you to have identified the endpoint (`references/server-api.md`).

4. **Move the change into code** — patch the read path or the decision. This is the only form that
   ships inside an APK (`§Making the fix durable` above).

### Two cautions about locking

- **Verify the feature, not the value.** Blocking a write the app depends on can make it misbehave
  or fail loudly. After locking, exercise the feature you care about — "the file still has my value"
  is not the same as "the app still works".
- **A lock is device state; it does not travel with an APK.** If the recipe requires it, record it as
  an environment requirement, so nobody later mistakes it for something baked into the artifact.

## Encoded values: do not assume "encrypted"

Preference values that carry server configuration are frequently stored as a single opaque string
rather than readable XML. Before concluding the value is encrypted, check whether it is merely
**framed**: a common shape is `base64( rotate( deflate( json ) ) )`, where the cyclic rotation exists
precisely so a naive decode fails.

`scripts/blob_decode.py` searches the parameter space instead of guessing it — outer encoding
(base64 / base64url / hex), rotation offset, and compression type — and reports every combination
that yields a structured document, plus the exact parameters to re-encode your edited payload:

```bash
# pull the value straight out of a preferences XML and decode it
python scripts/blob_decode.py --prefs-xml prefs.xml --name <key>      # (see --help for exact name)

# after editing the decoded payload, rebuild the value with the winning parameters
python scripts/blob_decode.py --encode --file decoded.bin --outer base64 --inner raw --cut <N>
```

The rotation search is cheap — a few tens of thousands of candidates resolve in well under a second
— so there is no reason to guess. **Distinguish framing from real encryption before spending time
on a key:** a framed blob becomes structured the moment you remove the framing, whereas a keyed blob
stays random-looking. If it stays random, treat it as opaque and move to the code path that consumes
it.

## Cautions

- Editing data while the app is running is unreliable: in-memory caches win. Force-stop, edit, then launch.
- The server may overwrite your value on next sync — see *When the app rewrites your edit* above.
- Do not edit a token you do not own and expect it to be accepted; tokens are validated server-side (`references/server-api.md`).
- A restored data directory needs ownership fixed again after every reinstall, because the uid increments.
