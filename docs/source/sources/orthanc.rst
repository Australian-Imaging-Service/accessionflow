.. _source-orthanc:

Orthanc
=======

If your scanner pushes to an `Orthanc <https://www.orthanc-server.com/>`_ instance
rather than exporting to a directory, ``collate orthanc`` takes the place of
``collate folder``. It queries Orthanc's REST API for studies and collates them into the
same layout that ``label`` reads (see :ref:`concepts-staging`), hardlinking the DICOM
files straight out of Orthanc's storage rather than copying them.

.. code-block:: console

    $ accessionflow collate orthanc http://localhost:8042 /var/lib/orthanc/db \
        /data/staging/collated orthanc-user orthanc-password

* ``URL`` — the Orthanc REST endpoint (``ACFLOW_ORTHANC_URL``)
* ``STORE_DIR`` — Orthanc's ``StorageDirectory``, as seen from wherever the command
  runs (``ACFLOW_ORTHANC_STORE_DIR``)
* ``OUTPUT_DIR`` — where the collated accessions are written
* ``USER``/``PASSWORD`` — Orthanc credentials
  (``ACFLOW_ORTHANC_USER``/``ACFLOW_ORTHANC_PASSWORD``)

Because the files are hardlinked, ``STORE_DIR`` and ``OUTPUT_DIR`` must be on the same
file system, and Orthanc's storage must be uncompressed. Compression is off by default,
so this only matters if you've enabled ``StorageCompression`` in the Orthanc
configuration. For the same reason, ``--copy-mode`` only supports its default.

Accessions are collated by ``StudyInstanceUID``, acquisitions by ``SeriesNumber``
(described by ``SeriesDescription``) and resources by ``ImageType``, following Orthanc's
own study/series/instance hierarchy. These groupings are fixed: there are no
``--accession-uid``/``--acquisition-id``/``--resource`` options like ``collate folder``'s. What
*metadata* is available to the ``label`` stage can be extended through the Orthanc
configuration however (see :ref:`source-orthanc-metadata`).

``--convert <src-mime-like> <tgt-spec>`` converts matching series as they are collated,
e.g. ``--convert medimage/dicom-series medimage/nifti-gz-x``. The source is always
``medimage/dicom-series``. Conversion happens before the processed label is applied, so
a study whose conversion fails is tried again on the next run.


.. _source-orthanc-labels:

Controlling which studies are collated
--------------------------------------

Which studies are collated, and collated only once, is controlled through Orthanc
*labels* rather than by moving or deleting anything:

* ``--to-process-label <label>`` — only studies carrying this label are collated. If
  unset, every study on the server is a candidate (``ACFLOW_ORTHANC_TO_PROCESS``)
* ``--processed-label <label>`` — applied to each study once it has been collated, and
  any study already carrying it is skipped on later runs (``ACFLOW_ORTHANC_PROCESSED``)

Removing the processed label from a study (e.g. through the Orthanc web UI) makes it
eligible to be collated again. ``--unlink-source`` is not yet implemented for
``collate orthanc``: the studies always stay in Orthanc, and the processed label is what
stops them being collated again.

A series that arrives after its study was collated is collated without a manual step.
When ``collate orthanc`` applies the processed label, it also applies a *snapshot
label*, ``<processed-label>-<LastUpdate>-<digest>``: the ``LastUpdate`` of the study
when it was collated, and a digest of the IDs of the instances it exported. On every
run, a processed study whose ``LastUpdate`` no longer matches its snapshot label (or
that has no snapshot label, from an older version) loses both labels and is collated
again in full. Later stages skip what they already hold, so the late series is the only
new data that moves on. A processed label makes the wait period at least one second, so
that a late instance always gets a later ``LastUpdate`` than the one collated.

The snapshot label is also what a retention tool can check before it deletes a study
from Orthanc: the exported instance set is the digest, and a changed ``LastUpdate``
shows that the study changed after it was collated.


.. _source-orthanc-fallbacks:

Missing series tags
-------------------

``collate orthanc`` doesn't refuse a study just because ``SeriesDescription`` or
``SeriesNumber`` is missing, empty or whitespace:

* A missing number becomes the ``SeriesInstanceUID`` with dots replaced by underscores,
  matching XNAT's header importer so that it updates the same scan. If that UID isn't in
  Orthanc's indexed tags, ``series_`` plus the full SHA-256 of Orthanc's series ID is
  used instead. The latter case hasn't been verified against XNAT's header importer.
  Both fallbacks are stable across retries on the same source.
* A missing description becomes ``Series_<acquisition-id>``. FrameTree, which
  ``store xnat`` uses to select resources, keys them by the acquisition's description
  and the resource's name, so two acquisitions both described as ``unknown`` would
  collide. The ``label`` stage keeps this fallback
  when the description is missing or empty, without treating an optional display tag as
  a missing field to label from.

A numeric zero is a valid number. Each fallback logs a ``series_metadata_fallback``
event with the ``orthanc_series_id``. These fallbacks don't repair missing study or
patient identity.


Studies that can't be collated
------------------------------

A study that can't be collated doesn't stop the others. Two series of one study that
map to the same acquisition and resource (the same ``SeriesNumber`` and
``SeriesDescription``), or one ``SeriesNumber`` used with two descriptions, are refused
before the study is published, since only one of them would survive in the staging
directory. The files already linked for the study's earlier series are discarded with
its build directory.

The study is logged as an error with its Orthanc ID and the reason, left without the
processed label, and tried again on the next run, so the error stays visible until the
study is corrected at the source. A study that changes while it is being collated is
logged as a warning and collated again on a later run.

Each study is built under ``__build__`` in the output directory before it is moved into
place. Run one ``collate orthanc`` per output directory: a retry removes its own stale
build, and converter processes that outlive their parent are outside this contract.


.. _source-orthanc-metadata:

Available metadata fields
-------------------------

Unlike ``collate folder``, which reads each file's full DICOM header,
``collate orthanc`` only sees the tags Orthanc itself indexes: the study-level
``MainDicomTags`` and ``PatientMainDicomTags``. These are what end up in the accession's
``__METADATA__.json``, and therefore what ``label`` can label from:

* study tags — ``StudyInstanceUID``, ``StudyID``, ``StudyDate``, ``StudyTime``,
  ``StudyDescription``, ``AccessionNumber``, ``InstitutionName``,
  ``ReferringPhysicianName``, ``RequestingPhysician``,
  ``RequestedProcedureDescription``
* patient tags — ``PatientID``, ``PatientName``, ``PatientBirthDate``, ``PatientSex``,
  ``OtherPatientIDs``
* ``Modality``, aggregated across the study's series

If the field you need isn't in that list (e.g. ``StudyComments``, the default field of
``label xnat``'s project), either label from one that is (e.g.
``--project RequestedProcedureDescription``), or add the tag to Orthanc's index with
``"ExtraMainDicomTags"`` in its configuration. That only applies to studies received
after the setting is in place, unless the existing ones are reconstructed.
