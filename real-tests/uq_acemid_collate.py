"""Collates and labels the UQ ACEMID test export with 'collate folder'

The export in ``<WORK_DIR>/input`` (dermoscopy images, Canfield whole-body analysis and
DexiData directories, and the dermoscopy metadata table) is collated into labelled
accessions, ``ACEMID.<SubjectID>.<SubjectID>_<CaptureDate>_combined``, in
``<WORK_DIR>/collated``. Collate consumes its input, so each run collates a hard-linked
copy of the export, ``<WORK_DIR>/inbox``, and the export itself is left as it is.

Set ``UQ_ACEMID_DIR`` to run it on another copy of the export.
"""

import logging
import os
import shutil
import traceback

import click
from click.testing import CliRunner

from accessionflow.sources.folder.cli import collate_cmd


def show_cli_trace(result: click.testing.Result) -> str:
    """Show the exception traceback from CLIRunner results"""
    assert result.exc_info is not None
    exc_type, exc, tb = result.exc_info
    return "".join(traceback.format_exception(exc_type, value=exc, tb=tb))


runner = CliRunner()

WORK_DIR = os.environ.get("UQ_ACEMID_DIR", "/Users/tclo7153/Data/ACEMID/uq-test")

logging.basicConfig(level=logging.DEBUG)

shutil.rmtree(f"{WORK_DIR}/collated", ignore_errors=True)
shutil.rmtree(f"{WORK_DIR}/inbox", ignore_errors=True)
# The hard-linked copy is moved by collate, not the export
shutil.copytree(f"{WORK_DIR}/input", f"{WORK_DIR}/inbox", copy_function=os.link)

result = runner.invoke(
    collate_cmd,
    [
        f"{WORK_DIR}/inbox",
        f"{WORK_DIR}/collated",
        "--recursive",
        "--datatype",
        "image/png",
        "--datatype",
        "image/jpeg",
        "--datatype",
        "medimage/vnd.canfield.whole-body-analysis-dir",
        "--datatype",
        "medimage/vnd.canfield.dexi-data-dir",
        "--exclude-path",
        "*/*/*/*.png",
        "--exclude-path",
        "*/*/*/*.jpg",
        "--allow-unrecognised",
        ".*",
        "--accession",
        "{subject_uid}_{CaptureDate:%Y%m%d}",
        "all",
        "--acquisition",
        "dermoscopy-{LesionID}",
        "image/png|image/jpeg",
        "--acquisition",
        "dexi-{CaptureTime}",
        "medimage/vnd.canfield.dexi-data-dir",
        "--acquisition",
        "analysis-{CaptureTime}",
        "medimage/vnd.canfield.whole-body-analysis-dir",
        "--resource",
        "CaptureDevice",
        "image/png|image/jpeg",
        "--resource",
        "__datatype__",
        "medimage/vnd.canfield.whole-body-analysis-dir|medimage/vnd.canfield.dexi-data-dir",
        "--on-resource-clash",
        "merge",
        "image/png|image/jpeg",
        "--path-metadata-regex",
        r".*/(?P<subject_uid>[\w-]+)/(?P<filename>[\w-]+\.(?:png|jpe?g))",
        "image/png|image/jpeg",
        "--path-metadata-regex",
        r".*/(?P<subject_uid>[\w-]+)/(?P<CaptureDate>\d{8})(?P<CaptureTime>\d+)/analysis",
        "medimage/vnd.canfield.whole-body-analysis-dir",
        "--path-metadata-regex",
        r".*/(?P<subject_uid>[\w-]+)/(?P<CaptureDate>\d{8})(?P<CaptureTime>\d+)/DexiData.*",
        "medimage/vnd.canfield.dexi-data-dir",
        "--metadata-table",
        f"{WORK_DIR}/input/Dermoscopy/LesionDermoscopyData_20260805155613.csv",
        "fileset[image/png|image/jpeg]",
        'ImagePath==HYPERLINK("{subject_uid}/{filename}")',
        # The labels, which the 'label' stage used to give the collated accessions
        "--subject",
        "SubjectID",
        "--session",
        "{SubjectID}_{CaptureDate:%Y%m%d}",
        "--constant-project-id",
        "ACEMID",
    ],  # ACFLOW_DIR
    catch_exceptions=False,
)


if result.exit_code != 0:
    print(result.output)
    print(show_cli_trace(result))
