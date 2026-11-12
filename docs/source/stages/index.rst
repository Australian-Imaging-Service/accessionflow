.. _stages:

Stages
======

Between collating the files from a :ref:`source <sources>` and depositing them in a
:ref:`data store <stores>`, these stages work the same way whatever the source and
store. Each reads the staging directory written by the stage before it and writes its
own (see :ref:`concepts-accession-flows`):

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

Only ``label`` is needed in every accession flow. A typical order is::

    collate → [attach] → label → [deidentify] → [select-fields] → [package] → store

``attach`` can run at any point after ``collate``, but before ``deidentify`` if its
pattern relies on identifying metadata (see :doc:`attach`). ``select-fields`` can run at
any point after ``label``, since every stage carries the fields through, but after
``deidentify`` if a field could identify the subject, since ``deidentify`` doesn't
de-identify the fields (see :doc:`select_fields`).

.. figure:: /_static/images/diagrams/accessionflow-stages.svg
   :alt: What each stage does to an accession, from unsorted input files to the repository
   :width: 100%
   :align: center
   :figclass: only-light

.. figure:: /_static/images/diagrams/accessionflow-stages-dark.svg
   :alt: What each stage does to an accession, from unsorted input files to the repository
   :width: 100%
   :align: center
   :figclass: only-dark
