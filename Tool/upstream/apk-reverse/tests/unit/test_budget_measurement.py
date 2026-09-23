"""The budget gate must reach the same verdict whether or not `tiktoken` is installed.

This is a small test for a defect that cost two red CI runs. `check_budget.py` measures the
always-loaded body in tokens, preferring `tiktoken` and falling back to `characters / N` when it is
absent. The first version's `N` was guessed (3.6) instead of calibrated, so a machine with tiktoken
saw ~10,900 tokens and passed while a machine without it saw ~13,200 and warned -- and this
repository's gate runner (CI's 3.11 job, and any contributor's box) is the one without it.

A gate whose answer depends on which packages the runner happens to have installed is not a gate, so
both paths are forced here and compared.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

pytestmark = pytest.mark.unit


@pytest.fixture
def budget():
    sys.path.insert(0, str(REPO_ROOT))
    return importlib.import_module("check_budget")


def _has_tiktoken():
    """Whether a real tokenizer is available, reported rather than assumed.

    The comparison needs *two* implementations; where there is only one, the honest outcome is a
    skip with the install command, not a failure and not a silent pass. CI installs it, so the
    property is verified where it matters; a contributor without it has both gates agreeing anyway,
    because the fallback is calibrated to the same constant.
    """
    try:
        import tiktoken  # noqa: F401
        return True
    except Exception:
        return False


pytestmark = pytest.mark.unit


def test_the_fallback_estimate_agrees_with_the_real_tokenizer(budget):
    """Both measurement paths must land on the same side of the soft budget."""
    if not _has_tiktoken():
        pytest.skip("tiktoken is not installed here, so there is no measurement to compare against; "
                    "install it with `python -m pip install tiktoken`")
    text = (REPO_ROOT / "skills" / "apk-reverse" / "SKILL.md").read_text(encoding="utf-8")

    real, how_real = budget.token_estimate(text)
    assert "tiktoken" in how_real, how_real

    # Force the fallback path by handing the module a tokenizer that cannot be imported.
    saved = sys.modules.get("tiktoken")
    sys.modules["tiktoken"] = None          # `import tiktoken` raises here
    try:
        fallback, how_fallback = budget.token_estimate(text)
    finally:
        if saved is not None:
            sys.modules["tiktoken"] = saved
        else:
            sys.modules.pop("tiktoken", None)

    assert "estimate" in how_fallback, how_fallback
    drift = abs(real - fallback) / max(1, real)
    assert drift < 0.05, (
        "the fallback is %.1f%% away from tiktoken (%d vs %d): recalibrate TOKENS_PER_CHAR "
        "against a fresh measurement rather than a guess" % (100 * drift, fallback, real))
    assert (real <= budget.TOKEN_SOFT) == (fallback <= budget.TOKEN_SOFT), (
        "the two paths straddle the soft budget (%d real / %d fallback vs %d): the gate would "
        "answer differently on CI than on a developer machine"
        % (real, fallback, budget.TOKEN_SOFT))


def test_the_fallback_constant_is_the_calibrated_one(budget):
    """Pin the constant to a measurement: `chars / tokens` on SKILL.md, recomputed here."""
    text = (REPO_ROOT / "skills" / "apk-reverse" / "SKILL.md").read_text(encoding="utf-8")
    real, how = budget.token_estimate(text)
    if "tiktoken" not in how:
        pytest.skip("no tiktoken available, so there is no measurement to calibrate against")
    expected = len(text) / real
    assert abs(budget.TOKENS_PER_CHAR - expected) < 0.25, (
        "TOKENS_PER_CHAR is %.3f but this SKILL.md measures %.3f characters per token -- the "
        "document changed, so recalibrate" % (budget.TOKENS_PER_CHAR, expected))
