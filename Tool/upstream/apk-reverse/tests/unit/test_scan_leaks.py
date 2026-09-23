"""Unit tests for skills/apk-reverse/scripts/scan_leaks.py.

Decoys are built in a temporary directory at run time. No real target identity
is committed here, and the token-shaped decoys are assembled from fragments so
that this test file itself cannot become a finding if the scanner is ever
pointed at the tests tree.
"""
from __future__ import annotations

import json

import pytest

from conftest import load_script, run_script

scan_leaks = load_script("scan_leaks.py")

pytestmark = pytest.mark.unit


# Synthetic identifiers: reverse-domain-shaped, not derived from any real target.
DECOY_PACKAGE = "com." + "acme" + ".targetapp"
DECOY_TOKEN = "AbCdEf" + "0123456789" + "XyZ"
DECOY_USER = "mkessler"


def write(root, name, body):
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def scan(root, *extra, timeout=120):
    """Run the scanner over a temporary root and parse its JSON report."""
    result = run_script("scan_leaks.py",
                        ["--root", str(root), "--format", "json"] + list(extra),
                        timeout=timeout)
    assert not result.timed_out, "scan_leaks.py did not finish: %r" % result
    assert not result.has_traceback, result.output
    # The JSON document is printed first, then the RESULT token line.
    lines = result.stdout.splitlines()
    token = lines[-1] if lines else ""
    doc = json.loads(result.stdout[:result.stdout.rindex("}") + 1])
    return result, doc, token


# --------------------------------------------------------------------------- #
# the exemption list as data
# --------------------------------------------------------------------------- #
class TestExemptions:
    @pytest.mark.parametrize("value", [
        "com.android.internal",
        "androidx.core.app",
        "com.google.firebase",
        "org.example.demo",
        "<pkg>",
        "${PKG}",
        "sg.vantagepoint.uncrackable1",
    ])
    def test_benign_values_carry_an_exemption_reason(self, value):
        assert scan_leaks._benign_package(value) != "", value

    @pytest.mark.parametrize("value", [
        DECOY_PACKAGE,
        "com.unknownvendor.someapp",
    ])
    def test_unknown_reverse_domain_values_are_reportable(self, value):
        assert scan_leaks._benign_package(value) == "", value

    def test_loopback_and_documentation_addresses_are_distinguished(self):
        """Loopback is exempt; an RFC 5737 documentation address is reported on purpose."""
        assert scan_leaks._benign_ip("127.0.0.1:8080") != ""
        assert scan_leaks._benign_ip("192.0.2.10:8080") == ""

    def test_placeholder_user_paths_are_exempt(self):
        assert scan_leaks._benign_path("C:\\Users\\<user>\\work") != ""
        assert scan_leaks._benign_path("/home/" + DECOY_USER + "/work") == ""


# --------------------------------------------------------------------------- #
# decoys that must be reported
# --------------------------------------------------------------------------- #
class TestDecoyDetection:
    def test_strong_decoys_are_reported(self, tmp_path):
        write(tmp_path, "notes.md", "\n".join([
            'package="%s"' % DECOY_PACKAGE,
            "Authorization: Bearer " + DECOY_TOKEN,
            "/home/%s/work/build/classes.dex" % DECOY_USER,
        ]) + "\n")

        result, doc, token = scan(tmp_path)

        rules = sorted({f["rule"] for f in doc["findings"]})
        assert "bundle_pkg_attr" in rules
        assert "token_authorization_header" in rules
        assert "user_path_posix" in rules
        assert all(f["strength"] in ("strong", "certain") for f in doc["findings"])
        assert token == "RESULT=leaks_found"
        assert result.returncode == 1, result.output

    def test_findings_carry_context_not_just_a_line_number(self, tmp_path):
        write(tmp_path, "notes.md", 'package="%s"\n' % DECOY_PACKAGE)
        _result, doc, _token = scan(tmp_path)
        finding = doc["findings"][0]
        assert finding["context"].strip()
        assert finding["match"] == DECOY_PACKAGE
        assert finding["line"] == 1
        assert finding["file"] == "notes.md"

    def test_device_serial_shaped_token_is_reported(self, tmp_path):
        # 16 uppercase alphanumerics with at least one letter, next to a device word.
        serial = "R58M" + "12ABCDEF" + "9K7Q"
        assert len(serial) == 16
        write(tmp_path, "adb.txt", "device %s\n" % serial)
        _result, doc, token = scan(tmp_path)
        assert any(f["rule"].startswith("device_serial") for f in doc["findings"]), doc
        assert token == "RESULT=leaks_found"


# --------------------------------------------------------------------------- #
# decoys that must not be reported
# --------------------------------------------------------------------------- #
class TestExemptDecoysStaySilent:
    def test_benign_identifiers_produce_no_findings(self, tmp_path):
        write(tmp_path, "notes.md", "\n".join([
            'package="com.android.internal"',
            'package="com.google.firebase.messaging"',
            'package="<pkg>"',
            "endpoint 127.0.0.1:8080",
            "path C:\\Users\\<user>\\work\\x.dex",
            "public crackme sg.vantagepoint.uncrackable1",
        ]) + "\n")

        result, doc, token = scan(tmp_path)

        assert doc["findings"] == [], doc["findings"]
        assert token == "RESULT=clean"
        assert result.returncode == 0

    def test_exempted_hits_are_kept_and_auditable_with_show_exempt(self, tmp_path):
        """The exemption list must be inspectable, not just silent."""
        write(tmp_path, "notes.md", 'package="com.android.internal"\n')
        _result, doc, _token = scan(tmp_path, "--show-exempt")
        assert doc["findings"] == []
        assert doc["exempted"], "an exempted hit must still be recorded"
        assert doc["exempted"][0]["exempt_reason"]

    def test_a_weak_only_hit_keeps_the_default_gate_green(self, tmp_path):
        """Documented behaviour: an RFC 5737 address is reported but does not fail --fail-on strong.

        Note the measured detail: `ip:port` satisfies both endpoint rules, so one
        address is reported twice (once as the `ip:port` form, once as the bare
        literal). Recorded here rather than smoothed over -- it is a report-volume
        question, not a missed or invented finding.
        """
        write(tmp_path, "notes.md", "endpoint 192.0.2.10:8080\n")

        result, doc, token = scan(tmp_path)
        assert {f["strength"] for f in doc["findings"]} == {"weak"}
        assert {f["rule"] for f in doc["findings"]} == {"plain_addr", "plain_addr_ipliteral"}
        assert token == "RESULT=leaks_found_strong_only"
        assert result.returncode == 0

        strict, _doc2, strict_token = scan(tmp_path, "--fail-on", "any")
        assert strict_token == "RESULT=leaks_found"
        assert strict.returncode == 1


# --------------------------------------------------------------------------- #
# the machine-readable contract
# --------------------------------------------------------------------------- #
class TestReportContract:
    def test_json_report_has_the_documented_keys(self, tmp_path):
        write(tmp_path, "notes.md", 'package="%s"\n' % DECOY_PACKAGE)
        _result, doc, _token = scan(tmp_path)
        assert set(doc) >= {"root", "files_scanned", "findings", "exempted",
                            "errors", "result", "fail_on"}
        assert doc["result"] == "leaks_found"
        assert doc["fail_on"] == "strong"

    def test_result_token_is_always_the_last_line(self, tmp_path):
        write(tmp_path, "notes.md", 'package="%s"\n' % DECOY_PACKAGE)
        result, _doc, token = scan(tmp_path)
        assert result.stdout.splitlines()[-1] == token
        assert token.startswith("RESULT=")

    def test_list_rules_prints_the_table_and_exits_zero(self):
        result = run_script("scan_leaks.py", ["--list-rules"])
        assert result.returncode == 0, result.output
        assert not result.has_traceback
        for rule_id in ("bundle_pkg_attr", "device_serial", "token_github_pat",
                        "appkey_assignment", "user_path_posix"):
            assert rule_id in result.stdout

    def test_unknown_category_is_a_usage_error(self, tmp_path):
        result = run_script("scan_leaks.py",
                            ["--root", str(tmp_path), "--only", "nosuchcategory"])
        assert result.returncode == 2, result.output
