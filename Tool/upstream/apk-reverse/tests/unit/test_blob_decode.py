"""Unit tests for skills/apk-reverse/scripts/blob_decode.py.

The encoded-blob search is the part worth pinning: the whole method exists
because a single un-rotated inflate attempt fails and the failure looks like
"this is encrypted". The tests build blobs with known parameters and require the
search to recover them.
"""
from __future__ import annotations

import gzip
import json
import zlib

import pytest

from conftest import load_script, run_script

blob_decode = load_script("blob_decode.py")

pytestmark = pytest.mark.unit

PAYLOAD = json.dumps({
    "flags": {"newCheckout": True, "minVersion": 4210},
    "endpoints": ["https://api.example.invalid/v3/config"],
    "notes": "synthetic payload for the rotation search regression" * 3,
}).encode("utf-8")


# --------------------------------------------------------------------------- #
# outer encodings
# --------------------------------------------------------------------------- #
class TestOuterEncodings:
    @pytest.mark.parametrize("which", ["base64", "base64url", "hex"])
    def test_round_trip(self, which):
        data = bytes(range(64))
        encoded = blob_decode.outer_encode(data, which)
        assert blob_decode.outer_decode(encoded, which) == data

    def test_unknown_encoding_raises(self):
        with pytest.raises(ValueError):
            blob_decode.outer_encode(b"x", "rot13")

    def test_undecodable_hex_returns_empty_not_an_exception(self):
        """The search calls this on candidate encodings; a raise would abort it."""
        assert blob_decode.outer_decode("zzzz", "hex") == b""

    def test_whitespace_and_newlines_are_stripped_before_decoding(self):
        encoded = blob_decode.outer_encode(b"hello world", "base64")
        wrapped = "\n".join([encoded[:4], encoded[4:]])
        assert blob_decode.outer_decode(wrapped, "base64") == b"hello world"

    def test_sniff_offers_all_three_encodings(self):
        guesses = blob_decode.sniff_outer("aGVsbG8gd29ybGQgdGhpcyBpcyBhIHRlc3Q=")
        assert set(guesses) >= {"base64", "base64url", "hex"}

    def test_sniff_puts_hex_first_for_hex_shaped_text(self):
        assert blob_decode.sniff_outer("deadbeef" * 8)[0] == "hex"


# --------------------------------------------------------------------------- #
# inner transforms
# --------------------------------------------------------------------------- #
class TestInnerTransforms:
    def test_inflate_raw_round_trips_through_raw_deflate(self):
        body = blob_decode.inflate_raw(PAYLOAD)
        assert zlib.decompress(body, -15) == PAYLOAD

    def test_inflate_raw_output_has_no_zlib_header(self):
        """A raw stream is what the rotation search needs: no header to mis-align."""
        body = blob_decode.inflate_raw(b"x" * 200)
        with pytest.raises(zlib.error):
            zlib.decompress(body)   # default wbits expects a zlib header

    @pytest.mark.parametrize("name,blob", [
        ("raw", zlib.compressobj(9, zlib.DEFLATED, -15)),
        ("zlib", zlib.compressobj(9, zlib.DEFLATED, 15)),
        ("gzip", zlib.compressobj(9, zlib.DEFLATED, 31)),
    ])
    def test_try_inflate_names_each_inner_transform(self, name, blob):
        body = blob.compress(PAYLOAD) + blob.flush()
        got = blob_decode.try_inflate(body)
        assert got is not None
        assert got[0] == name
        assert got[1] == PAYLOAD

    def test_try_inflate_returns_none_for_noise(self):
        assert blob_decode.try_inflate(bytes(range(256))) is None

    def test_gzip_is_accepted_via_the_stdlib_helper(self):
        got = blob_decode.try_inflate(gzip.compress(PAYLOAD))
        assert got is not None and got[0] == "gzip" and got[1] == PAYLOAD


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
class TestScoring:
    def test_structured_text_scores_above_random_bytes(self):
        structured = blob_decode.score(PAYLOAD)
        noise = blob_decode.score(bytes(range(256)) * 4)
        assert structured > noise

    def test_a_json_header_is_rewarded(self):
        assert blob_decode.score(b'{"a": 1}') > blob_decode.score(b"aaaaaaaa")

    def test_empty_output_scores_negative(self):
        assert blob_decode.score(b"") < 0


# --------------------------------------------------------------------------- #
# the rotation search
# --------------------------------------------------------------------------- #
def rotate(body, cut):
    return body[-cut:] + body[:-cut] if cut else body


class TestRotationSearch:
    def _hits(self, blob, max_skip=0):
        return blob_decode.search(blob, max_skip, lambda _msg: None)

    def test_search_recovers_a_rotated_raw_stream(self):
        body = blob_decode.inflate_raw(PAYLOAD)
        cut = 7
        hits = self._hits(rotate(body, cut))
        matching = [h for h in hits if h["data"] == PAYLOAD]
        assert matching, "the rotation with cut=%d was not recovered" % cut
        assert matching[0]["cut"] == cut
        assert matching[0]["inner"] == "raw"
        assert matching[0]["size"] == len(PAYLOAD)

    def test_search_recovers_a_prefixed_and_rotated_stream(self):
        """The `skip` arm: a short header in front of the compressed stream."""
        body = blob_decode.inflate_raw(PAYLOAD)
        blob = b"\x01\x02" + rotate(body, 5)
        hits = self._hits(blob, max_skip=4)
        matching = [h for h in hits if h["data"] == PAYLOAD]
        assert matching, "skip=2 + cut=5 was not recovered"
        assert matching[0]["skip"] == 2

    def test_search_on_noise_returns_no_hits(self):
        assert self._hits(bytes(range(64))) == []

    def test_scores_are_reported_rounded(self):
        body = blob_decode.inflate_raw(PAYLOAD)
        hits = self._hits(body)
        assert hits
        assert all(isinstance(h["score"], float) for h in hits)

    def test_the_shortest_accepted_body_is_eight_bytes(self):
        """Documented floor: `m < 8` breaks the loop, so tiny blobs yield nothing."""
        assert self._hits(b"\x01\x02\x03") == []


# --------------------------------------------------------------------------- #
# the CLI-level write-back contract
# --------------------------------------------------------------------------- #
class TestEncodePath:
    def test_encode_then_decode_recovers_the_payload(self, tmp_path):
        """The write-back line the tool prints must actually round-trip."""
        payload_file = tmp_path / "payload.bin"
        payload_file.write_bytes(PAYLOAD)

        encoded_file = tmp_path / "value.txt"
        enc = run_script("blob_decode.py",
                         ["--encode", "--file", str(payload_file), "--inner", "raw",
                          "--outer", "base64", "--cut", "0", "--out", str(encoded_file)])
        assert enc.returncode == 0, enc.output

        back = run_script("blob_decode.py",
                          ["--file", str(encoded_file), "--outer", "base64",
                           "--min-size", "1", "--out", str(tmp_path / "back.bin")])
        assert back.returncode == 0, back.output
        assert (tmp_path / "back.bin").read_bytes() == PAYLOAD

    def test_an_undecodable_blob_exits_one(self, tmp_path):
        value = tmp_path / "value.txt"
        value.write_text("not-a-blob-at-all-just-prose-text\n", encoding="utf-8")
        result = run_script("blob_decode.py", ["--file", str(value), "--outer", "hex"])
        assert result.returncode == 1, result.output
        assert not result.has_traceback

    def test_empty_stdin_is_reported_as_invalid_input(self):
        """Exit code 2, not 1: an empty input is invalid, not a failed decode."""
        result = run_script("blob_decode.py", [], stdin="   ")
        assert result.returncode == 2, result.output
        assert "empty input" in result.output
