"""The base class of the steps of a stage (see ``prefect-migration-docs/ROADMAP.md``,
design principle 12)"""

import abc
import typing as ty
from contextlib import ExitStack
from types import TracebackType

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

    A step that creates something a run must dispose of, e.g. a directory, overrides
    `clean_up`, which takes the run data that names it and the error the run raised,
    if any. The caller registers each step's clean-up on a `contextlib.ExitStack` with
    `register_clean_up` as it calls `act`: before `act` if the clean-up's arguments are
    known by then, so that an `act` that raises part way is cleaned up too, otherwise
    straight after. The stack runs the clean-ups in reverse order when the run ends,
    however it ends.
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

    def clean_up(self, *args: ty.Any, **kwargs: ty.Any) -> None:
        """Disposes of what `act` created once the run has ended, given the run data
        that names it and, as the keyword ``error``, the error the run raised (`None`
        if it didn't). An interrupt (e.g. a `KeyboardInterrupt`) is passed too, so each
        step decides what it leaves in place. Nothing by default.

        It doesn't need the configuration checked, and doesn't check it. With nothing
        to clean up, e.g. if `act` didn't get far or it has been cleaned up already, it
        does nothing, so it can be called again. It never handles the run's error,
        which is raised once every clean-up has run
        """

    def register_clean_up(
        self, stack: ExitStack, *args: ty.Any, **kwargs: ty.Any
    ) -> None:
        """Registers `clean_up` on the stack, to be called with the arguments, and the
        error the run raised as ``error``, when the stack exits

        Parameters
        ----------
        stack : ExitStack
            the stack of the run's clean-ups
        *args, **kwargs
            the arguments `clean_up` is called with
        """

        def exit_(
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            self.clean_up(*args, error=exc, **kwargs)
            return False  # the run's error is raised

        stack.push(exit_)

    @abc.abstractmethod
    def act(self, *args: ty.Any, **kwargs: ty.Any) -> ty.Any:
        """Does the step's work on one run's data. It never checks the configuration:
        the caller calls `check_configuration` first"""
