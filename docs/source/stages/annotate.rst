.. _stage-annotate:

Annotate
========

``annotate`` adds *fields* to an accession, extracted from its metadata: named values
that the data store records alongside the accession. ``store xnat`` sets them as custom
variables on the XNAT session, and ``store folder`` deposits them as a
``__FIELDS__.json`` file in the accession's folder.

.. code-block:: console

    $ accessionflow annotate /data/staging/labelled /data/staging/annotated \
        --extract scanner_site InstitutionName \
        --extract study_year '{StudyDate:%Y}'

* ``INPUT_DIR`` — the accessions to annotate
* ``OUTPUT_DIR`` — where the accessions are written with their fields, in
  ``__FIELDS__.json`` next to their metadata; point ``store`` at it
* ``--extract <field> <specifier>`` — a field, and the metadata field or format string
  its value is taken from (see :ref:`concepts-specifiers`). Repeatable; in the
  ``ACFLOW_FIELDS`` environment variable, separate the entries with ``;``

Fields the accession already has are kept, and a field whose specifier can't be
resolved is skipped.

Every later stage carries the fields through to its output unchanged, so
``annotate`` can run at any point after ``label``. In practice it runs before
``deidentify``, which drops every metadata field from its output except the accession's
UID and the fields that identify its labels. But ``deidentify`` doesn't de-identify the
fields either: a field added before it is deposited exactly as it was extracted. So only
extract fields that can't identify the subject, or coarser values derived from them,
e.g. ``'{StudyDate:%Y}'`` for the year of the study rather than its date.

To annotate de-identified data instead, e.g. so that a field holds a value the recipe
has shifted, run ``annotate`` after ``deidentify`` and keep the metadata fields it needs
with ``deidentify``'s ``--metadata-allowlist`` option:

.. code-block:: console

    $ accessionflow deidentify /data/staging/labelled /data/staging/deidentified \
        /etc/accessionflow/deid-recipes --metadata-allowlist StudyDate

    $ accessionflow annotate /data/staging/deidentified /data/staging/fields \
        --extract study_date StudyDate

The fields then hold the de-identified values, e.g. a ``StudyDate`` that the recipe has
shifted.
