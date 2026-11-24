"""Grouping the file-sets into accessions, acquisitions and resources (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

import typing as ty

from fileformats.core import FileSet
from fileformats.medimage import DicomCollection
from tqdm import tqdm

from accessionflow.helpers.arg_types import ClashSpec, IDSpec, OnResourceClash
from accessionflow.helpers.logging import logger

# Until Accession.from_paths is removed, these stay in the model, which uses them too
from accessionflow.model.accession import (
    _DERIVED_ID,
    Accession,
    _datatype_resource_label,
    dicom_image_type_to_resource_label,
)

__all__ = [
    "acquisition_id_for",
    "clash_hint_for",
    "group_into_accessions",
    "resource_label_for",
]


def resource_label_for(
    fileset: FileSet, resource_field: ty.Sequence[IDSpec] = ()
) -> tuple[str, bool]:
    """The label of the resource a file-set is collated into

    - A DICOM collection is labelled from the ``ImageType`` of its first file, or
      'DICOM' if it has none, as XNAT needs.
    - With no ``--resource`` spec, the resource is labelled with the format part of the
      file-set type's MIME-like name, e.g. 'json' or 'vectra-export'. The label is then
      derived.
    - Otherwise, from the matching ``--resource`` spec.

    Parameters
    ----------
    fileset : FileSet
        the file-set
    resource_field : Sequence[IDSpec], optional
        the ``--resource`` specs

    Returns
    -------
    tuple[str, bool]
        the label, and whether it was derived from the file-set's type
    """
    if isinstance(fileset, DicomCollection):
        try:
            image_type = fileset.contents[0].metadata["ImageType"]
        except (KeyError, IndexError):
            return "DICOM", False
        return dicom_image_type_to_resource_label(image_type), False
    if not resource_field:
        return _datatype_resource_label(type(fileset)), True
    return IDSpec.get_value_from_matching_spec(fileset, resource_field), False


def acquisition_id_for(
    fileset: FileSet,
    acquisition_id_field: ty.Sequence[IDSpec],
    resource_label: str,
) -> tuple[str, bool]:
    """The ID of the acquisition a file-set is collated into: from the ``--acquisition``
    spec whose datatype matches the file-set, or, if none does, the resource's label

    Parameters
    ----------
    fileset : FileSet
        the file-set
    acquisition_id_field : Sequence[IDSpec]
        the ``--acquisition`` specs
    resource_label : str
        the label of the file-set's resource, from `resource_label_for`

    Returns
    -------
    tuple[str, bool]
        the ID, and whether it was derived from the resource's label
    """
    acquisition_id = IDSpec.get_value_from_matching_spec(
        fileset, acquisition_id_field, default=_DERIVED_ID
    )
    if acquisition_id is _DERIVED_ID:
        return resource_label, True
    return acquisition_id, False


def clash_hint_for(acquisition_derived: bool, resource_derived: bool) -> str | None:
    """The hint added to a resource-name clash when the clashing IDs were derived from
    the file-set's type rather than given by a spec

    Parameters
    ----------
    acquisition_derived : bool
        whether the acquisition ID was derived (`acquisition_id_for`)
    resource_derived : bool
        whether the resource label was derived (`resource_label_for`)

    Returns
    -------
    str or None
        the hint, or None if neither was derived
    """
    derived_specs = [
        spec
        for spec, was_derived in (
            ("--acquisition", acquisition_derived),
            ("--resource", resource_derived),
        )
        if was_derived
    ]
    if not derived_specs:
        return None
    return (
        f"the {' and '.join(derived_specs)} ID(s) for this resource were "
        f"auto-derived from its fileset type; pass explicit "
        f"{' / '.join(derived_specs)} specifier(s) to control collation"
    )


def group_into_accessions(
    filesets: ty.Sequence[FileSet],
    accession_uid_field: ty.Sequence[IDSpec],
    acquisition_id_field: ty.Sequence[IDSpec] = (),
    resource_field: ty.Sequence[IDSpec] = (),
    on_resource_clash: OnResourceClash | ty.Sequence[ClashSpec] = "error",
    run_uid: str | None = None,
) -> list[Accession]:
    """Groups the file-sets into accessions, acquisitions and resources

    Each file-set's accession UID comes from the matching ``--accession`` spec, its
    resource label from `resource_label_for` and its acquisition ID from
    `acquisition_id_for`. This is where the file-sets' headers are first read for
    their ID fields, which can take minutes for a large DICOM delivery, so it shows a
    progress bar.

    Parameters
    ----------
    filesets : Sequence[FileSet]
        the file-sets, after `inject_fileset_tables`
    accession_uid_field : Sequence[IDSpec]
        the ``--accession`` specs
    acquisition_id_field : Sequence[IDSpec], optional
        the ``--acquisition`` specs
    resource_field : Sequence[IDSpec], optional
        the ``--resource`` specs
    on_resource_clash : OnResourceClash or Sequence[ClashSpec], optional
        what to do when two file-sets resolve to the same acquisition and resource
        names (see `Accession.add_resource`), by default "error"
    run_uid : str, optional
        the run's UID, from `make_run_uid`, set on each accession

    Returns
    -------
    list[Accession]
        the accessions, in the order their first file-sets came in

    Raises
    ------
    TypeError
        if no ``--accession`` spec matches a file-set's datatype
    AccessionParseError
        if a file-set lacks a field an ID spec uses
    KeyError or ValueError
        if two resources clash and ``on_resource_clash`` doesn't resolve it
    """
    accessions: dict[str, Accession] = {}
    for fileset in tqdm(filesets, "Collating files into accessions..."):
        accession_uid = IDSpec.get_value_from_matching_spec(
            fileset, accession_uid_field
        )
        resource_label, resource_derived = resource_label_for(fileset, resource_field)
        acquisition_id, acquisition_derived = acquisition_id_for(
            fileset, acquisition_id_field, resource_label
        )
        try:
            accession = accessions[accession_uid]
        except KeyError:
            accession = accessions[accession_uid] = Accession(
                uid=accession_uid, run_uid=run_uid
            )
        logger.debug(
            "Adding resource '%s' to %s acquisition in %s accession",
            resource_label,
            acquisition_id,
            accession_uid,
        )
        accession.add_resource(
            acquisition_id,
            None,
            resource_label,
            fileset,
            on_clash=on_resource_clash,
            clash_hint=clash_hint_for(acquisition_derived, resource_derived),
        )
    return list(accessions.values())
