from pathlib import Path

import pytest
from fileformats.application import Json

from accessionflow.api.collate import (
    apply_constant_fields,
    assign_labels,
    classify_paths,
    constant_label_fields,
    group_into_accessions,
)
from accessionflow.exceptions import LabelsNotAssignedError
from accessionflow.helpers.arg_types import IDSpec
from accessionflow.model.accession import Accession

LABEL_FIELDS = {"project": "project", "subject": "PatientID", "session": "visit"}


def _accession(tmp_path: Path, **metadata: str) -> Accession:
    path = tmp_path / "a.json"
    path.write_text("{}")
    (fileset,) = classify_paths([path], [Json])
    fileset.metadata.update({"sess": "s1", "name": "scan", **metadata})
    (accession,) = group_into_accessions([fileset], [IDSpec("sess")], [IDSpec("name")])
    return accession


def test_assign_labels(tmp_path: Path) -> None:
    accession = _accession(
        tmp_path, project="PROJ", PatientID="P01", visit="V1", desc="T1w"
    )
    result = assign_labels(
        accession, LABEL_FIELDS, acquisition_field="desc", store_type="xnat"
    )
    assert result is accession
    assert accession.labels == {"project": "PROJ", "subject": "P01", "session": "V1"}
    assert accession.name == "PROJ.P01.V1"
    assert accession.store_type == "xnat"
    assert accession.acquisitions["scan"].type == "T1w"


def test_assign_labels_missing_field_raises(tmp_path: Path) -> None:
    accession = _accession(tmp_path, project="PROJ", PatientID="P01")
    with pytest.raises(LabelsNotAssignedError, match=r"\['visit'\]"):
        assign_labels(accession, LABEL_FIELDS)


# constant_label_fields ------------------------------------------------------------


def test_constant_label_fields() -> None:
    label_fields = {"project": "StudyComments", "subject": "{PatientID}_{Site}"}
    fields, constants = constant_label_fields(
        label_fields, {"project": "PROJ", "subject": "S01"}
    )
    # Each constant level, even a format string, is labelled from the field named
    # after it
    assert fields == {"project": "project", "subject": "subject"}
    assert constants == {"project": "PROJ", "subject": "S01"}
    assert label_fields["project"] == "StudyComments"  # not changed


def test_constant_label_fields_without_constants() -> None:
    assert constant_label_fields(LABEL_FIELDS, {}) == (LABEL_FIELDS, {})


def test_constant_label_fields_unknown_level() -> None:
    with pytest.raises(ValueError, match=r"Constant labels \['site'\]"):
        constant_label_fields(LABEL_FIELDS, {"site": "X"})


def test_constant_labels_match_the_saved_metadata(tmp_path: Path) -> None:
    """A constant label is labelled from the metadata, so the accession's name and its
    metadata agree, while the field read from the files is kept"""
    path = tmp_path / "a.json"
    path.write_text("{}")
    (fileset,) = classify_paths([path], [Json])
    fileset.metadata.update(
        {"sess": "s1", "name": "scan", "StudyComments": "from the files"}
    )
    fields, constants = constant_label_fields(
        {"project": "StudyComments", "subject": "sess"}, {"project": "PROJ"}
    )
    apply_constant_fields([fileset], constants)
    (accession,) = group_into_accessions([fileset], [IDSpec("sess")], [IDSpec("name")])
    assign_labels(accession, fields)
    assert accession.name == "PROJ.s1"
    assert accession.metadata["project"] == "PROJ"
    assert accession.metadata["StudyComments"] == "from the files"
