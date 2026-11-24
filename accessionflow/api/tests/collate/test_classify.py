import pytest
from fileformats.application import Json, Zip
from fileformats.generic import DirectoryOf
from fileformats.medimage import DicomSeries
from fileformats.text import Csv

from accessionflow.api.collate import check_datatypes


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
