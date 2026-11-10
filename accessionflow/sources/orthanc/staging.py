"""Staging DICOM studies from an Orthanc server, by hardlinking the files from its
storage directory into the staging directory"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import typing as ty
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import requests
from dateutil.parser import isoparse
from fileformats.core import FileSet
from fileformats.medimage import DicomSeries
from tqdm import tqdm

from accessionflow.exceptions import OrthancStudyChangedError, StagingError
from accessionflow.helpers.arg_types import IDSpec
from accessionflow.helpers.logging import logger
from accessionflow.helpers.metadata import Metadata
from accessionflow.model.accession import Accession, dicom_image_type_to_resource_label
from accessionflow.model.resource import Resource


def _dicom_multi_value(value: ty.Any) -> list[str]:
    """The components of a multi-valued DICOM tag as Orthanc reports it: one
    backslash-joined string, or a list when the caller already split it."""
    if isinstance(value, str):
        return value.split("\\")
    return [str(v) for v in value]


def _remove_scratch_dir(path: Path) -> None:
    """Remove a scratch directory of a study that failed to stage.

    A failure to remove it, for example a permission error, is logged and not
    raised, so the next study is still staged. The remaining files are then
    removed where possible.
    """
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        # The directory, or a file in it, is already gone. Remove the rest.
        shutil.rmtree(path, ignore_errors=True)
    except OSError as e:
        logger.warning("Could not remove the scratch directory '%s': %s", path, e)
        shutil.rmtree(path, ignore_errors=True)


def _is_timestamp(value: str) -> bool:
    """Whether `value` is a real Orthanc timestamp (YYYYMMDDTHHMMSS)."""
    try:
        datetime.strptime(value, "%Y%m%dT%H%M%S")
    except ValueError:
        return False
    return True


def stage_studies(
    url: str,
    output_dir: Path,
    store_dir: Path,
    user: str,
    password: str,
    to_process_label: str | None = None,
    processed_label: str = "xnat-sorted",
    max_workers: int | None = None,
    wait_period: int = 0,
    conversion_map: (
        dict[ty.Type[FileSet], tuple[ty.Type[FileSet], dict[str, str]]] | None
    ) = None,
    errors: list[str] | None = None,
) -> list[Accession]:
    """Stage DICOM studies from Orthanc directly into output_dir using hardlinks.
    Requires orthanc_storage_dir and output_dir to be on the same filesystem.

    Parameters
    ----------
    url : str
        Base URL of the Orthanc REST API, e.g. 'http://orthanc:8042'
    output_dir : Path
        Staging directory. Hardlinks land here directly, must be on the same
        filesystem as orthanc_storage_dir.
    store_dir : Path
        Orthanc's StorageDirectory as mounted.
    user : str, optional
        Orthanc basic auth credentials username
    password : str, optional
        Orthanc basic auth credentials password
    processed_label : str, optional
        Label applied after staging to prevent re-processing, by default 'xnat-sorted'.
        Remove via the Orthanc UI to re-sort a study.
    max_workers : int, optional
        the number of threads to use to fetch per-instance attachment info from
        Orthanc concurrently. If None, defaults to
        `concurrent.futures.ThreadPoolExecutor`'s default.
    wait_period : int, optional
        Minimum number of seconds since Orthanc last updated a study before it is
        staged, by default 0.
    conversion_map : dict[type[FileSet], tuple[type[FileSet], dict[str, str]]], optional
        A mapping of source FileSet types to (target FileSet types, conversion
        options). Series matching a source type are converted to the target type
        before the study is labelled as processed, with the options passed through
        to ``convert()``.

    errors : list[str], optional
        if given, the IDs of the studies that could not be staged in this
        pass are appended to it. Such a study is logged and left
        unlabelled, so it is tried again on the next pass
    Returns
    -------
    list[Accession]
        the staged accessions, loaded from output_dir
    """
    output_dir = Path(output_dir).resolve()
    auth = (user, password) if user else None

    def get_json(path: str) -> ty.Any:
        resp = requests.get(f"{url}{path}", auth=auth)
        resp.raise_for_status()
        return resp.json()

    resp = requests.post(
        f"{url}/tools/find",
        auth=auth,
        json={
            "Level": "Study",
            "Query": {},
            "Labels": [processed_label],
            "LabelsConstraint": "None",
        },
    )
    resp.raise_for_status()
    study_ids = resp.json()
    logger.info("Found %d unstaged studies in Orthanc at '%s'", len(study_ids), url)

    def _find_studies(labels: list[str], constraint: str) -> set[str]:
        body: dict[str, ty.Any] = {"Level": "Study", "Query": {}}
        if labels:
            body["Labels"] = labels
            body["LabelsConstraint"] = constraint
        resp = requests.post(f"{url}/tools/find", auth=auth, json=body)
        resp.raise_for_status()
        return set(resp.json())

    if to_process_label:
        candidates = _find_studies([to_process_label], "All")
    else:
        candidates = _find_studies([], "All")

    if processed_label:
        # The snapshot label below is "<processed>-<LastUpdate>-<digest>" in
        # at most 64 characters (Orthanc's label limit), with a digest of
        # at least 8 hex digits. Checked here, before any study is staged.
        snapshot_prefix = f"{processed_label}-"
        digest_len = min(24, 64 - len(snapshot_prefix) - len("YYYYMMDDTHHMMSS-"))
        if digest_len < 8:
            raise ValueError(
                f"processed label {processed_label!r} is too long for a "
                "snapshot label (64 characters at most)"
            )
        receipt_re = re.compile(
            re.escape(snapshot_prefix) + r"(\d{8}T\d{6})-([0-9a-f]{%d})$" % digest_len
        )
        # LastUpdate has one-second resolution. The change check relies on
        # a late instance getting a LastUpdate in a later second than the
        # one staged, so the study must have been quiet for a second.
        if not wait_period or wait_period < 1:
            logger.info(
                "Using a wait period of 1 second with the processed label "
                "%r (requested: %r)",
                processed_label,
                wait_period,
            )
            wait_period = 1
        candidates -= _find_studies([processed_label], "All")
        # A processed study can change after it was staged: a series that
        # arrives late. The staging run records the LastUpdate it staged
        # as a second label, "<processed_label>-<LastUpdate>". A processed
        # study whose current LastUpdate has no such label (or none at
        # all, from an older version) has instances this stage never
        # saw: its labels are removed and it is staged again in full.
        resp = requests.post(
            f"{url}/tools/find",
            auth=auth,
            json={
                "Level": "Study",
                "Query": {},
                "Labels": [processed_label],
                "LabelsConstraint": "All",
                "Expand": True,
            },
        )
        resp.raise_for_status()
        expanded = resp.json()
        if not isinstance(expanded, list) or not all(
            isinstance(e, dict) and isinstance(e.get("ID"), str) for e in expanded
        ):
            raise ValueError(f"Unexpected reply to the expanded study query at '{url}'")
        for entry in expanded:
            # Both keys must be present. A study document without Labels
            # comes from an Orthanc without label support, which this
            # mode cannot work with.
            labels = entry.get("Labels")
            last_update = entry.get("LastUpdate")
            if (
                not isinstance(labels, list)
                or not all(isinstance(lb, str) for lb in labels)
                or not isinstance(last_update, str)
                or not re.fullmatch(r"\d{8}T\d{6}", last_update)
                or not _is_timestamp(last_update)
            ):
                raise ValueError(
                    f"Unexpected Labels or LastUpdate for Orthanc study "
                    f"'{entry['ID']}' at '{url}'"
                )
            if to_process_label and to_process_label not in labels:
                continue
            snapshots = [lb for lb in labels if lb.startswith(snapshot_prefix)]
            # Exactly one well-formed snapshot label naming the current
            # LastUpdate: the cheap check. The digest is for the reclaimer,
            # which holds the instance list anyway.
            match = receipt_re.match(snapshots[0]) if len(snapshots) == 1 else None
            if match and match.group(1) == last_update:
                continue
            logger.info(
                "Orthanc study '%s' changed after it was staged "
                "(LastUpdate %s, snapshot labels %s): staging it again",
                entry["ID"],
                last_update,
                snapshots,
            )
            for label in [processed_label, *snapshots]:
                requests.delete(
                    f"{url}/studies/{entry['ID']}/labels/{label}", auth=auth
                ).raise_for_status()
            candidates.add(entry["ID"])

    study_ids = sorted(candidates)
    logger.info(
        "Found %d studies in Orthanc at '%s' (label=%r, skip label=%r)",
        len(study_ids),
        url,
        to_process_label,
        processed_label,
    )

    convert_series = any(
        issubclass(DicomSeries, src_type) for src_type in conversion_map or {}
    )

    staged: list[Accession] = []
    # The build directory and the conversion scratch directories of the
    # study being staged, for the clean-up when staging fails part way.
    current_work_dir: dict[str, ty.Any] = {}

    def _discard_work_dir() -> None:
        work_dir = current_work_dir.pop("path", None)
        if work_dir is not None and work_dir.exists():
            _remove_scratch_dir(work_dir)
        for convert_dir in current_work_dir.pop("convert", []):
            _remove_scratch_dir(convert_dir)

    def _stage_study(study_id: str) -> Accession | None:
        study = get_json(f"/studies/{study_id}")
        if wait_period:
            try:
                last_update = isoparse(study["LastUpdate"])
            except (KeyError, TypeError, ValueError) as e:
                raise ValueError(
                    f"Could not parse LastUpdate for Orthanc study '{study_id}'"
                ) from e
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - last_update).total_seconds()
            if age < wait_period:
                logger.info(
                    "Skipping Orthanc study '%s' because it was updated %.0f "
                    "seconds ago (wait period: %d seconds)",
                    study_id,
                    age,
                    wait_period,
                )
                return None
        study_tags = {**study["MainDicomTags"], **study["PatientMainDicomTags"]}

        session_uid = IDSpec("StudyInstanceUID").get_value(study_tags)
        final_dir = output_dir / f"_.{session_uid}"
        # One "collate orthanc" producer must own this output directory. A
        # converter child that outlives its parent is outside this contract.
        work_dir = output_dir / "__build__" / f"orthanc_{session_uid}"
        current_work_dir["path"] = work_dir
        if work_dir.exists():
            shutil.rmtree(work_dir)
        session_dir = work_dir / final_dir.name
        session_dir.mkdir(parents=True)

        modalities: set[str] = set()
        staged_instance_ids: dict[str, set[str]] = {}
        staged_resources: set[tuple[str, str]] = set()
        scan_types: dict[str, str] = {}
        for series_id in study["Series"]:
            series = get_json(f"/series/{series_id}")
            if modality := series["MainDicomTags"].get("Modality"):
                modalities.add(modality)
            all_tags = {**study_tags, **series["MainDicomTags"]}
            fallback_fields = []
            number = all_tags.get("SeriesNumber")
            if number is None or not str(number).strip():
                # Series identity is stable across retries and late instances.
                # Prefer the DICOM UID; Orthanc's series ID is the fallback
                # when its indexed tags do not include that UID. Never use
                # iteration order or a shared "unknown" scan number.
                series_uid = all_tags.get("SeriesInstanceUID")
                if series_uid and str(series_uid).strip():
                    # Match XNAT's header importer, otherwise it creates a
                    # second scan for the same unnumbered DICOM series.
                    scan_id = IDSpec("SeriesInstanceUID").get_value(all_tags)
                else:
                    scan_id = "series_" + hashlib.sha256(series_id.encode()).hexdigest()
                fallback_fields.append("SeriesNumber")
            else:
                scan_id = IDSpec("SeriesNumber").get_value(
                    {**all_tags, "SeriesNumber": str(number)}
                )
            description = all_tags.get("SeriesDescription")
            if description is None or not str(description).strip():
                scan_type = "Series_" + scan_id
                fallback_fields.append("SeriesDescription")
            else:
                scan_type = IDSpec("SeriesDescription").get_value(all_tags)
            if fallback_fields:
                logger.warning(
                    "Using a stable series fallback for missing %s",
                    ", ".join(fallback_fields),
                    extra={
                        "event": "series_metadata_fallback",
                        "orthanc_series_id": series_id,
                    },
                )

            if "ImageType" in all_tags:
                # Orthanc gives a multi-valued tag as one backslash-joined
                # string. The mapping wants the components; an escaped ID
                # string ("DERIVED_SECONDARY") never matched any of them.
                resource_label = dicom_image_type_to_resource_label(
                    _dicom_multi_value(all_tags["ImageType"])
                )
            else:
                resource_label = "DICOM"
            scan_dir = session_dir / f"{scan_id}.{scan_type}"
            # The scan ID (SeriesNumber) must name one scan. Two series with
            # the same SeriesNumber and SeriesDescription would share one
            # resource directory and one manifest; two with the same
            # SeriesNumber and different descriptions would be loaded as
            # one scan, and one of them dropped. Refuse the study instead.
            if scan_types.setdefault(scan_id, scan_type) != scan_type:
                raise StagingError(
                    f"Orthanc study '{study_id}': SeriesNumber '{scan_id}' is "
                    f"used by series with different descriptions "
                    f"('{scan_types[scan_id]}' and '{scan_type}'). The study "
                    "needs attention before it can be staged."
                )
            resource_key = (scan_dir.name, resource_label)
            if resource_key in staged_resources:
                raise StagingError(
                    f"Orthanc study '{study_id}': series '{series_id}' maps to "
                    f"'{scan_dir.name}/{resource_label}' like another series of "
                    f"the study (SeriesNumber '{scan_id}', SeriesDescription "
                    f"'{scan_type}'). The study needs attention before it can "
                    "be staged."
                )
            staged_resources.add(resource_key)
            if convert_series:
                convert_tmp_dir = Path(
                    tempfile.mkdtemp(prefix="__convert_", dir=output_dir)
                )
                current_work_dir.setdefault("convert", []).append(convert_tmp_dir)
                resource_dir = convert_tmp_dir / resource_label
            else:
                resource_dir = scan_dir / resource_label
            resource_dir.mkdir(parents=True, exist_ok=True)

            instances = get_json(f"/series/{series_id}/instances")
            staged_instance_ids[series_id] = {instance["ID"] for instance in instances}

            def _link_instance(
                instance: ty.Mapping[str, ty.Any],
                resource_dir: Path = resource_dir,
                series_id: str = series_id,
            ) -> tuple[str, str]:
                instance_id = instance["ID"]
                sop_uid = instance["MainDicomTags"].get("SOPInstanceUID", instance_id)
                fname = f"{sop_uid}.dcm"
                dest_path = resource_dir / fname
                attachment = get_json(
                    f"/instances/{instance_id}/attachments/dicom/info"
                )
                if attachment["CompressedSize"] != attachment["UncompressedSize"]:
                    raise ValueError(
                        f"Instance '{instance_id}' in series '{series_id}' is stored "
                        "compressed in Orthanc — disable StorageCompression in the "
                        "Orthanc config to use hardlink sorting."
                    )
                if not dest_path.exists():
                    uuid = attachment["Uuid"]
                    src_path = Path(store_dir) / uuid[0:2] / uuid[2:4] / uuid
                    os.link(src_path, dest_path)
                return fname, attachment["UncompressedMD5"]

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                linked = executor.map(_link_instance, instances)
            checksums: dict[str, str] = dict(linked)

            manifest = {"datatype": "medimage/dicom-series", "checksums": checksums}
            Resource.write_manifest(resource_dir, manifest)

            if convert_series:
                try:
                    Resource.load(resource_dir, check_checksums=False).save(
                        scan_dir,
                        conversion_map=conversion_map,
                        calculate_checksums=False,
                        overwrite=True,
                    )
                finally:
                    shutil.rmtree(convert_tmp_dir)

        metadata_path = session_dir / Metadata.FNAME
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                existing_tags = json.load(f)
            study_tags.update(existing_tags)
        if modalities:
            study_tags["Modality"] = (
                next(iter(modalities)) if len(modalities) == 1 else list(modalities)
            )
        # Keep the grouping identity when load() reads the saved metadata.
        study_tags[Accession.UID_METADATA_KEY] = session_uid
        with open(metadata_path, "w") as f:
            json.dump(study_tags, f, indent=4, default=str)

        staged_session = Accession.load(session_dir)

        if processed_label:
            current_study = get_json(f"/studies/{study_id}")
            current_series_ids = set(current_study["Series"])
            if current_study.get("LastUpdate") != study.get(
                "LastUpdate"
            ) or current_series_ids != set(staged_instance_ids):
                raise OrthancStudyChangedError(
                    f"Orthanc study '{study_id}' changed while it was being staged"
                )
            for series_id, expected_instance_ids in staged_instance_ids.items():
                current_instances = get_json(f"/series/{series_id}/instances")
                if {instance["ID"] for instance in current_instances} != (
                    expected_instance_ids
                ):
                    raise OrthancStudyChangedError(
                        f"Orthanc study '{study_id}' changed while it was being staged"
                    )
        if os.path.lexists(final_dir):
            logger.error(
                "Skipping Orthanc study '%s': destination exists at '%s'",
                study_id,
                final_dir,
            )
            shutil.rmtree(work_dir)
            if errors is not None:
                errors.append(study_id)
            return None
        session_dir.rename(final_dir)
        for resource in staged_session.resources:
            resource.fileset.fspaths = frozenset(
                final_dir / path.relative_to(session_dir)
                for path in resource.fileset.fspaths
            )
        work_dir.rmdir()
        if processed_label:
            # The snapshot label names the LastUpdate the final check
            # verified. A stale one from an earlier staging goes first,
            # and the processed label last, so a processed study always
            # carries exactly one snapshot label.
            exported = sorted(
                iid for ids in staged_instance_ids.values() for iid in ids
            )
            digest = hashlib.sha256(("\n".join(exported) + "\n").encode()).hexdigest()[
                :digest_len
            ]
            snapshot = f"{snapshot_prefix}{study['LastUpdate']}-{digest}"
            for stale in current_study.get("Labels") or []:
                if stale.startswith(f"{processed_label}-") and stale != snapshot:
                    requests.delete(
                        f"{url}/studies/{study_id}/labels/{stale}", auth=auth
                    ).raise_for_status()
            requests.put(
                f"{url}/studies/{study_id}/labels/{snapshot}", auth=auth
            ).raise_for_status()
            requests.put(
                f"{url}/studies/{study_id}/labels/{processed_label}", auth=auth
            ).raise_for_status()

        logger.info("Staged and labelled study '%s' -> '%s'", study_id, final_dir.name)
        return staged_session

    for study_id in tqdm(study_ids, "Staging studies from Orthanc"):
        current_work_dir.clear()
        try:
            session = _stage_study(study_id)
        except OrthancStudyChangedError as e:
            logger.warning("%s. It is staged again on a later pass.", e)
            _discard_work_dir()
        except Exception as e:  # noqa: BLE001 - one study must not stop the stage
            logger.error("Skipping Orthanc study '%s': %s", study_id, e, exc_info=True)
            _discard_work_dir()
            if errors is not None:
                errors.append(study_id)
        else:
            if session is not None:
                staged.append(session)

    return staged
