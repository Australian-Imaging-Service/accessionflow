.. _store-folder:

Folder store
============

The ``folder`` data store deposits accessions in nested label folders, on a local path,
a mount, or a remote file system such as S3 or SFTP. Unlike XNAT, a folder store has no
fixed hierarchy: you name its levels, in order from the top, when labelling, along with
the metadata field each one is labelled from (see :ref:`concepts-specifiers`):

.. code-block:: console

    $ accessionflow label folder /data/staging/collated /data/staging/labelled \
        --level site SiteID \
        --level subject PatientID \
        --level visit '{StudyDate:%Y%m%d}'

    $ accessionflow store folder /data/staging/labelled s3://my-bucket/archive

    $ accessionflow check-store folder /data/staging/labelled s3://my-bucket/archive


Labelling
---------

* ``--level <name> <field>`` — a level of the hierarchy and the field it is labelled
  from. Repeat it for each level, from the top. Required. In the ``ACFLOW_LEVELS``
  environment variable, give the pairs separated by spaces
* ``--constant-label <name> <value>`` — fix the label of a level for everything the
  command labels, e.g. ``--constant-label site SYDNEY``. Repeatable
* ``--acquisition <field>`` — the field each acquisition is described by, which names
  its folder. Defaults to ``SeriesDescription``

See :doc:`/stages/label` for the options every ``label`` subcommand shares.


Layout
------

Each accession is deposited as:

.. code-block:: text

    <root>/<site>/<subject>/<visit>/<acq-id>.<acq-description>/<resource>/<files...>
                                                                         /__MANIFEST__.json
    <root>/<site>/<subject>/<visit>/__FIELDS__.json

The resources' manifests (the checksums of their files) and the accessions' fields (see
:doc:`/stages/annotate`) are deposited with them, but not their metadata. Each
manifest is written after the files it lists, so a resource with a manifest is
complete: depositing again skips resources that are already there, and finishes any
that an interrupted run left without one. A resource that is already in the store with
different files is reported as an error, unless ``--overwrite`` is given.


Remote file systems
-------------------

``DEST`` is a path or an `fsspec <https://filesystem-spec.readthedocs.io>`_ URL, e.g.
``/mnt/archive``, ``s3://bucket/archive`` or ``sftp://host/archive``. Remote file
systems need their fsspec package, installed with the ``s3`` or ``ssh`` extra, e.g.
``python3 -m pip install accessionflow[s3]``. Options for them, such as credentials, are
given with ``--storage-option <key> <value>``, e.g. ``--storage-option anon true``;
values that are JSON are decoded.


Checking the store
------------------

``check-store folder`` takes the same ``STAGED`` and ``DEST`` arguments and storage
options as ``store folder``. It reads every file back from the store to compare their
checksums with the staged manifests, or with ``--sizes-only`` just compares their sizes,
which is much cheaper. It logs every resource that is missing, incomplete or different,
and exits with a non-zero status if there are any.
