"""The base class of the steps of a stage (see ``prefect-migration-docs/ROADMAP.md``,
design principle 12)"""

import abc
import typing as ty

import attrs

__all__ = ["Step"]


@attrs.define
class Step(abc.ABC):
    """A step of a stage, made with its configuration, e.g. the datatypes to collate

    The caller checks the configuration of every step of a run with
    `check_configuration` before any step acts, so that a run with an invalid
    configuration fails without creating, moving or deleting anything (principle 12).
    Then it runs each step with `act`, which takes the run's data, e.g. the claimed
    files, and never checks the configuration itself. A step whose `act` needs values
    that the check derives from the configuration, e.g. the recursion plan, refuses to
    act if it hasn't been checked.

    A subclass is an ``attrs.define`` class whose fields are its configuration. It
    keeps what it derives from the configuration in private ``init=False`` fields,
    sets them in `_check_configuration`, and implements `act`. Steps pickle, with
    their derived fields, so a configured step can be passed to a task (principle 8).
    """

    _checked: bool = attrs.field(default=False, init=False, repr=False, eq=False)

    def check_configuration(self) -> None:
        """Checks the configuration, and derives what `act` needs from it. Only the
        first call checks. Nothing is changed on disk

        Raises
        ------
        ValueError
            if the configuration is invalid
        """
        if not self._checked:
            self._check_configuration()
            self._checked = True

    def _check_configuration(self) -> None:
        """The step's own checks, and anything derived from the configuration that
        `act` uses. None by default"""

    def _require_checked(self) -> None:
        """Refuses to act on a configuration that hasn't been checked. It doesn't
        check the configuration itself

        Raises
        ------
        RuntimeError
            if `check_configuration` hasn't been called
        """
        if not self._checked:
            raise RuntimeError(
                f"{type(self).__name__}.check_configuration() must be called before "
                "act()"
            )

    @abc.abstractmethod
    def act(self, *args: ty.Any, **kwargs: ty.Any) -> ty.Any:
        """Does the step's work on one run's data. It never checks the configuration:
        the caller calls `check_configuration` first"""
