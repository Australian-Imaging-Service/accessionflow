"""Assigning each accession the labels it is delivered and stored under (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

import typing as ty

from accessionflow.exceptions import LabelsNotAssignedError
from accessionflow.model.accession import Accession

__all__ = ["assign_labels"]


def assign_labels(
    accession: Accession,
    label_fields: ty.Mapping[str, str],
    acquisition_field: str | None = None,
    constant_labels: ty.Mapping[str, str] | None = None,
    store_type: str | None = None,
) -> Accession:
    """Assigns an accession its labels from its metadata, e.g. ``project``,
    ``subject`` and ``session`` for XNAT, and a description for each acquisition. The
    labels name the accession's directory in the target directory, ``<labels>_<run_uid>``
    (`move_to_target`).

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
    constant_labels : Mapping[str, str], optional
        labels used as given rather than made from the metadata, keyed by level name
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
        constant_labels=constant_labels,
        store_type=store_type,
    )
    if missing:
        raise LabelsNotAssignedError(
            f"Couldn't assign the labels of accession '{accession.uid}', as the "
            f"metadata fields {sorted(missing)} are missing"
        )
    return accession
