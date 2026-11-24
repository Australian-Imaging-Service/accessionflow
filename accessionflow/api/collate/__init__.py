"""The collate stage, split into step functions (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

from .claim import (
    CLAIMED_FILES_DIRNAME,
    CLAIMED_MANIFEST,
    PROCESSING_NAME_DEFAULT,
    ClaimedFiles,
    claim_input_files,
    finish_claim,
    make_run_uid,
)
from .classify import (
    RecursionPlan,
    check_datatypes,
    classify_paths,
    disable_metadata_reading,
    drop_ignored_filesets,
    expand_claimed_paths,
    plan_recursion,
)
from .discover import list_input_files
from .group import (
    acquisition_id_for,
    clash_hint_for,
    group_into_accessions,
    resource_label_for,
)
from .metadata import (
    apply_path_metadata,
    inject_accession_tables,
    inject_fileset_tables,
    load_metadata_tables,
    tag_fileset_types,
)
from .save import (
    STAGED_MARKER_SUFFIX,
    remove_claimed_files,
    save_to_build_dir,
    stage_accession,
    warn_if_hardlinks_unavailable,
)

__all__ = [
    "STAGED_MARKER_SUFFIX",
    "CLAIMED_FILES_DIRNAME",
    "CLAIMED_MANIFEST",
    "PROCESSING_NAME_DEFAULT",
    "ClaimedFiles",
    "claim_input_files",
    "RecursionPlan",
    "acquisition_id_for",
    "apply_path_metadata",
    "check_datatypes",
    "clash_hint_for",
    "classify_paths",
    "disable_metadata_reading",
    "drop_ignored_filesets",
    "expand_claimed_paths",
    "finish_claim",
    "group_into_accessions",
    "inject_accession_tables",
    "inject_fileset_tables",
    "list_input_files",
    "load_metadata_tables",
    "make_run_uid",
    "plan_recursion",
    "remove_claimed_files",
    "resource_label_for",
    "save_to_build_dir",
    "stage_accession",
    "tag_fileset_types",
    "warn_if_hardlinks_unavailable",
]
