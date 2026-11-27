"""Tests of the base class of the steps (see ``prefect-migration-docs/ROADMAP.md``,
design principle 12)"""

import pickle
import typing as ty

import attrs
import pytest

from accessionflow.api.step import Step


@attrs.define
class _Doubling(Step):
    """A step whose act needs a value its check derives"""

    factor: int
    checks: list[int] = attrs.field(factory=list)
    _derived: int | None = attrs.field(default=None, init=False, repr=False)

    def _check_configuration(self) -> None:
        if self.factor < 0:
            raise ValueError("factor can't be negative")
        self.checks.append(self.factor)
        self._derived = self.factor * 2

    def act(self, value: int) -> int:
        self._require_checked()
        return ty.cast(int, self._derived) * value


@attrs.define
class _Unchecked(Step):
    """A step with no configuration checks, which acts without them"""

    def act(self) -> str:
        return "done"


def test_check_configuration_checks_once() -> None:
    step = _Doubling(3)
    step.check_configuration()
    step.check_configuration()
    assert step.checks == [3]
    assert step.act(5) == 30


def test_invalid_configuration_raises_from_the_check() -> None:
    step = _Doubling(-1)
    with pytest.raises(ValueError, match="negative"):
        step.check_configuration()
    # It wasn't checked, so it still refuses to act
    with pytest.raises(RuntimeError, match="check_configuration"):
        step.act(5)


def test_act_never_checks_the_configuration() -> None:
    step = _Doubling(3)
    with pytest.raises(RuntimeError, match=r"_Doubling.check_configuration\(\)"):
        step.act(5)
    assert step.checks == []


def test_a_step_without_checks_acts_unchecked() -> None:
    assert _Unchecked().act() == "done"


def test_a_checked_step_pickles_with_what_it_derived() -> None:
    step = _Doubling(3)
    step.check_configuration()
    copy = pickle.loads(pickle.dumps(step))
    assert copy.act(5) == 30
    assert copy.checks == [3]  # not checked again


def test_step_is_abstract() -> None:
    with pytest.raises(TypeError):
        Step()  # type: ignore[abstract]
