# Security Policy

## Supported versions

AOTopsy is a static analysis tool. Security-relevant fixes land on the latest release line.

| Version | Supported |
|---------|-----------|
| Latest `v1.x` release | ✅ |
| `develop` (rolling) | Best-effort |
| Older tags | ❌ |

## Reporting a vulnerability

Report suspected vulnerabilities — especially anything where a **malicious `libapp.so`
could crash, hang, or achieve code execution in the parser** — privately via GitHub
Security Advisories ("Report a vulnerability" on the repository **Security** tab). Please
do not open a public issue for exploitable parser bugs. Include the input snapshot (or a
minimized reproducer) and the command used.

AOTopsy ingests untrusted binaries by design. The snapshot parser is being hardened with
Go native fuzzing (`go test -fuzz`) and property invariants so that malformed or
unknown-format input fails safely rather than desyncing or crashing.

## Verifying release binaries

Every [release](https://github.com/BroNils/aotopsy/releases) ships a `SHA256SUMS.txt`.
Verify the archive you downloaded before running it:

```bash
# 1. download the archive + SHA256SUMS.txt from the release, then:
sha256sum -c SHA256SUMS.txt --ignore-missing
```

Releases cut by the automated pipeline (`.github/workflows/release.yml`) additionally
ship a **keyless Sigstore signature** of the checksum file and a **SLSA build-provenance
attestation** for each binary — no stored keys, bound to the GitHub Actions build via
OIDC. Verify them with:

```bash
# checksum-file signature (cosign v2+):
cosign verify-blob \
  --bundle SHA256SUMS.txt.sigstore.json \
  --certificate-identity-regexp 'https://github.com/BroNils/aotopsy/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  SHA256SUMS.txt

# build provenance of a downloaded binary:
gh attestation verify ./aotopsy --repo BroNils/aotopsy
```

## Handling of analyzed apps

AOTopsy runs entirely offline and does not transmit analyzed binaries or extracted data
anywhere. When reverse-engineering third-party apps, follow the applicable laws and terms;
recovered secrets, keys, or endpoints are the responsibility of the operator and must not
be committed to this repository.
