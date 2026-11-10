.. _stage-package:

Package
=======

``package`` replaces the resources of one datatype with one or more named conversions of
them. Run it after :doc:`deidentify` when the data store needs derived resources but
de-identification should work on the unpacked source. Every output is converted
directly from that source, rather than from another output, so an archive and a sample
can be produced independently without reopening the archive.

.. code-block:: console

    $ accessionflow package INPUT_DIR OUTPUT_DIR SOURCE_DATATYPE \
        --output-resource <label> <target-spec> [--output-resource ...]

* ``INPUT_DIR`` — normally the output of ``deidentify``
* ``OUTPUT_DIR`` — where the packaged accessions are written; point ``store`` at it
* ``SOURCE_DATATYPE`` — the datatype of the resources to convert
* ``--output-resource <label> <target-spec>`` — a resource to produce from each matching
  source, and the datatype to convert it to. Repeatable. Converter options go after the
  target type, e.g. ``application/zip:allowZip64=false``. Converting a resource to its
  own type copies it, which keeps the original alongside the conversions

The input stays untouched unless ``--unlink-source`` is given (see
:ref:`concepts-unlink-source`), and a packaged accession only appears in the output once
every conversion and manifest has been written successfully. ``--on-resource-clash``
decides what happens when an output label clashes with another resource of the same
acquisition.

``package`` doesn't carry an accession's fields through to its output, so run
:doc:`select_fields` after it.


Example: a DICOM archive and a sample
-------------------------------------

With the Australian Imaging Service fileformat packages installed, a de-identified DICOM
directory can become a zip in XNAT's ``DICOM-zip`` resource and a single DICOM file in
the resource XNAT chooses from its SOP class (``DICOM`` for primary images,
``secondary`` for other DICOM), without reopening the zip.

Collate this workflow using ``medimage/dicom-dir``. Each input directory must contain
only one series and the files intended for its archive. Use ``--recursive`` if the
series directories are nested below the input path:

.. code-block:: console

    $ accessionflow collate folder /data/incoming /data/staging/collated \
        --datatype medimage/dicom-dir --recursive

``deidentify`` uses a ``medimage/dicom-dir`` recipe if there is one, and otherwise the
``medimage/dicom-series`` recipe and transforms. After labelling and de-identifying the
collated accessions, package them with the generic FileFormats ZIP converter:

.. code-block:: console

    $ accessionflow package /data/staging/deidentified /data/staging/packaged \
        medimage/dicom-dir \
        --output-resource DICOM-zip \
            medimage/dicom-dir+zip:compression=ZIP_STORED \
        --output-resource auto \
            medimage/vnd.australianimagingservice.dicom-sample

Packaging rejects samples from different DICOM studies in one accession. When it is
deposited with ``store xnat``, the scan is created from the sample's SOP class, the
archive is recorded as ``ZIP`` and the sample as ``DICOM``.

``package`` can also generate the snapshots XNAT shows for each scan, see
:ref:`store-xnat-snapshots`.
