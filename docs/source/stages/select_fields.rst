.. _stage-select-fields:

Select fields
=============

``select-fields`` copies metadata into an accession's *fields*: named values that the
data store records alongside the accession. ``store xnat`` sets them as custom variables
on the XNAT session, and ``store folder`` deposits them as a ``__FIELDS__.json`` file in
the accession's folder.

.. code-block:: console

    $ accessionflow select-fields /data/staging/deidentified /data/staging/fields \
        --extract scanner_site InstitutionName \
        --extract study_year '{StudyDate:%Y}'

* ``INPUT_DIR`` — the accessions to select fields for
* ``OUTPUT_DIR`` — where the accessions are written with their fields, in
  ``__FIELDS__.json`` next to their metadata; point ``store`` at it
* ``--extract <field> <specifier>`` — a field, and the metadata field or format string
  its value is taken from (see :ref:`concepts-specifiers`). Repeatable; in the
  ``ACFLOW_FIELDS`` environment variable, separate the entries with ``;``

Fields the accession already has are kept, and a field whose specifier can't be
resolved is skipped.

Every later stage carries the fields through to its output unchanged, so
``select-fields`` can run at any point after ``label``. But ``deidentify`` doesn't
de-identify the fields: a field selected before it is deposited exactly as it was
selected. So select any field that could identify the subject *after* ``deidentify``.

``deidentify`` drops every metadata field from its output except the accession's UID,
so to select fields from de-identified data, keep the ones you need with its
``--metadata-allowlist`` option:

.. code-block:: console

    $ accessionflow deidentify /data/staging/labelled /data/staging/deidentified \
        /etc/accessionflow/deid-recipes --metadata-allowlist StudyDate

    $ accessionflow select-fields /data/staging/deidentified /data/staging/fields \
        --extract study_date StudyDate

The fields then hold the de-identified values, e.g. a ``StudyDate`` that the recipe has
shifted.
