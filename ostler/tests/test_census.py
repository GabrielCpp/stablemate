"""The census tells an unrun checker from a clean one; nothing else can."""

from __future__ import annotations

import types

from ostler import census


def _module() -> tuple[types.ModuleType, str]:
    """A stand-in for `doctor`: three codes, one per classification."""
    source = '''
class Finding:
    def __init__(self, severity, code, message=""):
        self.severity, self.code, self.message = severity, code, message

class Report:
    def __init__(self, findings, profile="full"):
        self.findings, self.profile = findings, profile

def _check_fires(f):
    f.append(Finding("error", "fires"))

def _check_clean(f):
    if False:
        f.append(Finding("warn", "clean"))

def _check_never_called(f):
    f.append(Finding("error", "unreachable"))

def run():
    f = []
    _check_fires(f)
    _check_clean(f)
    return Report(f)
'''
    module = types.ModuleType("fake_doctor")
    module.__file__ = "<fake_doctor>"
    code = compile(source, "<fake_doctor>", "exec")
    exec(code, module.__dict__)  # noqa: S102 - the source is the fixture, written above
    return module, source


def test_code_sites_reads_every_literal_code_and_its_enclosing_function(monkeypatch):
    module, source = _module()
    monkeypatch.setattr(census.inspect, "getsource", lambda _m: source)
    sites = census.code_sites(module)
    assert sites == {
        "fires": frozenset({"_check_fires"}),
        "clean": frozenset({"_check_clean"}),
        "unreachable": frozenset({"_check_never_called"}),
    }


def test_a_checker_that_ran_clean_is_not_reported_as_unreachable(monkeypatch):
    """The distinction the whole module exists for, and the one a grep cannot draw."""
    module, source = _module()
    monkeypatch.setattr(census.inspect, "getsource", lambda _m: source)
    monkeypatch.setattr(census.inspect, "getsourcefile", lambda _m: "<fake_doctor>")

    result = census.take_census(module.run, module)

    assert result.fired == frozenset({"fires"})
    assert result.dormant_clean == frozenset({"clean"})
    assert result.dormant_unreachable == frozenset({"unreachable"})
    assert result.profile == "full"


def test_an_unreachable_code_with_no_recorded_reason_is_the_finding():
    result = census.Census(
        fired=frozenset(), dormant_clean=frozenset(),
        dormant_unreachable=frozenset({"nobody-calls-me"}),
    )
    assert result.undeclared == frozenset({"nobody-calls-me"})
    assert "nobody-calls-me" in census.render(result)


def test_a_reason_for_a_code_that_now_fires_is_itself_a_finding():
    """A family wired back up must not leave its excuse behind to pre-waive the next one."""
    recorded = next(iter(census.DORMANT_UNREACHABLE))
    result = census.Census(
        fired=frozenset({recorded}), dormant_clean=frozenset(),
        dormant_unreachable=frozenset(),
    )
    assert recorded in result.stale


def test_the_real_registry_only_names_codes_doctor_actually_defines():
    """A rename upstream leaves a reason attached to nothing, which reads as coverage."""
    defined = census.code_sites().keys()
    assert not census.DORMANT_UNREACHABLE.keys() - defined
