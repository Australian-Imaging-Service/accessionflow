.. _store-xnat:

XNAT
====

The ``xnat`` data store uploads accessions to an `XNAT <https://www.xnat.org/>`_
instance. XNAT has a fixed hierarchy: each accession becomes a *session*, within a
*subject*, within a *project*, and each of its acquisitions becomes a *scan*.

.. code-block:: console

    $ accessionflow label xnat /data/staging/collated /data/staging/labelled

    $ accessionflow store xnat /data/staging/labelled xnat.example.org \
        --user my-upload-user --password my-upload-password

    $ accessionflow check-store xnat /data/staging/labelled xnat.example.org \
        --user my-upload-user --password my-upload-password

*AccessionFlow* creates subjects, sessions, scans and resources as needed, but not
projects: create each project in XNAT before uploading to it.


.. _store-xnat-label:

Labelling
---------

``label xnat`` writes each accession to a ``<project>.<subject>.<session>`` directory.
The labels are taken from these metadata fields by default:

.. list-table::
    :header-rows: 1

    * - Label
      - Option
      - Default field
    * - project
      - ``--project``
      - ``StudyComments``
    * - subject
      - ``--subject``
      - ``PatientID``
    * - session
      - ``--session``
      - ``AccessionNumber``
    * - scan type
      - ``--scan``
      - ``SeriesDescription``

Override them if your scanner populates different fields. Any of them can be a format
string composing more than one field, e.g. ``--project '{PatientID}_{StudyDate:%Y}'``
(see :ref:`concepts-specifiers`). ``--constant-project-id <id>`` fixes the project for
everything the command labels, instead of taking it from a field.

See :doc:`/stages/label` for the options every ``label`` subcommand shares.


.. _store-xnat-store:

Uploading
---------

``store xnat`` takes the labelled accessions and uploads them:

* ``STAGED`` — the ``label`` output directory (or the output of a later stage), or an S3
  bucket URI (``ACFLOW_STAGED``)
* ``SERVER`` — the XNAT server address (``ACFLOW_HOST``)
* ``--user``/``--password`` — XNAT credentials (``ACFLOW_USER``/``ACFLOW_PASS``)
* ``--date <field>`` — when creating a session, set its date from the named metadata
  field (``ACFLOW_DATE``). Repeated values must all resolve to the same calendar date;
  existing sessions aren't changed

Credentials are read from the environment if the flags are omitted, so on a shared node
you'd typically set ``ACFLOW_HOST``, ``ACFLOW_USER`` and ``ACFLOW_PASS`` once in the
environment rather than passing them on every invocation.

``--always-include`` filters which resources are uploaded by their file type, e.g.
``--always-include medimage/dicom-series``. It defaults to ``all``, which uploads every
resource in the accession. The alternative is to define the expected columns for the
project with the `FrameTree <https://arcanaframework.github.io/frametree/>`_ tool, in
which case only data with a matching column in the dataset definition is uploaded.

The accession's fields (see :doc:`/stages/annotate`) are set as custom variables on
the session.

To attach session-level resources to an existing XNAT session, the staging directory
may be named with the session label alone. This works for local and S3 staging. The
label must match exactly one session that the upload account can access; no match or
several matches is an error. For example, ``000077/radiology-doc-report/report.pdf``
uploads into the ``radiology-doc-report`` resource of session ``000077``. Labelled
``<project>.<subject>.<session>`` directories continue to use their project, subject and
session labels.


.. _store-xnat-snapshots:

Generating scan snapshots
-------------------------

XNAT shows a snapshot and thumbnail for each scan on the session page.
:doc:`/stages/package` can generate them for non-DICOM scans by converting a resource to
``medimage/vnd.xnat.snapshots``, keeping the original files alongside. For example, to
show the PNG views of a lesion merged into one resource by
``--on-resource-clash merge image/png`` (see :ref:`source-folder-clashes`):

.. code-block:: console

    $ accessionflow package /data/staging/labelled /data/staging/packaged \
        image/png+set-of \
        --output-resource photos image/png+set-of \
        --output-resource snapshots medimage/vnd.xnat.snapshots

The first output passes the PNGs through unchanged, because converting a resource to its
own type copies it. The second tiles the PNGs, in file-name order, into a roughly square
grid without resizing them, then saves the grid and a smaller thumbnail as GIFs.
Converter options go after the target type, e.g.
``medimage/vnd.xnat.snapshots:thumbnail_size=128`` (the default is 256 pixels on the
longest side).

The label of the snapshots output doesn't matter. ``store xnat`` always stores snapshots
in the scan's ``SNAPSHOTS`` resource, marking the files as the ``ORIGINAL`` and
``THUMBNAIL`` images that XNAT displays, and ``check-store xnat`` looks for them there.

Only resources that match the source datatype are converted. An acquisition with just
one PNG holds an ``image/png`` resource, not an ``image/png+set-of``, so it gets no
snapshots from the command above.


.. _store-xnat-identity:

Session identity on reuse
-------------------------

An existing session label must belong to the expected subject. The uploader checks the
subject's internal XNAT ID through fresh REST responses, including for a subject shared
into the selected project.

The grouping identity is the ``__uid__`` value saved in the accession's metadata. It
works for DICOM and other formats; it is not XNAT's DICOM ``UID`` attribute. New
experiments include it in the custom field ``xnat_ingest_uid`` in the creation request,
then read it back. This field has no project UI form and is hidden from that UI by
default. It is not secret storage.

By default ``__uid__`` is the original accession UID, which for DICOM is its
``StudyInstanceUID``, and de-identification keeps it, so it is stored on XNAT. To replace
it with a keyed hash, give ``deidentify`` a private ``--hash-uid-key``
(``ACFLOW_HASH_UID_KEY``). The same UID and key always give the same hash, so don't
change the key. With ``--reid-dir``, both values are recorded in the re-identification
metadata.

Sessions already on XNAT hold their previous value, which a hashed UID won't match.
While moving to hashed UIDs, pass ``--no-uid-check`` (``ACFLOW_NO_UID_CHECK``) to
``store xnat`` and ``check-store xnat``. This skips only the UID comparison: the subject
is still checked where it is known, and the value on XNAT isn't changed, so these
sessions will be refused again once the option is removed unless their values are
updated. Uploads to a session named by its label alone have no known subject, so they
aren't checked at all with this option.

Before reuse or a completeness decision, the uploader reads this field again. A
different value, a duplicate field or an unreadable response refuses the upload and
keeps the staged copy. Local and S3 checks read only the accession's metadata; they
don't download DICOM headers to establish identity. Identity reads request
``Cache-Control: no-cache`` and ``Pragma: no-cache``.

An older experiment with no field is incomplete for the purpose of the skip check. In
the upload path, after the subject matches, the uploader warns that the old identity is
unverified, writes the incoming grouping identity, and reads it back before sending
files. This adoption does not prove that the old files belong to the incoming accession.
It never replaces a different existing value. Run one uploader per experiment: the read,
write and readback are not an atomic claim against concurrent writers.

Legacy local staging without ``__uid__`` keeps the subject check, but cannot establish
grouping identity or stamp this field. Uploads to a session named by its label alone
lack an expected subject, so they cannot adopt a missing remote identity; if supplied,
their local grouping identity must already match the remote field.


.. _store-xnat-check:

Checking what made it up
------------------------

``check-store xnat`` compares a staging directory against what's actually present on the
XNAT server and logs anything that's missing — useful to run after ``store xnat`` to
confirm nothing was dropped. It takes the same ``STAGED``/``SERVER``/credential options
as ``store xnat``. It doesn't support ``--loop``, so in a long-running deployment run it
on a schedule instead (see :doc:`/deployment`).
