"""The collate stage, split into step functions (see
``prefect-migration-docs/ROADMAP.md``, Phase 1)"""

from .discover import list_input_files

__all__ = ["list_input_files"]
