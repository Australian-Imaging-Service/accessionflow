"""The collate stage, split into step functions (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

from .classify import check_datatypes
from .discover import list_input_files

__all__ = ["check_datatypes", "list_input_files"]
