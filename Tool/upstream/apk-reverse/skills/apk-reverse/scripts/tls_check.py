#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TLS certificate health check for one or more hosts.

WHY THIS EXISTS
---------------
When a repacked app's login/registration fails with
`Chain validation failed` / `SSLHandshakeException`, the cause is often the
*server* certificate, not your patch. This script answers that question
independently of the app, so you can rule the server side in or out **before**
touching the APK. It is step 2 of the three-step TLS triage:
  1. take the real request URL / host out of the runtime probe (see frida_probe.js)
  2. verify that host's certificate out-of-band  <-- this script
  3. compare with another host of the same app (usually one of them is fine),
     which proves the failure is host-specific and not your clock/network

WHY IT STILL PRINTS THE CERTIFICATE WHEN VERIFICATION FAILS
-----------------------------------------------------------
`ssl.SSLSocket.getpeercert()` returns an empty dict whenever the handshake was
not validated, and `verification_mode=CERT_NONE` never validates. So on failure
we re-read the peer certificate in DER form and decode it locally. That is what
turns "it failed" into "it failed because notAfter is 39 days in the past".

WHAT IT REPORTS
---------------
Per host: strict verification result, protocol/cipher, subject, issuer,
notBefore, notAfter, days remaining, and a classification of the failure:
  EXPIRED            certificate has expired
  NOT-YET-VALID      certificate is not valid yet
  HOSTNAME-MISMATCH  chain is fine, the name does not match
  UNTRUSTED-CA       self-signed, or issuer not in the trust store
  CHAIN-BROKEN       bad signature / invalid CA / incomplete chain
  REVOKED            revoked by the issuer
  OTHER              anything else, with the raw OpenSSL message

Exit code: 0 if every host verified strictly, 2 if any host failed.
Pure standard library, Python 3.9+.

USAGE
-----
  python tls_check.py api.example.com
  python tls_check.py api.example.com cdn.example.com
  python tls_check.py api.example.com --port 8443
  python tls_check.py 203.0.113.10 --sni api.example.com   # IP + real SNI name
  python tls_check.py api.example.com --json                # machine-readable
"""
import argparse
import hashlib
import json
import os
import socket
import ssl
import sys
import tempfile
from datetime import datetime, timezone

DEFAULT_PORT = 443
DEFAULT_TIMEOUT = 10

# OpenSSL X509_V_ERR_* -> (classification, human readable)
VERIFY_CODE_CLASS = {
    7: ('CHAIN-BROKEN', 'certificate signature failure'),
    9: ('NOT-YET-VALID', 'certificate is not yet valid'),
    10: ('EXPIRED', 'certificate has expired'),
    18: ('UNTRUSTED-CA', 'self-signed certificate'),
    19: ('UNTRUSTED-CA', 'self-signed certificate in certificate chain'),
    20: ('UNTRUSTED-CA', 'unable to get local issuer certificate'),
    21: ('UNTRUSTED-CA', 'unable to verify the first certificate'),
    24: ('CHAIN-BROKEN', 'invalid CA certificate'),
    27: ('REVOKED', 'certificate revoked'),
    62: ('HOSTNAME-MISMATCH', 'hostname mismatch'),
}

# What a failure means for the reverse-engineering workflow.
CLASS_ACTION = {
    'EXPIRED': 'server-side problem: the certificate chain is not trustworthy '
               'any more. Re-signing the APK cannot fix this, and a client patch '
               'is the only way to keep the app usable.',
    'NOT-YET-VALID': 'either the server is misconfigured or the device clock is '
                     'wrong. Check the device date before blaming the app.',
    'HOSTNAME-MISMATCH': 'the chain is valid but the connection is using the '
                         'wrong name. Check for a proxy, a hosts entry, or a '
                         'hardcoded IP + wrong SNI.',
    'UNTRUSTED-CA': 'the presented chain is not rooted in the system trust store. '
                    'Expected for a MITM/proxy setup; suspicious for a public API.',
    'CHAIN-BROKEN': 'the server sent an incomplete or internally inconsistent '
                    'chain. Often a missing intermediate certificate.',
    'REVOKED': 'the certificate was revoked by its issuer.',
    'OTHER': 'read the raw OpenSSL message below; this is not one of the '
             'well-known failure classes.',
}


def fmt_name(parts):
    """Flatten ((('commonName','x'),),) into 'commonName=x'."""
    if not parts:
        return None
    flat = []
    for rdn in parts:
        for key, val in rdn:
            flat.append('%s=%s' % (key, val))
    return ', '.join(flat)


def parse_asn1_time(text):
    """'Nov 29 23:59:59 2026 GMT' -> aware UTC datetime (or None)."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.endswith(' GMT') or cleaned.endswith(' UTC'):
        cleaned = cleaned[:-4].rstrip()
    try:
        return datetime.strptime(cleaned, '%b %d %H:%M:%S %Y').replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def decode_der(der):
    """Decode a DER certificate without ever verifying it.

    Uses the CPython private helper that backs `getpeercert()`; if it is not
    available we still return what we can (length + fingerprint), because a
    partially decoded certificate beats no certificate at all.
    """
    info = {'der_bytes': len(der),
            'sha256': hashlib.sha256(der).hexdigest(),
            'sha1': hashlib.sha1(der).hexdigest()}
    helper = getattr(getattr(ssl, '_ssl', None), '_test_decode_cert', None)
    if helper is None:
        return info
    path = None
    try:
        pem = ssl.DER_cert_to_PEM_cert(der)
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as fh:
            path = fh.name
            fh.write(pem)
        info.update(helper(path))
    except Exception:
        pass
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return info


def fetch_peer_cert(host, port, sni, timeout):
    """Read the peer certificate even when the chain cannot be validated."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with ctx.wrap_socket(raw, server_hostname=sni) as tls:
            der = tls.getpeercert(binary_form=True)
    return decode_der(der) if der else {}


def strict_connect(host, port, sni, timeout):
    """Full strict verification: system trust store + hostname match."""
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with ctx.wrap_socket(raw, server_hostname=sni) as tls:
            return {
                'cert': tls.getpeercert() or {},
                'protocol': tls.version(),
                'cipher': (tls.cipher() or ('', '', ''))[0],
            }


def check_host(host, port, sni, timeout):
    """Return one result dict; never raises for network/TLS problems."""
    res = {
        'host': host,
        'port': port,
        'sni': sni,
        'ok': False,
        'classification': None,
        'reason': None,
        'verify_code': None,
        'protocol': None,
        'cipher': None,
        'subject': None,
        'issuer': None,
        'not_before': None,
        'not_after': None,
        'days_remaining': None,
        'fingerprint_sha256': None,
        'action': None,
        'error': None,
    }

    try:
        hit = strict_connect(host, port, sni, timeout)
    except ssl.SSLCertVerificationError as exc:
        code = getattr(exc, 'verify_code', None)
        cls, human = VERIFY_CODE_CLASS.get(code, ('OTHER', getattr(exc, 'verify_message', str(exc))))
        res['classification'] = cls
        res['reason'] = human
        res['verify_code'] = code
        res['action'] = CLASS_ACTION.get(cls)
        res['error'] = '%s: %s' % (type(exc).__name__, exc)
    except (ssl.SSLError, socket.error, OSError) as exc:
        res['classification'] = 'OTHER'
        res['reason'] = 'connection or handshake failed before certificate validation'
        res['action'] = CLASS_ACTION['OTHER']
        res['error'] = '%s: %s' % (type(exc).__name__, exc)
        return res
    else:
        cert = hit['cert']
        res.update({'ok': True, 'protocol': hit['protocol'], 'cipher': hit['cipher'],
                    'subject': fmt_name(cert.get('subject')),
                    'issuer': fmt_name(cert.get('issuer')),
                    'not_before': cert.get('notBefore'),
                    'not_after': cert.get('notAfter')})
        res['days_remaining'] = days_left(res['not_after'])
        return res

    # Verification failed: still try to show the real certificate.
    try:
        cert = fetch_peer_cert(host, port, sni, timeout)
    except Exception as exc:
        res['error'] = (res['error'] or '') + ' | peek failed: %s' % exc
        return res

    res.update({'subject': fmt_name(cert.get('subject')),
                'issuer': fmt_name(cert.get('issuer')),
                'not_before': cert.get('notBefore'),
                'not_after': cert.get('notAfter'),
                'fingerprint_sha256': cert.get('sha256')})
    res['days_remaining'] = days_left(res['not_after'])
    return res


def days_left(not_after):
    dt = parse_asn1_time(not_after)
    if dt is None:
        return None
    return (dt - datetime.now(timezone.utc)).days


def report(res, out=sys.stdout):
    w = out.write
    w('== %s:%d%s\n' % (res['host'], res['port'],
                        '' if res['sni'] == res['host'] else '  (SNI: %s)' % res['sni']))
    if res['ok']:
        w('   status         : OK (strict verification passed)\n')
    else:
        w('   status         : FAIL - %s\n' % res['classification'])
        w('   reason         : %s\n' % res['reason'])
        if res['verify_code'] is not None:
            w('   verify_code    : %d\n' % res['verify_code'])
    if res['protocol']:
        w('   protocol       : %s  cipher: %s\n' % (res['protocol'], res['cipher']))
    w('   subject        : %s\n' % (res['subject'] or '<undecoded>'))
    w('   issuer         : %s\n' % (res['issuer'] or '<undecoded>'))
    w('   notBefore      : %s\n' % (res['not_before'] or '<unknown>'))
    w('   notAfter       : %s\n' % (res['not_after'] or '<unknown>'))
    days = res['days_remaining']
    if days is not None:
        if days < 0:
            w('   validity       : EXPIRED %d days ago\n' % (-days))
        else:
            w('   days remaining : %d\n' % days)
    if res['fingerprint_sha256']:
        w('   sha256         : %s\n' % res['fingerprint_sha256'])
    if res['action'] and not res['ok']:
        w('   action         : %s\n' % res['action'])
    if res['error']:
        w('   raw error      : %s\n' % res['error'])
    w('\n')


def main():
    ap = argparse.ArgumentParser(
        description='Verify TLS certificates for one or more hosts, strictly, '
                    'and classify any failure (expired / hostname mismatch / untrusted CA).')
    ap.add_argument('hosts', nargs='+', metavar='HOST',
                    help='hostname or IP to check, e.g. api.example.com')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT,
                    help='TCP port (default %d)' % DEFAULT_PORT)
    ap.add_argument('--sni', default=None,
                    help='override the SNI/hostname to validate against; useful when '
                         'HOST is a bare IP, e.g. --sni api.example.com')
    ap.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT,
                    help='connect timeout in seconds (default %d)' % DEFAULT_TIMEOUT)
    ap.add_argument('--json', action='store_true', help='emit JSON instead of a report')
    args = ap.parse_args()

    results = []
    for host in args.hosts:
        sni = args.sni or host
        results.append(check_host(host, args.port, sni, args.timeout))

    if args.json:
        json.dump(results, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write('\n')
    else:
        for res in results:
            report(res)

        bad = [r for r in results if not r['ok']]
        good = [r for r in results if r['ok']]
        if len(results) > 1:
            if bad and good:
                print('SUMMARY: %d/%d hosts failed. At least one host on this app '
                      'verifies fine, so the failure is host-specific (server side), '
                      'not a clock/network problem on your side.'
                      % (len(bad), len(results)))
            elif bad:
                print('SUMMARY: every host failed. Suspect the network path, a proxy, '
                      'or the device/host clock before blaming the app.')
            else:
                print('SUMMARY: all %d hosts verified strictly.' % len(results))
        for r in bad:
            print('FAIL %s -> %s' % (r['host'], r['classification']))

    return 0 if all(r['ok'] for r in results) else 2


if __name__ == '__main__':
    sys.exit(main())
