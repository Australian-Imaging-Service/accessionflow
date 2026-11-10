.. _sources:

Sources
=======

A source is where the files come from. The ``collate`` stage reads them from a source
and collates them into accessions, acquisitions and resources (see
:ref:`concepts-model`) in a staging directory, ready to be labelled. Each source
provides its own ``collate`` subcommand:

:doc:`folder`
    ``collate folder`` reads files from directories on a local path or a mounted file
    system, e.g. where an instrument exports to. It reads each file's metadata to decide
    which accession, acquisition and resource it belongs to, and works with any file
    format that `FileFormats <https://arcanaframework.github.io/fileformats/>`_ can read
    metadata from.
:doc:`orthanc`
    ``collate orthanc`` pulls the DICOM studies held by an `Orthanc
    <https://www.orthanc-server.com/>`_ server, for scanners that push to a PACS
    rather than exporting to a directory. It hardlinks the files out of Orthanc's
    storage rather than copying them.

Both write the same layout (see :ref:`concepts-staging`), so everything after
``collate`` works the same whichever source the data came from.

The sources share these options:

* ``--loop`` and ``--wait-period`` — run continuously, skipping anything still being
  transferred (see :ref:`concepts-looping`)
* ``--copy-mode`` — how files are copied into the staging directory, e.g. as hardlinks
  where possible (the default) or as copies
* ``--convert <src-mime-like> <tgt-spec>`` — convert resources of one format to another
  as they are collated, e.g. ``--convert medimage/dicom-series medimage/nifti-gz-x``.
  Converter options go after the target type, e.g.
  ``application/zip:compression=ZIP_STORED``
* ``--logger``, ``--additional-logger`` and ``--raise-errors`` — logging and error
  handling (see :ref:`concepts-looping`)

Run ``accessionflow collate --help`` to list the sources that are installed. Sources are
plugins, so a site can add its own (see :doc:`/developer/plugins`).
