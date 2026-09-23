# Protocol reverse engineering

**Load this when the app's traffic is not readable by the usual means**: the body is protobuf with no
schema, the transport is gRPC, the connection is QUIC rather than TCP, or the client refuses to trust
your proxy because it validates the certificate inside a native library.

Everything in this file assumes you have already decided the traffic matters and that a proxy is
allowed to see it. If a *feature-scoped* TLS failure has appeared while the rest of the app works,
that is a different problem with its own file: read `tls-and-cert.md` first — it owns the trust-chain
attribution and the permissive-defaults template, and this file deliberately does not repeat them.

**Claim strength.** `measured` = an exact command and output exist in
`references/evidence-summary.md` §The capability matrix. `inferred` = documented behaviour or a step that
follows directly from a measured one. `unverified` = reported by others, not reproduced here. The
wire-format section is `measured` on a self-built fixture; every tool named below is `unverified`
unless stated otherwise.

## 1. Protobuf on the wire (measured)

Protobuf has no field names on the wire and no header. A payload is a flat sequence of
`tag, value` pairs, and a nested message is just a value of type "bytes whose content is another
sequence". That is the whole format; the schema supplies meaning and nothing else.

| Element | Encoding |
|---|---|
| Varint | base-128, least-significant group first, high bit set on every byte but the last |
| Tag | `(field_number << 3) \| wire_type`, itself a varint |
| Wire type 0 | varint value (int32/int64/uint/bool/enum) |
| Wire type 1 | fixed 8 bytes (fixed64/sfixed64/double) |
| Wire type 2 | length-delimited: length varint, then that many bytes (string, bytes, nested message, packed repeated) |
| Wire type 5 | fixed 4 bytes (fixed32/sfixed32/float) |
| Wire types 3/4 | group start/end, legacy; treat as unsupported when walking a modern payload |

A host-side check of the rules, including the canonical `150 -> 96 01`, was run independently of the
shipped decoder — `references/evidence-summary.md` §The capability matrix records that cross-check against
the official runtime. Measured output on the fixture built for it:

```
message (29 B): 089601120774657374696e671a0508011201782206038e029ea7052800
  field 1   varint            150
  field 2   len-delimited(7)  'testing'
  field 3   len-delimited(5)  nested message:
    field 1   varint            1
    field 2   len-delimited(1)  'x'
  field 4   len-delimited(6)  hex '038e029ea705'
  field 5   varint            0
rebuild from the walked rows equals original: True
```

Three consequences that decide how you interpret any decoded body:

1. **Field numbers are local to their message.** In the walk above, field 3 of the outer message is a
   nested message whose own field 1 exists independently. Nothing on the wire says which message a
   field number belongs to; only a schema does.
2. **A packed repeated field is invisible without a schema.** Field 4 above is three varints
   (`3, 270, 86942`) packed into one length-delimited value. A schema-free decode can only report it
   as opaque bytes — the length is known, the element boundaries are not.
3. **A decoded `0` and a field that was never set are two different questions.** An implicit
   (no-presence) proto3 field whose value is the default writes **nothing at all**, so `field = 0`
   and "never touched" produce identical bytes; a field **with** presence (`proto2 optional`,
   `proto3 optional`) set to `0` does put its tag and a zero byte on the wire. Both halves were
   measured against the official runtime; a schema-free decoder can only flag the case, never
   resolve it. So a decoded `0` was emitted on purpose by some writer, and a field *missing* from a
   decode is not evidence that 0 was the value in use.

### Decoding without a schema

- `protoc --decode_raw < body.bin` — the reference implementation's own raw decode; prints field
  numbers and values in exactly the shape above. Note it prints strings and nested messages without
  distinguishing them, which is why the fallback order matters: try a nested walk first, then
  printable UTF-8, then hex.
- `protobuf-inspector` and `blackboxprotobuf` are the pip-installable equivalents, and both add
  heuristics: guessing whether a length-delimited value is a string or a submessage, and (for
  `blackboxprotobuf`) inferring a candidate type set per field across many samples. Useful when you
  have traffic but no `protoc`; still unverified here.
- Decode **many samples of the same message**, not one. The number of distinct field numbers in a
  large sample set is what tells you which fields are optional, which repeat, and which are enums
  whose value set you can then enumerate.
- Anything the app stores locally is a sample source that needs no proxy at all: an OkHttp disk cache
  (the `journal` file plus its entries), a DataStore file, or a Room blob column. `runtime-data.md`
  covers reading these, and `datastore_inject.py` can re-encode an edited DataStore value once you
  know the message.

### The decoder that ships here (measured)

`scripts/protobuf_decode_raw.py` walks a payload with no schema and prints a tree. Input is a hex
string, a binary file, or stdin (hex text and raw bytes are told apart automatically); `0x` prefixes,
spaces, commas, newlines and `\xNN` escapes are all accepted, and `|` splits independent frames.
`--json` emits the same tree as data, `--max-depth` bounds the nesting, and `--reencode` writes a
decoded (possibly hand-edited) tree back to bytes and can diff the result against the original.

```
$ python skills/apk-reverse/scripts/protobuf_decode_raw.py --hex "08 96 01 12 07 74657374696e67"
frame 0  bytes 0..12  (12 B)  status=end_of_buffer
  f1  varint  150
  f2  len-delimited(7)  view=utf8_string
      candidate utf8_string      0.50  valid UTF-8 with no control characters
      candidate packed_varint    0.50  the payload is exactly a sequence of 7 varint(s) ...
      candidate bytes            0.20  opaque bytes: always consistent with the payload ...
      tie: packed_varint and utf8_string are equally consistent with these bytes ...
      string: 'testing'
```

The point of the tool is the candidate list. Fed a nested message that `google.protobuf` 6.33.6
itself produced (inner payload `0801120178`), it answers:

```
nested_message 0.50 | packed_varint 0.50 | utf8_string 0.35 | bytes 0.20
tie: nested_message and packed_varint are equally consistent ... the view is a display default
```

Both readings really are legal protobuf for those six bytes, and no heuristic closes the gap. The
confidence numbers are a documented ordering, not probabilities, and the `view` exists only so the
tree can be expanded and re-encoded -- it is not a claim about what the field is.

**Round trip, which is the strongest evidence available without a schema.** Decode, re-encode, and
compare bytes: the message serialized by the official runtime re-encodes byte-identically to
`SerializeToString()`; a real AndroidX DataStore file (81 B, written by `scripts/datastore_inject.py`)
round-trips byte-identically; and editing one value in the JSON tree and re-encoding produced a file
that the *other* tool read back as the new value. Two of the built-in fixture families are exceptions
by design and are reported as such rather than hidden: a non-canonical varint re-encodes to the
minimal form, and a `--split varint-length` run compares frame bodies only, since the length prefixes
are framing and not message data.

**What a schema-free decode cannot conclude -- write none of these down:**

- that a length-delimited field *is* a string, a submessage or a packed array, rather than that it
  could be any of them;
- the element boundaries of a packed array, or its element type;
- that a field's value was 0 because it is absent from the decode, or that a sender "set" a field
  because a 0 appears (see the two traps above);
- which message a field number belongs to, or that the same field number in two payloads means the
  same thing;
- that a payload which parses cleanly is a real message at all -- §6 has that failure mode, and the
  fixes are a second sample and a round trip, not a longer look at the first one.

The measured record for this tool -- every command, both input forms, the round trip, and the
framing mistake it does *not* protect you from -- is in
`references/evidence-summary.md` §The capability matrix.

## 2. Recovering the schema from the APK

### What generated protobuf code looks like

| Marker in the decompiled output | What it tells you |
|---|---|
| `extends GeneratedMessageLite` / `GeneratedMessageV3` | protobuf class; `Lite` means the reflection/schema runtime, not the descriptor-based one |
| `static final int FIELD_NUMBER = 3;` (or `int <name>_ = 3`) | the field number, usually right next to the field's getter |
| `switch (tag >>> 3)` with `case` constants | the parse loop's field dispatch — each `case` is a field number, in declaration order |
| `input.readInt32()`, `readInt64()`, `readBool()`, `readStringRequireUtf8()`, `readBytes()`, `readMessage(...)`, `readEnum()` | the field's wire type and semantic type, read *after* the tag |
| `input.readTag()` returning 0 as the loop exit | the standard `parsePartialFrom` skeleton; the loop body is where all field knowledge lives |
| `writeTo(CodedOutputStream)` / `getSerializedSize()` / `dynamicMethod(...)` | the class really is a generated message, not a hand-written DTO |
| `newMessageInfo(instance, "<escaped string>", ...)` | protobuf-lite's compact schema blob (see below) |

The generator keeps those framework calls even after R8, so an obfuscated app usually still carries
readable protobuf structure: class and field *names* are gone, field *numbers* and wire types are
not.

### Two routes to a `.proto`

**Route A — read the field table out of the bytecode (inferred).** Decompile the class, walk
`parsePartialFrom`, and record `case <n>` → the `read*` call that follows. Field name unknown? Name
it `field_<n>`; a valid `.proto` does not need the original identifiers, and the app's own getter
names often survive anyway. Then verify immediately against captured bytes with
`protoc --decode=<message> <schema.proto>`: a decode that produces a coherent structure for **every**
sample is the proof that your field table is right, and it costs seconds. A field that decodes into
nonsense means a wrong wire type, not a wrong field number — check the `read*` call before moving on.

**Route B — read protobuf-lite's own schema blob (inferred).** protobuf-java-lite 3.x embeds a
compact schema string (`rawMessageInfo`) per message class, consumed by `MessageSchema` at runtime.
Recovering it means locating that blob and feeding it to a matching runtime build. It is a strictly
larger win when it works — it carries field numbers, types, and labels in one place — and it is
version-sensitive, so treat Route A as the default and Route B as the acceleration. `unverified`
here: no target in this repository was analysed this way.

**Tooling that automates this (unverified):** `pbtk`/`protodump`-style scanners walk dex/JAR inputs
looking for the generated-code shape above and emit `.proto` files, and a protobuf-aware decompiler
plugin can do the same from a loaded APK. Use them to produce a first draft, then verify it with
`protoc --decode` against real captured bytes — that verification is the step that turns a guess into
a schema, and it is the step worth spending time on.

## 3. gRPC

gRPC is HTTP/2 with a message framing convention, so the first decision is whether you can see
HTTP/2 at all.

- **Recognise it.** A request carries `:method: POST`, `content-type: application/grpc[+proto]` (also
  `+json`, `+thrift`), and `:path: /<package>.<Service>/<Method>` — that path shape is the reliable
  fingerprint; the package in it usually matches a package name visible in the APK, which is how you
  connect traffic to a client class.
- **Message framing.** Each message is: one compression-flag byte, then a 4-byte **big-endian**
  length, then that many bytes of (possibly compressed) protobuf. Several messages can share one
  DATA frame and one message can span frames, so reassemble by length, not by frame. The call's
  outcome is in **trailers** (`grpc-status`, `grpc-message`), which many proxies display separately
  from the body — a `200` with no body and a nonzero `grpc-status` is a normal gRPC error.
- **Read it after capture.** Extract the reassembled message bytes and hand them to
  `protoc --decode_raw` or your recovered schema. `grpcurl -plaintext -protoset file.protoset`
  replays against an endpoint once you have a schema, which is also the fastest way to confirm that
  a recovered `.proto` has the right shape.
- **Capture it.** A transparent TCP proxy sees HTTP/2 fine; a tool that only understands HTTP/1.1 may
  show the tunnel without the frames, which looks like "the app is not making requests". Interception
  tooling for this comes in two shapes: a proxy add-on that understands the gRPC framing and prints
  messages (`grpc-dump` and similar mitmproxy add-ons, or a gRPC-Web decoder when the client is a
  browser-style stack), and a command-line client (`grpcurl`) for replay against a live endpoint. If
  the app uses TLS (gRPC-Java does by default), the certificate question comes first — see
  `tls-and-cert.md`, and the native-material trust chain below.

## 4. QUIC / HTTP/3

The failure to expect: a working HTTP proxy, a working CA, and **an empty capture**.

- **Why.** An HTTP proxy is a TCP endpoint, and a client reaches it with `CONNECT`. QUIC is a
  UDP-based transport with TLS 1.3 built into the handshake; there is no TCP connection for a
  `CONNECT` to carry and no separate TLS layer for a proxy to terminate.
- **Recognise it before debugging anything else.** `Alt-Svc: h3=":443"` in an earlier HTTP response
  announced the upgrade; on the wire you see UDP traffic to port 443 whose first packets are QUIC
  Initials (long header, version field, and a TLS ClientHello inside), and the client's ALPN is `h3`.
  Check for UDP activity when a TCP proxy stays idle while the app plainly works.
- **Options, in order of how little they change:**
  1. **Force a fallback to TCP.** Block or blackhole UDP 443 for the device. A client that cannot
     reach an origin over QUIC falls back to TCP/HTTP2 if the server also offers it, and then your
     existing proxy works unchanged. This is the cheapest option and the one to try first, but it is
     a **network-condition change**: state it in the report, because "the app failed to load over
     QUIC" and "the app failed" look identical in a screenshot.
  2. **Decrypt with keys, not with a proxy.** TLS 1.3 key logging (`SSLKEYLOGFILE`-style) works for
     QUIC exactly as it does for TLS-over-TCP, and a packet capture plus the key log can be
     decrypted in Wireshark. It requires the client to support a key-log callback — Chromium-based
     stacks and BoringSSL generally do, Java/OkHttp-based stacks generally do not — so this is a
     per-client property, not a general solution.
  3. **Turn HTTP/3 off in the client** by hooking whatever enables it (a library version check, a
     remote-config flag, or a build-time constant). This is a client-side patch and therefore
     belongs to the repack decision, not to the capture step.
- Everything in this section is `inferred`/`unverified` here: no HTTP/3 target was exercised in this
  repository. Treat the ordering as a plan whose first step (block UDP 443) needs no tool support to
  test.

## 5. SSL pinning that lives inside a native library

Three different mechanisms are routinely called "pinning", and only the last one survives a system
certificate module.

| Mechanism | Where it runs | What defeats it |
|---|---|---|
| OkHttp `CertificatePinner` (or a custom `TrustManager`) in Java/Kotlin | app's own client | Client-level, **not** the system path: `tls-and-cert.md` §Step 4 and §"If OkHttp is the failing path" own this case — do not apply the permissive-defaults template to it |
| System trust decisions via `HttpsURLConnection` / platform stack | platform | System store policy — see `tls-and-cert.md` §Step 5 |
| Verification performed by a **library the app ships**, e.g. a Flutter app's own BoringSSL, or a bundled `libcurl`/`mbedtls` | `libflutter.so`, `libapp.so`, another `.so` | Only an in-memory change to that library's verification path (below), because the library does not consult the platform trust manager you can influence from Java |

**Flutter, specifically.** A Flutter app's `dart:io` HTTP client runs on the engine's BoringSSL
inside `libflutter.so`; the app's own Dart code can additionally supply a custom trusted-certificate
context or a bad-certificate callback. Two consequences that decide which direction to work in:

- If the app is **not** pinning and simply fails to trust your CA, getting your CA into the **system**
  store is the normal fix. `MoveCertificate`-style Magisk modules exist precisely because Android 7+
  ignores user-store CAs for app traffic; moving the CA into the system store is a **device change**,
  not an artifact, and it must be labelled as a fallback rather than the deliverable. Its boundary is
  exactly this: it changes what the platform trust store contains, so it can only help a client that
  reads that store.
- If the app **is** pinning, or supplies its own verification context, the system store is irrelevant
  and the change has to land on the library's verification function.

**Locating the verifier inside `libflutter.so` (unverified — reported method).** The published
approach in
[universal-flutter-ssl-pinning](https://github.com/vichhka-git/universal-flutter-ssl-pinning)
(`github.com/vichhka-git/universal-flutter-ssl-pinning`) automates the anchor search with PyGhidra:

1. load `libflutter.so` headlessly in Ghidra and scan its defined strings for `ssl_client`;
2. resolve cross-references from that string to the **containing functions**;
3. decompile each candidate to count its parameters;
4. take the **3-parameter** function — that is BoringSSL's
   `ssl_crypto_x509_session_verify_cert_chain`, the certificate-chain verification entry point;
5. emit the discovered RVA into two ready-to-run artifacts: a Frida script that attaches to that
   address and replaces the return value with `1` (success), and a Renef script that patches the
   function entry with the ARM64 sequence `MOV X0, #1 ; RET`.

The repository reports it working on Google Flutter arm64-v8a and Shorebird-patched builds with
Frida 16.x/17.x, and notes the RVA is identical across build types for the same engine version. The
same project also ships an HTTP monitor that auto-locates BoringSSL's `SSL_write`/`SSL_read` in
`libflutter.so` and prints reassembled, de-chunked plaintext — which is the route to take when the
traffic cannot be proxied at all, because it never needs a certificate the app will accept.

**Two things to verify before trusting that recipe on your target.** First, the string anchor is a
build artifact: a stripped or repacked engine can lose `ssl_client` while keeping the function, in
which case fall back to the structural search — find the `X509_verify_cert`-shaped call sequence in
the handshake code, or identify the function called with the handshake structure during
`certificate_verify`. Second, the failure mode of a wrong anchor is a **silent** success: replacing a
return value in a function that merely *looks* like the verifier makes the certificate check pass
in a process that then fails somewhere else, which is easy to misread as "the app detected my hook".
Always confirm the hook fires on a connection that would otherwise fail, and confirm it is
`SSL_VERIFY`-shaped semantics (the same value the library itself uses for success), rather than
assuming `1` is right.

**When the string anchor is gone (the `session_creator` route).** A second family of anchors does not
depend on the `ssl_client` literal at all: instead of finding the verifier through a string it
references, find it through the call chain that reaches it. BoringSSL's handshake creates the session
and then verifies the peer certificate chain, so the target is the function invoked with the
handshake/session structure on that path — this is the shape that Flutter-unpinning write-ups call the
session-creator route. It survives string and symbol stripping, because the call graph survives, and
it costs more: you must identify the handshake structure first, which is why the string anchor is the
fast path and this is the fallback when an engine build has dropped the string. `unverified` here — no
engine binary was analysed in this repository.

**When the system store is genuinely enough.** If the client is Java-side and non-pinning, moving the
CA into the system store is the least invasive change and needs no per-library work. The decision is
therefore: identify the client first (`tls-and-cert.md` §Step 4 attribution), then choose the
mechanism. Patching a library that was never consulting the store is work with no effect; installing
a system CA when a native verifier ignores it produces the same empty capture you started with.

## 6. Failure modes

**A decode that looks valid but is not.** protobuf is self-synchronising enough that random bytes
often decode into a plausible-looking field list. Guard against it by (a) decoding several samples of
the same message and expecting the same field set, (b) checking that nested lengths exactly consume
their parents, and (c) when you have a schema, re-encoding the decoded structure and comparing bytes
with the input — the same round-trip check used in, which caught a decoder bug in this
repository's own fixture.

**A framing choice that is wrong without being refused.** `--split varint-length` means protobuf's own
`writeDelimitedTo` framing: a varint length, then the message. gRPC frames a message differently — one
compression-flag byte, then a **four-byte big-endian** length (). Handed a real gRPC frame, the
varint splitter reported **five** frames rather than failing, while the same bytes decoded with no
splitting reported `stray_end_group`. Strip the 5-byte gRPC prefix yourself, and check the frame count
either way: a wrong split still produces a decode, which is what makes it expensive.

**Assuming the proxy sees everything.** The proxy sees what the client sends through it. An app that
uses QUIC (), a raw socket, a native client bypassing Java's HTTP stack, or a certificate-pinned
connection shows up as silence. Silence is evidence about the transport, not about the app: check
UDP activity, check whether a native library is doing the I/O (`lib_map.py`, `dynamic-frida.md`),
and only then conclude that a feature is client-side.

**Patching the wrong verifier.** Covered in §5: the failure is silent, and the resulting state is
worse than a clean failure because it looks like progress. Verify the hook against a connection
known to fail.

**Treating a recovered schema as ground truth for the server contract.** A schema recovered from the
client tells you what the client expects to send and parse — it does not prove the server honours
those fields, and it says nothing about authorization. `server-api.md` owns that question. The
recurring expensive mistake is to assume that because a field exists and is settable client-side, the
server will act on it.
