.. _stages:

Stages
======

Between collating the files from a :ref:`source <sources>` and depositing them in a
:ref:`data store <stores>`, these stages work the same way whatever the source and
store. Each reads the staging directory written by the stage before it and writes its
own (see :ref:`concepts-pipeline`):

:doc:`attach`
    Links in files that don't carry the metadata to collate them by, e.g. raw PET
    list-mode files, using a naming convention they share with the files that do.
:doc:`label`
    Labels each accession with where it belongs in the data store. Each store provides
    its own ``label`` subcommand, e.g. ``label xnat`` or ``label folder``, but they all
    work the same way.
:doc:`deidentify`
    Strips patient-identifying information, with recipes chosen per project and file
    format, and optionally keeps a mapping to reverse it.
:doc:`package`
    Converts resources into the forms the data store needs, e.g. a zip archive and a
    sample file, after de-identification has worked on the unpacked files.
:doc:`select_fields`
    Copies metadata fields into the accession's fields, which the data store records
    alongside it, e.g. as XNAT custom variables.

Only ``label`` is needed for every pipeline. The full order is::

    collate → [attach] → label → [deidentify] → [package] → [select-fields] → store

``attach`` can run at any point after ``collate``, but before ``deidentify`` if its
pattern relies on identifying metadata (see :doc:`attach`). ``select-fields`` comes
last, since ``deidentify`` and ``package`` don't carry the fields through to their
output (see :doc:`select_fields`).
