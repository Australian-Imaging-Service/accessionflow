"""Tests of the base class of the steps (see ``prefect-migration-docs/ROADMAP.md``,
design principle 12)"""

import pickle
import typing as ty
from contextlib import ExitStack

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


@attrs.define
class _Recording(Step):
    """A step whose clean-up records what it was called with"""

    name: str
    calls: list[tuple[str, str, BaseException | None]]
    fail: bool = False

    def act(self) -> None:
        pass

    def clean_up(self, value: str, error: BaseException | None = None) -> None:
        self.calls.append((self.name, value, error))
        if self.fail:
            raise OSError(f"{self.name} couldn't clean up")


def test_default_clean_up_does_nothing() -> None:
    _Unchecked().clean_up("anything", error=ValueError("x"))


def test_clean_ups_run_in_reverse_order_without_an_error() -> None:
    calls: list[tuple[str, str, BaseException | None]] = []
    with ExitStack() as stack:
        _Recording("first", calls).register_clean_up(stack, "a")
        _Recording("second", calls).register_clean_up(stack, "b")
        assert calls == []
    assert calls == [("second", "b", None), ("first", "a", None)]


def test_clean_ups_get_the_error_which_is_raised() -> None:
    calls: list[tuple[str, str, BaseException | None]] = []
    error = ValueError("failed")
    with pytest.raises(ValueError, match="failed"):
        with ExitStack() as stack:
            _Recording("first", calls).register_clean_up(stack, "a")
            _Recording("second", calls).register_clean_up(stack, "b")
            raise error
    assert calls == [("second", "b", error), ("first", "a", error)]


def test_a_clean_up_runs_after_another_raises() -> None:
    calls: list[tuple[str, str, BaseException | None]] = []
    with pytest.raises(OSError, match="second couldn't") as raised:
        with ExitStack() as stack:
            _Recording("first", calls).register_clean_up(stack, "a")
            _Recording("second", calls, fail=True).register_clean_up(stack, "b")
            raise ValueError("failed")
    assert [name for name, _, _ in calls] == ["second", "first"]
    # The run's error is kept as the clean-up's context
    assert isinstance(raised.value.__context__, ValueError)
