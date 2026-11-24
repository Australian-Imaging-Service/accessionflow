import pytest
from fileformats.application import Json, Zip
from fileformats.core import FileSet
from fileformats.generic import Directory, DirectoryOf
from fileformats.medimage import DicomSeries
from fileformats.text import Csv

from accessionflow.api.collate import RecursionPlan, check_datatypes, plan_recursion


def test_check_datatypes_distinct_passes() -> None:
    check_datatypes([DicomSeries], [Json, Zip])
    check_datatypes([DicomSeries, Json])


def test_check_datatypes_overlap_names_only_overlapping_sorted() -> None:
    with pytest.raises(ValueError, match="listed for both") as excinfo:
        check_datatypes([DicomSeries, Json], [Json, Zip, DicomSeries])
    message = str(excinfo.value)
    assert message.endswith("['application/json', 'medimage/dicom-series']")
    assert "zip" not in message


def test_check_datatypes_parametrised_types() -> None:
    check_datatypes([DirectoryOf[Json]], [DirectoryOf[Csv]])
    with pytest.raises(ValueError, match="listed for both"):
        check_datatypes([DirectoryOf[Json]], [DirectoryOf[Json]])


@pytest.mark.parametrize(
    "datatypes, ignore_datatypes, recursive, expected",
    [
        ([DicomSeries], [], False, (False, [])),
        # the generic types are only rejected with recursion
        ([Directory], [], False, (False, [])),
        # recursion over files only: bare directories are ignored
        ([DicomSeries], [Json], True, (False, [Json, Directory])),
        # a directory format, wanted or ignored, makes the walk prune on a match
        ([DirectoryOf[Json]], [], True, (True, [])),
        ([Json], [DirectoryOf[Csv]], True, (True, [DirectoryOf[Csv]])),
        ([DicomSeries], [Directory], True, (True, [Directory])),
    ],
)
def test_plan_recursion(
    datatypes: list[type[FileSet]],
    ignore_datatypes: list[type[FileSet]],
    recursive: bool,
    expected: tuple[bool, list[type[FileSet]]],
) -> None:
    assert plan_recursion(datatypes, ignore_datatypes, recursive) == expected


@pytest.mark.parametrize(
    "generic, name", [(Directory, "generic/directory"), (FileSet, "core/file-set")]
)
def test_plan_recursion_rejects_generic_types(
    generic: type[FileSet], name: str
) -> None:
    with pytest.raises(ValueError, match="generic/directory") as excinfo:
        plan_recursion([Json, generic], recursive=True)
    assert f"'{name}'" in str(excinfo.value)


def test_plan_recursion_doesnt_change_its_input() -> None:
    ignore_datatypes = [Json]
    plan = plan_recursion([DicomSeries], ignore_datatypes, recursive=True)
    assert ignore_datatypes == [Json]
    assert plan.ignore_datatypes is not ignore_datatypes


def test_recursion_plan_fields() -> None:
    plan = plan_recursion([DirectoryOf[Json]], recursive=True)
    assert isinstance(plan, RecursionPlan)
    recurse_into_dirs, ignore_datatypes = plan
    assert plan.recurse_into_dirs is recurse_into_dirs is True
    assert plan.ignore_datatypes == ignore_datatypes == []
