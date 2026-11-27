"""Assigning each accession the labels it is delivered and stored under (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

import typing as ty

from accessionflow.exceptions import LabelsNotAssignedError
from accessionflow.model.accession import Accession

__all__ = ["assign_labels", "constant_label_fields"]


def constant_label_fields(
    label_fields: ty.Mapping[str, str],
    constant_labels: ty.Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Turns labels given as constants into metadata fields, so that an accession's
    labels are always made from its metadata and its directory name matches what is
    saved. Each constant is written to a field named after its level (e.g.
    ``project``), by `ApplyFilesetMetadata`, and its level is labelled from that field.
    The field read from the files for that level, e.g. ``StudyComments``, is left as it
    was. It only checks and computes, so it runs before any step that changes the file
    system

    Parameters
    ----------
    label_fields : Mapping[str, str]
        the metadata field (or a format string over several fields) each label is made
        from, keyed by level (see `assign_labels`)
    constant_labels : Mapping[str, str]
        labels used as given, keyed by level, e.g. ``{"project": "MYPROJECT"}``

    Returns
    -------
    dict[str, str]
        the label fields, with each constant level labelled from the field named after
        it
    dict[str, str]
        the constant metadata fields to write, e.g. ``{"project": "MYPROJECT"}``, for
        ``ApplyFilesetMetadata(constant_fields=...)``

    Raises
    ------
    ValueError
        if a constant label isn't one of the label levels
    """
    if unknown := set(constant_labels) - set(label_fields):
        raise ValueError(
            f"Constant labels {sorted(unknown)} are not label levels "
            f"{list(label_fields)}"
        )
    fields = {
        level: level if level in constant_labels else field
        for level, field in label_fields.items()
    }
    return fields, dict(constant_labels)


def assign_labels(
    accession: Accession,
    label_fields: ty.Mapping[str, str],
    acquisition_field: str | None = None,
    store_type: str | None = None,
) -> Accession:
    """Assigns an accession its labels from its metadata, e.g. ``project``,
    ``subject`` and ``session`` for XNAT, and a description for each acquisition. The
    labels name the accession's directory in the target directory, ``<labels>_<run_uid>``
    (`move_to_target`).

    The labels are made from the metadata only, so the directory name matches the
    metadata saved with the accession. Labels given as constants are written to the
    metadata first (`constant_label_fields`).

    Unlike the ``label`` stage, it doesn't use placeholder labels for fields missing
    from the metadata: it raises, so the accession isn't delivered, and its files are
    left for `FinishClaim` to move to the unprocessed directory.

    The accession is changed in place and returned.

    Parameters
    ----------
    accession : Accession
        the accession to label, from `group_into_accessions`
    label_fields : Mapping[str, str]
        the metadata field (or a format string over several fields) each label is made
        from, keyed by the name of its level in the data store, in order from the top
        level, e.g. ``{"project": "StudyComments", "subject": "PatientID",
        "session": "AccessionNumber"}``
    acquisition_field : str, optional
        the metadata field each acquisition's description is made from. Acquisitions it
        can't be resolved for are left without one
    store_type : str, optional
        the data store the labels are for, e.g. 'xnat', recorded with the accession

    Returns
    -------
    Accession
        the same accession, labelled

    Raises
    ------
    LabelsNotAssignedError
        if a field a label is made from is missing from the accession's metadata
    """
    missing = accession.label(
        label_fields,
        acquisition_field=acquisition_field,
        store_type=store_type,
    )
    if missing:
        raise LabelsNotAssignedError(
            f"Couldn't assign the labels of accession '{accession.uid}', as the "
            f"metadata fields {sorted(missing)} are missing"
        )
    return accession
