"""The session-label upload mode must obey the same completeness rule.

XnatSessionOnlyListing sat outside the XnatSessionListing hierarchy as a duck-typed
sibling with its own copy of all_uploaded comparing resource LABELS, so fixing
the base class could not reach it.

The two modes differ only in how they FIND their session, by project and label
or by a global label search, so find_xnat_session is the only override and the
completeness rule has one implementation. The mode is selected on whether the
staging directory name contains a dot.
"""

import json
import typing as ty
from types import SimpleNamespace

import pytest

from accessionflow.stores.xnat.remotes import (
    XnatSessionListing,
    XnatSessionOnlyListing,
)

LOCAL = {f"slice{i}.dcm": f"digest{i}" for i in range(8)}


class FakeResponse:
    def __init__(self, body: ty.Any) -> None:
        self.status_code = 200
        self._body = body

    def json(self) -> ty.Any:
        return self._body


class FakeConnection:
    """Answers the REST reads of all_uploaded(): session 'SESSLABEL' (ID
    'XNAT_E1') holds one session-level resource, 'DICOM'."""

    def __init__(
        self,
        on_xnat: ty.Dict[str, str],
        found: bool = True,
        fields: ty.Optional[ty.Dict[str, ty.Any]] = None,
    ) -> None:
        self.on_xnat = on_xnat
        self.found = found
        self.fields = fields or {}

    def get_json(
        self, uri: str, query: ty.Optional[ty.Dict[str, str]] = None, headers=None
    ) -> ty.Any:
        rows: ty.List[ty.Dict[str, str]] = []
        if uri == "/data/experiments":
            if self.found:
                rows = [
                    {
                        "ID": "XNAT_E1",
                        "label": "SESSLABEL",
                        "xsiType": "xnat:petSessionData",
                    }
                ]
        elif uri == "/data/experiments/XNAT_E1/resources":
            rows = [
                {
                    "xnat_abstractresource_id": "7",
                    "label": "DICOM",
                    "element_name": "xnat:resourceCatalog",
                }
            ]
        elif uri != "/data/experiments/XNAT_E1/scans":
            raise AssertionError(f"unexpected GET {uri}")
        return {"ResultSet": {"Result": rows}}

    def get(self, uri: str) -> FakeResponse:
        if uri == "/data/experiments/XNAT_E1":
            return FakeResponse(
                {
                    "items": [
                        {
                            "children": [
                                {
                                    "field": "fields/field",
                                    "items": [
                                        {"data_fields": {"name": name, "field": value}}
                                        for name, value in self.fields.items()
                                    ],
                                }
                            ]
                        }
                    ]
                }
            )

        assert uri == "/data/experiments/XNAT_E1/resources/7/files", uri
        return FakeResponse(
            {
                "ResultSet": {
                    "Result": [
                        {"Name": n, "URI": f"{uri}/{n}", "digest": d}
                        for n, d in self.on_xnat.items()
                    ]
                }
            }
        )

    def clearcache(self) -> None:
        pass

    def create_object(self, uri: str) -> SimpleNamespace:
        assert uri == "/data/experiments/XNAT_E1"
        return SimpleNamespace(fields=self.fields)


def _staging(tmp_path: ty.Any, checksums: dict[str, str]) -> XnatSessionOnlyListing:
    """A session-only staging dir: no dots in the name, one resource."""
    session_dir = tmp_path / "SESSLABEL"
    resource_dir = session_dir / "DICOM"
    resource_dir.mkdir(parents=True)
    for name in checksums:
        (resource_dir / name).write_bytes(b"x")
    (resource_dir / "__MANIFEST__.json").write_text(
        json.dumps({"checksums": checksums, "datatype": "medimage/dicom-series"})
    )
    return XnatSessionOnlyListing(session_dir)


def test_it_is_part_of_the_hierarchy() -> None:
    """The fix must not be able to miss this class again."""
    assert issubclass(XnatSessionOnlyListing, XnatSessionListing)
    assert "all_uploaded" not in XnatSessionOnlyListing.__dict__, (
        "a second copy of the completeness rule is how this bug survived"
    )
    assert "find_xnat_session" in XnatSessionOnlyListing.__dict__, (
        "the mode still resolves its session by a global label search"
    )
    assert "find_xnat_session_uri" in XnatSessionOnlyListing.__dict__, (
        "all_uploaded() finds the session through find_xnat_session_uri()"
    )


def test_short_resource_is_not_uploaded(tmp_path: ty.Any) -> None:
    """THE REGRESSION: 3 of 8 files on XNAT must not count as uploaded."""
    listing = _staging(tmp_path, LOCAL)
    on_xnat = {k: LOCAL[k] for k in list(LOCAL)[:3]}

    assert listing.all_uploaded(FakeConnection(on_xnat)) is False, (  # type: ignore[arg-type]
        "the label matches but 5 files are missing; reporting this as "
        "uploaded lets the staged copy be reclaimed while XNAT holds a "
        "fraction of the session"
    )


def test_complete_resource_is_uploaded(tmp_path: ty.Any) -> None:
    """A genuinely complete session must still be skipped."""
    listing = _staging(tmp_path, LOCAL)
    assert listing.all_uploaded(FakeConnection(dict(LOCAL))) is True  # type: ignore[arg-type]


def test_missing_session_on_xnat_is_not_uploaded(tmp_path: ty.Any) -> None:
    """The label search finding nothing still means not uploaded."""
    listing = _staging(tmp_path, LOCAL)
    assert listing.all_uploaded(FakeConnection({}, found=False)) is False  # type: ignore[arg-type]


def test_empty_digests_do_not_make_a_complete_session_look_short(
    tmp_path: ty.Any,
) -> None:
    """XNAT reports digest '' until a catalog refresh; names still count."""
    listing = _staging(tmp_path, LOCAL)
    xnat = FakeConnection({k: "" for k in LOCAL})
    assert listing.all_uploaded(xnat) is True  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "remote_fields,expected",
    [
        ({"scanner_site": "Sydney"}, True),
        ({"scanner_site": "Sydney", "other": "preserved"}, True),
        ({}, False),
        ({"scanner_site": "Melbourne"}, False),
    ],
)
def test_staged_fields_must_match_before_skipping_session_only_upload(
    tmp_path: ty.Any,
    remote_fields: dict[str, ty.Any],
    expected: bool,
) -> None:
    listing = _staging(tmp_path, LOCAL)
    (listing.cache_path / "__FIELDS__.json").write_text(
        json.dumps({"scanner_site": "Sydney"})
    )

    xnat = FakeConnection(dict(LOCAL), fields=remote_fields)
    assert listing.all_uploaded(xnat) is expected  # type: ignore[arg-type]
