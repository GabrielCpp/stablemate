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


def _colliding_module() -> tuple[types.ModuleType, str]:
    """Two checkers, each with a nested helper of the same name — `doctor` has three.

    The shape is not contrived: a cycle walk wants a recursive `visit`, so every checker
    that walks a graph grows one, and they are siblings in different scopes rather than one
    shared helper. Only one of the two runs here.
    """
    source = '''
class Finding:
    def __init__(self, severity, code, message=""):
        self.severity, self.code, self.message = severity, code, message

class Report:
    def __init__(self, findings, profile="full"):
        self.findings, self.profile = findings, profile

def _check_fixture_cycles(f):
    def visit(seen):
        if seen:
            f.append(Finding("error", "fixture-cycle"))
    visit(False)

def _check_milestone_cycles(f):
    def visit(seen):
        if seen:
            f.append(Finding("error", "milestone-cycle"))
    visit(False)

def run():
    f = []
    _check_fixture_cycles(f)
    return Report(f)
'''
    module = types.ModuleType("fake_doctor")
    module.__file__ = "<fake_doctor>"
    exec(compile(source, "<fake_doctor>", "exec"), module.__dict__)  # noqa: S102 - the fixture above
    return module, source


def test_two_helpers_sharing_a_name_are_two_functions(monkeypatch):
    """A bare `__name__` is not an identity, and the join has to survive that.

    Keyed on the bare name, entering the fixture walk marked *both* `visit`s entered, and
    `milestone-cycle` — which only the milestone walk can emit — was reported reachable on a
    book with no milestones in it. That is the failure mode the census exists to prevent,
    produced by the census: a rule reported as enforced where it is not.
    """
    module, source = _colliding_module()
    monkeypatch.setattr(census.inspect, "getsource", lambda _m: source)
    monkeypatch.setattr(census.inspect, "getsourcefile", lambda _m: "<fake_doctor>")

    sites = census.code_sites(module)
    assert sites == {
        "fixture-cycle": frozenset({"_check_fixture_cycles.<locals>.visit"}),
        "milestone-cycle": frozenset({"_check_milestone_cycles.<locals>.visit"}),
    }

    result = census.take_census(module.run, module)
    assert result.dormant_clean == frozenset({"fixture-cycle"})
    assert result.dormant_unreachable == frozenset({"milestone-cycle"})
