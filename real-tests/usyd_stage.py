"""Collates and labels a USyd TBP raw-data export with 'collate folder'

The DICOM series and Siemens Biograph Vision raw data in the export are collated into
accessions labelled for XNAT, ``<PatientComments>.<PatientID>.<AccessionNumber>_combined``,
in ``<WORK_DIR>/TEST-STAGED``, which ``usyd_upload.py`` and ``usyd_check_upload.py``
read once it has been copied to the S3 bucket. Collate consumes its input, so each run
collates a hard-linked copy of the export, ``<WORK_DIR>/INBOX``, and the export itself
is left as it is.

This replaces the old 'sort' command, which also uploaded to S3. The 'transfer' command
that did that later has been removed, so copy the staged accessions to the bucket
yourself, e.g. with ``aws s3 sync``. Deidentification is its own stage, not run here.

Set ``USYD_TBP_DIR`` to run it on another copy of the export.
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

WORK_DIR = os.environ.get("USYD_TBP_DIR", "/Users/tclo7153/Data/TBP")
EXPORT = "VENTURE_P001_Galligas_Post-RT"

DATATYPES = [
    "medimage/dicom-series",
    "medimage/vnd.siemens.syngo-mi.vr20b.count-rate",
    "medimage/vnd.siemens.syngo-mi.vr20b.list-mode",
    "medimage/vnd.siemens.syngo-mi.vr20b.normalisation",
    "medimage/vnd.siemens.syngo-mi.vr20b.sinogram",
    "medimage/vnd.siemens.syngo-mi.vr20b.dynamic-sinogram-series",
    "medimage/vnd.siemens.syngo-mi.vr20b.parameterisation",
    "medimage/vnd.siemens.syngo-mi.vr20b.ct-spl",
    "medimage/vnd.siemens.syngo-mi.vr20b.physio",
]

logging.basicConfig(level=logging.DEBUG)

shutil.rmtree(f"{WORK_DIR}/TEST-STAGED", ignore_errors=True)
shutil.rmtree(f"{WORK_DIR}/INBOX", ignore_errors=True)
# The hard-linked copy is moved by collate, not the export
shutil.copytree(
    f"{WORK_DIR}/RAW-DATA-EXPORT/{EXPORT}",
    f"{WORK_DIR}/INBOX/{EXPORT}",
    copy_function=os.link,
)

result = runner.invoke(
    collate_cmd,
    [
        f"{WORK_DIR}/INBOX/{EXPORT}",
        f"{WORK_DIR}/TEST-STAGED",
        *(arg for datatype in DATATYPES for arg in ("--datatype", datatype)),
        # The raw data are collated by the same fields as the DICOM series
        "--accession",
        "StudyInstanceUID",
        "all",
        "--acquisition",
        "SeriesNumber",
        "all",
        "--resource",
        "ImageType[2:]",
        "medimage/vnd.siemens.syngo-mi.vr20b.raw-data",
        # The labels, which the 'sort' command gave
        "--project",
        "PatientComments",
        "--subject",
        "PatientID",
        "--session",
        "AccessionNumber",
        "--scan",
        "SeriesDescription",
        "--copy-mode",
        "hardlink_or_copy",
        "--logger",
        "stream",
        "info",
        "stdout",
        "--logger",
        "file",
        "debug",
        f"{WORK_DIR}/accessionflow-test-stage.log",
        "--additional-logger",
        "fileformats",
    ],
    catch_exceptions=False,
)


if result.exit_code != 0:
    print(result.output)
    print(show_cli_trace(result))
