"""The collate stage, split into step functions (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

from .claim import (
    CLAIMED_FILES_DIRNAME,
    CLAIMED_MANIFEST,
    PROCESSING_NAME_DEFAULT,
    ClaimedFiles,
    claim_input_files,
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
from .metadata import apply_path_metadata, tag_fileset_types

__all__ = [
    "CLAIMED_FILES_DIRNAME",
    "CLAIMED_MANIFEST",
    "PROCESSING_NAME_DEFAULT",
    "ClaimedFiles",
    "claim_input_files",
    "RecursionPlan",
    "apply_path_metadata",
    "check_datatypes",
    "classify_paths",
    "disable_metadata_reading",
    "drop_ignored_filesets",
    "expand_claimed_paths",
    "list_input_files",
    "make_run_uid",
    "plan_recursion",
    "tag_fileset_types",
]
