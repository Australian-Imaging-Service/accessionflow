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
from .group import (
    acquisition_id_for,
    clash_hint_for,
    group_into_accessions,
    resource_label_for,
)
from .metadata import (
    apply_path_metadata,
    inject_fileset_tables,
    load_metadata_tables,
    tag_fileset_types,
)

__all__ = [
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
    "group_into_accessions",
    "inject_fileset_tables",
    "list_input_files",
    "load_metadata_tables",
    "make_run_uid",
    "plan_recursion",
    "resource_label_for",
    "tag_fileset_types",
]
