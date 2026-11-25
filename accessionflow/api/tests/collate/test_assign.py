from pathlib import Path

import pytest
from fileformats.application import Json

from accessionflow.api.collate import (
    assign_labels,
    classify_paths,
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
    accession = _accession(tmp_path, PatientID="P01", visit="V1", desc="T1w")
    result = assign_labels(
        accession,
        LABEL_FIELDS,
        acquisition_field="desc",
        constant_labels={"project": "PROJ"},
        store_type="xnat",
    )
    assert result is accession
    assert accession.labels == {"project": "PROJ", "subject": "P01", "session": "V1"}
    assert accession.name == "PROJ.P01.V1"
    assert accession.store_type == "xnat"
    assert accession.acquisitions["scan"].type == "T1w"


def test_assign_labels_missing_field_raises(tmp_path: Path) -> None:
    accession = _accession(tmp_path, PatientID="P01")
    with pytest.raises(LabelsNotAssignedError, match=r"\['visit'\]"):
        assign_labels(accession, LABEL_FIELDS, constant_labels={"project": "PROJ"})
