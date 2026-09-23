"""Regression tests for the documented-command gate itself.

`check_commands.py` is the gate that proves other documentation is runnable, so a blind spot in it
is worth more than a blind spot elsewhere: it turns "146 commands checked, 0 drift" into a claim the
repository cannot back. One such blind spot is pinned here, exactly as it was found.

**What was wrong.** `resolve_script()` tried the *document's own directory* first when resolving a
relative path. A bare `python analyze_pair.py` written inside `docs/tool-verification/` therefore
resolved to `tools/_work/bench/unpack/b3/analyze_pair.py` -- a real file, inside the gitignored
workbench -- and scored `ok`. Seven commands in two evidence files used that form while the same
files wrote the correct path elsewhere, and a reader copying one from the repository root gets
"No such file". The gate said the documentation was clean.

The tests below drive the resolver and the finding classifier directly rather than through the CLI,
so they stay fast and do not depend on the current state of the documentation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

pytestmark = pytest.mark.integration

CHECK_COMMANDS = REPO_ROOT / "check_commands.py"


@pytest.fixture(scope="module")
def gate():
    """The gate as a module, so its internals can be driven without a subprocess."""
    sys.path.insert(0, str(REPO_ROOT))
    import importlib

    return importlib.import_module("check_commands")


def _workbench_script_name(gate):
    """A `.py` basename that exists only under tools/, or skip if the workbench is absent."""
    names = sorted(gate._workbench_names())
    if not names:
        pytest.skip("no workbench present (tools/ is gitignored and may not exist in a checkout)")
    shipped = {p.name for p in (REPO_ROOT / "skills" / "apk-reverse" / "scripts").glob("*.py")}
    root = {p.name for p in REPO_ROOT.glob("*.py")}
    for name in names:
        if name not in shipped and name not in root:
            return name
    pytest.skip("every workbench script name is also shipped; nothing to test with")


def test_a_bare_name_that_only_exists_in_the_workbench_is_drift(gate):
    """The exact defect: the name exists *somewhere*, which used to be enough to pass it."""
    name = _workbench_script_name(gate)
    doc = str(REPO_ROOT / "docs" / "tool-verification" / "EXTENSION-extraction-shell-bench.md")
    path, why = gate.resolve_script(name, doc, include_workbench=False)
    assert path is None
    assert why == "unqualified-workbench", why

    text = "```\n$ python %s --flag\n```\n" % name
    findings = gate.command_findings(doc, text, {}, False)
    kinds = [f["kind"] for f in findings]
    assert "unqualified-workbench" in kinds, findings


def test_a_path_qualified_workbench_reference_is_a_skip_not_drift(gate):
    """`tools/_work/...` is deliberate in an evidence record: a skip, reported with its reason."""
    name = _workbench_script_name(gate)
    doc = str(REPO_ROOT / "docs" / "tool-verification" / "EXTENSION-extraction-shell-bench.md")
    _path, why = gate.resolve_script("tools/_work/bench/unpack/b3/%s" % name, doc,
                                     include_workbench=False)
    assert why == "workbench"


@pytest.fixture
def fake_repo(gate, tmp_path, monkeypatch):
    """A repository-shaped tree with its own workbench, so resolution can be tested anywhere.

    This exists because the workbench-dependent tests above cannot run on a clean checkout: the
    `tools/` tree is gitignored, so on CI they skip and the gate's most important property goes
    unverified exactly where it matters. The tree built here has the layout the resolver assumes
    (a root, a skill dir, a gitignored `tools/`) and nothing else.
    """
    root = tmp_path / "repo"
    (root / "skills" / "apk-reverse" / "scripts").mkdir(parents=True)
    (root / "docs" / "tool-verification").mkdir(parents=True)
    (root / "tools" / "_work" / "bench").mkdir(parents=True)
    (root / "README.md").write_text("# root\n", encoding="utf-8")
    (root / "skills" / "apk-reverse" / "scripts" / "shipped.py").write_text(
        '"""capability: x\n"""\nimport argparse\np = argparse.ArgumentParser()\n'
        'p.add_argument("--flag")\n', encoding="utf-8")
    (root / "tools" / "_work" / "bench" / "solo_in_workbench.py").write_text(
        "print('x')\n", encoding="utf-8")
    (root / "docs" / "tool-verification" / "record.md").write_text("# record\n", encoding="utf-8")

    monkeypatch.setattr(gate, "ROOT", str(root))
    monkeypatch.setattr(gate, "SKILL_DIR", str(root / "skills" / "apk-reverse"))
    monkeypatch.setattr(gate, "SCRIPT_DIR", str(root / "skills" / "apk-reverse" / "scripts"))
    gate._WORKBENCH_INDEX.clear()
    yield root
    gate._WORKBENCH_INDEX.clear()


def test_resolution_order_is_root_then_skill_then_document(gate, fake_repo):
    """The corrected order, asserted against a tree that exists on any machine."""
    doc = str(fake_repo / "docs" / "tool-verification" / "record.md")
    path, why = gate.resolve_script("README.md", doc, include_workbench=False)
    assert why == "ok" and path.endswith("README.md")
    path, why = gate.resolve_script("shipped.py", doc, include_workbench=False)
    assert why == "ok" and path.endswith("shipped.py")


def test_a_workbench_only_name_is_drift_and_a_qualified_one_is_not(gate, fake_repo):
    doc = str(fake_repo / "docs" / "tool-verification" / "record.md")
    path, why = gate.resolve_script("solo_in_workbench.py", doc, include_workbench=False)
    assert (path, why) == (None, "unqualified-workbench")
    path, why = gate.resolve_script("tools/_work/bench/solo_in_workbench.py", doc,
                                    include_workbench=False)
    assert (path, why) == (None, "workbench")


def test_a_bare_name_the_document_paths_elsewhere_is_a_skip(gate, fake_repo):
    """The fix that made the gate behave the same on CI as on a populated machine.

    `solo_in_workbench.py` appears once bare and once with a path in the same document. The
    document has already told the reader where it lives, so the bare line is a shorthand -- and
    that verdict must not depend on the gitignored tree being visible, which is how the first
    version of this fix passed locally and failed on CI.
    """
    doc = str(fake_repo / "docs" / "tool-verification" / "record.md")
    text = ("Path: `tools/_work/bench/solo_in_workbench.py` explains it.\n\n"
            "```\n$ python solo_in_workbench.py\n```\n")
    findings = gate.command_findings(doc, text, {}, False)
    kinds = [f["kind"] for f in findings]
    assert "unqualified-workbench" not in kinds, findings
    assert "missing-script" not in kinds, findings
    assert "skipped" in kinds, findings


def test_a_bare_name_after_cd_with_no_resolution_is_skipped_not_drift(gate, fake_repo):
    """`cd <somewhere cloned>` then a bare name: unverifiable, and reported as such."""
    doc = str(fake_repo / "docs" / "tool-verification" / "record.md")
    text = "```\n$ cd tools/_work/bench/repos/elsewhere\n$ python upstream_tool.py --x\n```\n"
    findings = gate.command_findings(doc, text, {}, False)
    kinds = [f["kind"] for f in findings]
    assert "missing-script" not in kinds, findings
    assert "after-cd-unresolved" in kinds, findings


def test_the_external_dcc_entry_point_is_never_drift(gate):
    """`python dcc.py` after `cd tools/_work/bench/repos/dcc` runs inside the external dcc
    checkout, so it is a skip on every machine -- including one without the workbench.

    The name is declared in EXTERNAL_SCRIPTS because recognition by filename needs `tools/` to
    exist: on a clean checkout `dcc.py` degraded to `missing-script` drift and the gate failed away
    from the machine that wrote the record. Asserted as a *property* rather than as one specific
    reason, because two mechanisms can legitimately produce it -- the declared entry point and the
    workbench-after-`cd` rule -- and pinning either one alone makes the test machine-dependent,
    which is the very defect it is guarding against.
    """
    doc = str(REPO_ROOT / "docs" / "tool-verification" / "EXTENSION-java2c.md")
    _path, why = gate.resolve_script("dcc.py", doc, include_workbench=False, chdir=True)
    assert why in ("external", "workbench-after-cd"), why

    text = "```\n$ cd tools/_work/bench/repos/dcc\n$ python dcc.py --no-build\n```\n"
    findings = gate.command_findings(doc, text, {}, False)
    kinds = [f["kind"] for f in findings]
    assert "missing-script" not in kinds, findings
    assert "unqualified-workbench" not in kinds, findings
    assert any(k in ("workbench-after-cd", "external") for k in kinds), findings


def test_a_shipped_script_resolves_from_the_repository_root(gate):
    """The order that matters: root, then the skill's scripts, then the document's own directory."""
    doc = str(REPO_ROOT / "docs" / "tool-verification" / "README.md")
    path, why = gate.resolve_script("check_repo.py", doc, include_workbench=False)
    assert why == "ok" and path and path.endswith("check_repo.py")
    path, why = gate.resolve_script("skills/apk-reverse/scripts/scan_leaks.py", doc,
                                    include_workbench=False)
    assert why == "ok" and path and path.endswith("scan_leaks.py")


def test_the_committed_tree_reports_no_drift(gate, tmp_path):
    """The gate's own verdict on this repository, run in-process so it cannot drift silently."""
    docs = gate.collect_docs(None)
    findings = []
    cache = {}
    for doc in docs:
        try:
            text = Path(doc).read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(gate.command_findings(doc, text, cache, False))
    drift = [f for f in findings
             if f["kind"] in ("unknown-flag", "missing-script", "unqualified-workbench")]
    detail = "\n".join("  %s:%s %s (%s)" % (f["doc"], f["line"], f["command"], f["kind"])
                       for f in drift[:20])
    assert not drift, "documented commands that cannot run:\n%s" % detail
