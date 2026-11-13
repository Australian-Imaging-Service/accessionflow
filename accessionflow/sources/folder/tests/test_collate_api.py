import re

import pytest
from fileformats.generic import File
from fileformats.medimage import DicomSeries

from accessionflow.helpers.arg_types import PathMetadataPattern, PathMetadataRegex
from accessionflow.sources.folder.api.collate_api import (
    merge_path_metadata,
    path_metadata_pattern_to_regex,
)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        # Unanchored patterns match the trailing segments
        ("{cohort}", "/data/incoming/cohort-A", {"cohort": "cohort-A"}),
        (
            "{subject}/{session}/*.dcm",
            "/data/in/subj-01/ses-02/1.dcm",
            {"subject": "subj-01", "session": "ses-02"},
        ),
        # A placeholder can be part of a segment
        (
            "sub-{subject}_ses-{session}.nii.gz",
            "/x/sub-01_ses-a.nii.gz",
            {"subject": "01", "session": "a"},
        ),
        # Anchored patterns match the whole path
        ("/data/{site}/**/*.dcm", "/data/site1/a/b/1.dcm", {"site": "site1"}),
        # '**/' matches zero segments too
        ("/data/{site}/**/*.dcm", "/data/site1/1.dcm", {"site": "site1"}),
        ("{subject}/scan?.png", "/in/s1/scan1.png", {"subject": "s1"}),
        ("{subject}/[ab]*.png", "/in/s1/a1.png", {"subject": "s1"}),
        ("{subject}/[!ab]*.png", "/in/s1/c1.png", {"subject": "s1"}),
        # Escaped braces are literal
        ("{{{name}}}", "/in/{xyz}", {"name": "xyz"}),
        # A repeated field must have the same value
        ("{subject}/{subject}_*.png", "/in/s1/s1_t1.png", {"subject": "s1"}),
    ],
)
def test_path_metadata_pattern_matches(
    pattern: str, path: str, expected: dict[str, str]
) -> None:
    match = re.match(path_metadata_pattern_to_regex(pattern), path)
    assert match is not None
    assert match.groupdict() == expected


@pytest.mark.parametrize(
    ("pattern", "path"),
    [
        # '*' and '{name}' don't cross segments
        ("/in/{subject}/*.dcm", "/in/s1/a/1.dcm"),
        ("/in/{subject}", "/in/s1/a"),
        # Anchored at the start, and at the end
        ("/data/{site}", "/other/data/site1"),
        ("{cohort}/*.dcm", "/data/cohort-A/1.dcm/extra"),
        # Other characters are literal, not regex syntax
        ("{subject}.dcm", "/in/s1xdcm"),
        ("{subject}/[!ab]*.png", "/in/s1/a1.png"),
        ("{subject}/{subject}_*.png", "/in/s1/s2_t1.png"),
    ],
)
def test_path_metadata_pattern_no_match(pattern: str, path: str) -> None:
    assert re.match(path_metadata_pattern_to_regex(pattern), path) is None


@pytest.mark.parametrize(
    "pattern", ["{sub-ject}/*", "{}/*", "{1st}/*", "{subject/*", "subject}/*"]
)
def test_path_metadata_pattern_invalid(pattern: str) -> None:
    with pytest.raises(ValueError):
        path_metadata_pattern_to_regex(pattern)


def test_merge_path_metadata() -> None:
    merged = merge_path_metadata(
        [PathMetadataPattern("{cohort}", "medimage/dicom-series")],
        [PathMetadataRegex(r".*/(?P<name>[^/]+)$", "generic/file")],
    )
    assert merged == [
        PathMetadataRegex(r"(?:.*/)?(?P<cohort>[^/]+)$", DicomSeries),
        PathMetadataRegex(r".*/(?P<name>[^/]+)$", File),
    ]
