"""CLI contract tests: every shipped script, four invocation shapes each.

What is asserted, per the repository-wide contract in REBUILD-BRIEF section 4:

  1. `--help` succeeds and never prints an uncaught traceback.
  2. An unknown flag is a usage error: exit 2.
  3. An invocation with required arguments missing, or with every input pointed
     at a file that does not exist, is a usage error: exit 2.
  4. A script that advertises `--json` emits a parseable JSON document that
     states a `status`.
  5. Every observed exit code is one of 0/1/2/3/4.

Two clean outcomes are distinguished, and the distinction is the whole point:

  * `xfail` means the script is on the tree and does **not** meet the contract.
    The reason carries the measured value. The xfail list this file produces is
    the work order for exit-code unification -- it is not a defect to be fixed
    here, because every one of those scripts has an owner.
  * `skip` means the scenario is not applicable or not reachable on a machine
    with no device, no network and no frida. Those are coverage gaps, and they
    are reported as such in docs/tool-verification/EXTENSION-test-harness.md.

Each scenario runs once per script and is cached for the session, so the suite
spends its time on assertions rather than on re-spawning interpreters.
"""
from __future__ import annotations

import pytest

from conftest import all_scripts, run_script
from contract import (
    CONTRACT_EXIT_CODES, DEVICE_OR_NETWORK_BOUND, JSON_REQUIRED_KEYS,
    JSON_RUNNABLE, execution_refusal, has_option, missing_input_args,
    parse_leading_json,
)

pytestmark = pytest.mark.cli

SCRIPTS = all_scripts()
BAD_FLAG = "--zzz-not-a-real-flag"

HELP_TIMEOUT = 60
SCENARIO_TIMEOUT = 12


def why(name):
    if name in DEVICE_OR_NETWORK_BOUND:
        return " (device/network bound: it may legitimately block)"
    return ""


def require_returned(result, what):
    if result.timed_out:
        pytest.xfail("%s did not return within %ss%s; there is no exit code to check"
                     % (what, SCENARIO_TIMEOUT, why(result.argv[1])))
    if result.returncode not in CONTRACT_EXIT_CODES:
        pytest.fail("%s returned %r, outside the 0/1/2/3/4 contract vocabulary"
                    % (what, result.returncode))


def expect_exit(result, expected, what):
    """Pass when the measured code matches; otherwise record it as an xfail."""
    require_returned(result, what)
    if result.returncode != expected:
        pytest.xfail("%s: contract says exit %d, measured %d%s"
                     % (what, expected, result.returncode, why(result.argv[1])))


# --------------------------------------------------------------------------- #
# one cached run per script per scenario
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def help_results():
    return {n: run_script(n, ["--help"], timeout=HELP_TIMEOUT) for n in SCRIPTS}


@pytest.fixture(scope="session")
def badflag_results():
    return {n: run_script(n, [BAD_FLAG], timeout=SCENARIO_TIMEOUT) for n in SCRIPTS}


@pytest.fixture(scope="session")
def empty_results():
    """Bare invocations, for the scripts that may be run at all.

    Device-bound scripts are excluded here too: their no-argument path is exactly
    where several of them start doing device work (`usb_net_proxy.py` did not
    return within 20 s when probed by hand), and this suite does not touch a device.
    """
    return {n: run_script(n, [], timeout=SCENARIO_TIMEOUT) for n in SCRIPTS
            if n not in DEVICE_OR_NETWORK_BOUND}


@pytest.fixture(scope="session")
def missing_results(help_results):
    """Argument-complete runs against a missing file, for the scripts that may be run at all.

    Device-bound scripts are skipped here rather than executed and timed out: on
    the host this harness was written on, `adb devices` reported an online device,
    so running them would have touched real hardware.
    """
    results = {}
    for name in SCRIPTS:
        if name in DEVICE_OR_NETWORK_BOUND:
            continue
        args = missing_input_args(help_results[name].output)
        if args is None:
            continue
        results[name] = run_script(name, args, timeout=SCENARIO_TIMEOUT)
    return results


# --------------------------------------------------------------------------- #
# 1. --help
# --------------------------------------------------------------------------- #
class TestHelp:
    @pytest.mark.parametrize("name", SCRIPTS)
    def test_help_never_crashes(self, name, help_results):
        """Hard assertion: an uncaught traceback from --help is a defect, not a drift."""
        result = help_results[name]
        assert not result.timed_out, "--help did not return for %s" % name
        assert not result.has_traceback, result.output[-2000:]

    @pytest.mark.parametrize("name", SCRIPTS)
    def test_help_prints_something(self, name, help_results):
        assert help_results[name].output.strip(), "--help printed nothing"

    @pytest.mark.parametrize("name", SCRIPTS)
    def test_help_exits_zero(self, name, help_results):
        expect_exit(help_results[name], 0, "%s --help" % name)


# --------------------------------------------------------------------------- #
# 2. unknown flag
# --------------------------------------------------------------------------- #
class TestUnknownFlag:
    @pytest.mark.parametrize("name", SCRIPTS)
    def test_unknown_flag_is_never_success(self, name, badflag_results):
        result = badflag_results[name]
        require_returned(result, "%s %s" % (name, BAD_FLAG))
        assert result.returncode != 0, (
            "an unknown flag was reported as success:\n%s" % result.output[-2000:])

    @pytest.mark.parametrize("name", SCRIPTS)
    def test_unknown_flag_exits_two(self, name, badflag_results):
        expect_exit(badflag_results[name], 2, "%s %s" % (name, BAD_FLAG))


# --------------------------------------------------------------------------- #
# 3a. empty invocation
# --------------------------------------------------------------------------- #
class TestEmptyInvocation:
    @pytest.mark.parametrize("name", SCRIPTS)
    def test_no_arguments_is_a_usage_error(self, name, help_results, empty_results):
        """Only applies when the script actually requires arguments.

        A script whose usage block has no positional and no required option may
        legitimately succeed with no arguments; demanding exit 2 from those would
        invent a rule the contract does not state. Device-bound scripts are not run
        at all -- see `contract.execution_refusal`.
        """
        refusal = execution_refusal(name, "a bare invocation", help_results[name].output)
        if refusal:
            pytest.skip(refusal)
        expect_exit(empty_results[name], 2, "%s with no arguments" % name)


# --------------------------------------------------------------------------- #
# 3b. bad input
# --------------------------------------------------------------------------- #
class TestMissingInput:
    @pytest.mark.parametrize("name", SCRIPTS)
    def test_missing_input_file_is_a_usage_error(self, name, help_results, missing_results):
        if name not in missing_results:
            pytest.skip(execution_refusal(name, "a missing input", help_results[name].output)
                        or "not executed for %s" % name)
        expect_exit(missing_results[name], 2, "%s with a missing input" % name)

    @pytest.mark.parametrize("name", SCRIPTS)
    def test_missing_input_is_never_success(self, name, help_results, missing_results):
        if name not in missing_results:
            pytest.skip(execution_refusal(name, "a missing input", help_results[name].output)
                        or "not executed for %s" % name)
        result = missing_results[name]
        require_returned(result, "%s with a missing input" % name)
        assert result.returncode != 0, (
            "a missing input was reported as success:\n%s" % result.output[-2000:])

    @pytest.mark.parametrize("name", SCRIPTS)
    def test_bad_input_reports_cleanly_not_as_an_exception(self, name, help_results,
                                                           missing_results):
        """A missing file is an expected failure mode; it must not escape as an exception.

        Several scripts currently let `FileNotFoundError` propagate. Each is
        recorded here as an xfail naming the exception; the fix belongs to that
        script's owner, not to this suite.
        """
        if name not in missing_results:
            pytest.skip(execution_refusal(name, "a missing input", help_results[name].output)
                        or "not executed for %s" % name)
        result = missing_results[name]
        require_returned(result, "%s with a missing input" % name)
        if result.has_traceback:
            tail = [l for l in result.output.splitlines() if l.strip()]
            pytest.xfail("%s reports a missing input by letting an exception escape "
                         "instead of exiting 2 cleanly: %s"
                         % (name, (tail[-1] if tail else "uncaught exception")[:140]))


# --------------------------------------------------------------------------- #
# 4. the --json contract
# --------------------------------------------------------------------------- #
def json_capable(help_results):
    return sorted(n for n, r in help_results.items() if has_option(r.output, "--json"))


def test_json_capable_scripts_are_discoverable(help_results):
    found = json_capable(help_results)
    assert found, "no script advertises --json; the discovery method is broken"


@pytest.mark.parametrize("name,args", sorted(JSON_RUNNABLE.items()))
def test_json_output_is_parseable_and_states_a_status(name, args):
    result = run_script(name, args, timeout=120)
    require_returned(result, "%s %s" % (name, " ".join(args)))
    doc = parse_leading_json(result.stdout)
    assert doc is not None, (
        "%s %s printed no parseable JSON document:\n%s"
        % (name, " ".join(args), result.output[-2000:]))
    missing = [k for k in JSON_REQUIRED_KEYS if not isinstance(doc, dict) or k not in doc]
    if missing:
        present = sorted(doc) if isinstance(doc, dict) else type(doc).__name__
        pytest.xfail("%s --json does not carry %s; top-level keys are %s"
                     % (name, missing, present))


@pytest.mark.parametrize("name", SCRIPTS)
def test_json_capable_but_unreachable_scripts_are_named(name, help_results):
    """Coverage honesty: a --json script is either exercised here or explicitly not."""
    if not has_option(help_results[name].output, "--json"):
        pytest.skip("%s does not advertise --json" % name)
    if name in JSON_RUNNABLE:
        return
    pytest.skip("%s advertises --json, but reaching that path needs a device or a "
                "sample; the gap is listed in EXTENSION-test-harness.md" % name)


# --------------------------------------------------------------------------- #
# 5. the exit-code vocabulary
# --------------------------------------------------------------------------- #
class TestExitCodeVocabulary:
    @pytest.mark.parametrize("name", SCRIPTS)
    def test_observed_codes_stay_inside_the_vocabulary(self, name, help_results,
                                                       badflag_results):
        for label, result in (("--help", help_results[name]),
                              (BAD_FLAG, badflag_results[name])):
            if result.returncode is not None:
                assert result.returncode in CONTRACT_EXIT_CODES, (
                    "%s %s returned %r" % (name, label, result.returncode))
            assert result.returncode is None or result.returncode >= 0, (
                "a negative code is a crash signal, not an exit status: %s %s"
                % (name, label))
