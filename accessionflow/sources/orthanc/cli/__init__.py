"""The 'collate orthanc' subcommand, which is registered with the 'collate' stage
when this package is imported"""

from .collate_cli import collate_cmd

__all__ = ["collate_cmd"]
