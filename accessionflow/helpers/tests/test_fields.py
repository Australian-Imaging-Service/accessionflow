from pathlib import Path
from unittest.mock import patch

from fileformats.generic import File
from fileformats.testing import MyFormat

from accessionflow.api.select_fields_api import select_fields
from accessionflow.helpers.arg_types import IDSpec
from accessionflow.helpers.fields import Fields
from accessionflow.model.accession import Accession
from accessionflow.model.acquisition import Acquisition


def _staged_session(input_dir: Path) -> tuple[Accession, Path]:
    source_path = input_dir.parent / "source.my"
    source_path.write_text("deidentified source")
    report_path = input_dir.parent / "report.txt"
    report_path.write_text("session report")

    session = Accession(
        uid="uid",
        labels={"project": "PROJECT", "subject": "SUBJECT", "session": "SESSION"},
        acquisitions=[
            Acquisition(
                id="1",
                type="CT",
                resources={"SOURCE": MyFormat(source_path)},
            )
        ],
    )
    session.metadata["session-field"] = "preserved"
    session.acquisitions["1"].metadata["scan-field"] = "preserved"
    session.acquisitions["1"].resources["SOURCE"].metadata["resource-field"] = (
        "preserved"
    )
    session.add_session_resource("REPORT", File(report_path))
    _, session_dir = session.save(input_dir)
    return session, session_dir


def test_fields_writes_fields_file(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _staged_session(input_dir)

    errors = select_fields(
        input_dir=input_dir,
        output_dir=output_dir,
        extract={"preserved_field": IDSpec("session-field")},
    )

    assert errors == []
    session_dir = output_dir / "PROJECT.SUBJECT.SESSION"
    assert (session_dir / Fields.FNAME).exists()
    assert dict(Accession.load(session_dir).fields) == {"preserved_field": "preserved"}


def test_fields_preserves_resources_and_metadata(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _session, source_dir = _staged_session(input_dir)

    errors = select_fields(
        input_dir=input_dir,
        output_dir=output_dir,
        extract={"preserved_field": IDSpec("session-field")},
    )

    assert errors == []
    assert source_dir.exists(), "field extraction removed its input without being asked"
    out = Accession.load(output_dir / "PROJECT.SUBJECT.SESSION")
    scan = out.acquisitions["1"]
    assert scan.type == "CT"
    assert set(scan.resources) == {"SOURCE"}
    assert scan.resources["SOURCE"].fileset.fspath.read_text() == (
        "deidentified source"
    )
    assert out.metadata["session-field"] == "preserved"
    assert scan.metadata["scan-field"] == "preserved"
    assert scan.resources["SOURCE"].metadata["resource-field"] == "preserved"
    assert out.session_resources["REPORT"].fileset.fspath.read_text() == (
        "session report"
    )
    assert dict(Accession.load(source_dir).fields) == {}


def test_fields_preserves_existing_fields(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    session, _source_dir = _staged_session(input_dir)
    session.fields["existing_field"] = "from-upstream"
    session.save(input_dir)

    errors = select_fields(
        input_dir=input_dir,
        output_dir=output_dir,
        extract={"preserved_field": IDSpec("session-field")},
    )

    assert errors == []
    out = Accession.load(output_dir / "PROJECT.SUBJECT.SESSION")
    assert dict(out.fields) == {
        "existing_field": "from-upstream",
        "preserved_field": "preserved",
    }


def test_fields_skips_unresolvable_mapping(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _staged_session(input_dir)

    errors = select_fields(
        input_dir=input_dir,
        output_dir=output_dir,
        extract={
            "preserved_field": IDSpec("session-field"),
            "missing_field": IDSpec("missing-key"),
        },
    )

    assert errors == []
    out = Accession.load(output_dir / "PROJECT.SUBJECT.SESSION")
    assert dict(out.fields) == {"preserved_field": "preserved"}


def test_fields_does_not_finalize_output_when_extraction_fails(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    _session, source_dir = _staged_session(input_dir)

    with patch.object(Fields, "extract", side_effect=RuntimeError("extraction failed")):
        errors = select_fields(
            input_dir=input_dir,
            output_dir=output_dir,
            extract={"preserved_field": IDSpec("session-field")},
        )

    assert len(errors) == 1
    assert "extraction failed" in errors[0]
    assert not (output_dir / "PROJECT.SUBJECT.SESSION").exists()
    assert source_dir.exists()


def _staged_session_with_fields(input_dir: Path) -> Path:
    _, session_dir = _staged_session(input_dir)
    session = Accession.load(session_dir)
    session.fields["site"] = "SYDNEY"
    session.save(input_dir)
    assert dict(Accession.load(session_dir).fields) == {"site": "SYDNEY"}
    return session_dir


def test_new_empty_keeps_fields(tmp_path: Path) -> None:
    """An accession's fields belong to the accession, not to its acquisitions, so a
    copy without the acquisitions keeps them"""
    session_dir = _staged_session_with_fields(tmp_path / "input")
    session = Accession.load(session_dir)
    empty = session.new_empty()
    assert not empty.acquisitions
    assert dict(empty.fields) == {"site": "SYDNEY"}
    # The copy has its own fields, so changing them leaves the original's alone
    empty.fields["extra"] = "value"
    assert dict(session.fields) == {"site": "SYDNEY"}


def test_package_keeps_fields(tmp_path: Path) -> None:
    from accessionflow.api import package

    _staged_session_with_fields(tmp_path / "input")
    errors = package(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        source_datatype=MyFormat,
        output_resources={"COPY": (MyFormat, {})},
    )
    assert errors == []
    out = Accession.load(tmp_path / "output" / "PROJECT.SUBJECT.SESSION")
    assert dict(out.fields) == {"site": "SYDNEY"}


def test_deidentify_keeps_fields(tmp_path: Path) -> None:
    from accessionflow.api import deidentify
    from accessionflow.api.tests.test_deidentify import SHIPPED_RECIPES_DIR

    _staged_session_with_fields(tmp_path / "input")
    errors = deidentify(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        recipe_dir=SHIPPED_RECIPES_DIR,
    )
    assert errors == []
    out = Accession.load(tmp_path / "output" / "PROJECT.SUBJECT.SESSION")
    assert dict(out.fields) == {"site": "SYDNEY"}


def test_label_keeps_fields(tmp_path: Path) -> None:
    from accessionflow.api import label

    source = tmp_path / "source.my"
    source.write_text("data")
    collated = Accession(
        uid="1.2.3",
        acquisitions=[
            Acquisition(id="1", type="CT", resources={"SOURCE": MyFormat(source)})
        ],
    )
    collated.metadata.update({"P": "PROJECT", "S": "SUBJECT", "E": "SESSION"})
    collated.fields["site"] = "SYDNEY"
    collated.save(tmp_path / "input")
    errors = label(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        label_fields={"project": "P", "subject": "S", "session": "E"},
        store_type="xnat",
    )
    assert errors == []
    out = Accession.load(tmp_path / "output" / "PROJECT.SUBJECT.SESSION")
    assert dict(out.fields) == {"site": "SYDNEY"}


def test_attach_keeps_fields(tmp_path: Path) -> None:
    from accessionflow.api import attach

    _staged_session_with_fields(tmp_path / "input")
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    (extra_dir / "5_LISTMODE_EXTRA.txt").write_text("attached")
    errors = attach(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        datatype=File,
        glob=str(extra_dir / "*.txt"),
        identity_pattern=r".*/(?P<id>\d+)_(?P<type>[A-Z]+)_(?P<resource>[A-Z]+)\.txt",
    )
    assert errors == []
    out = Accession.load(tmp_path / "output" / "PROJECT.SUBJECT.SESSION")
    assert "EXTRA" in out.acquisitions["5"].resources
    assert dict(out.fields) == {"site": "SYDNEY"}
