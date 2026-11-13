.. _push:

Pushing to a central staging area
=================================

A pipeline doesn't have to run on one machine. A common layout is an *edge* node beside
the instruments that collates, labels and de-identifies the data, and a central node
that deposits it in the data store. ``push`` copies the edge's staging directory to a
staging area both can reach, e.g. an S3 bucket, and the central node's ``store`` reads
the accessions from there:

.. code-block:: console

    # on the edge node
    $ accessionflow push /data/staging/deidentified s3://my-bucket/staged \
        --storage-option endpoint_url https://s3.example.org

    # on the central node
    $ accessionflow store xnat s3://my-bucket/staged xnat.example.org

* ``STAGED`` — the staging directory to push, e.g. the output of ``label`` or
  ``deidentify`` (``ACFLOW_STAGED``)
* ``DEST`` — the staging directory to copy it to, a path or an `fsspec
  <https://filesystem-spec.readthedocs.io>`_ URL, e.g. ``s3://bucket/staged``,
  ``sftp://host/staged`` or a mounted path (``ACFLOW_DEST``). Remote file systems need
  their fsspec package, installed with the ``s3`` or ``ssh`` extra, e.g.
  ``python3 -m pip install accessionflow[s3]``
* ``--storage-option <key> <value>`` — options for the destination's file system, such
  as its endpoint or credentials (see :doc:`stores/folder` for how they are given)

Each accession is copied to ``DEST/<accession>/`` in the same layout as the staging
directory (see :ref:`concepts-staging`), metadata, fields and manifests included, so
the next stage can read it from there as it would from a local staging directory.
Links are followed, so the files they point to are copied, and an accession with a
link whose target has gone isn't pushed at all.

Like the other stages, ``push`` takes ``--loop`` and ``--wait-period`` to run
continuously (see :ref:`concepts-looping`). When it starts, it tries to list the
destination, by default 12 times, 5 seconds apart (``--probe-attempts``), and refuses
to start if it can't, so an endpoint that is down or credentials that can't see the
destination are reported clearly rather than as an error for every accession.


.. _push-complete:

Complete copies
---------------

The destination is the record of what has been pushed, so nothing needs to be kept
locally:

* a resource's manifest is written after its files, so a resource with a manifest at
  the destination is a complete copy
* the accession's metadata (``__METADATA__.json``) is written after everything else, so
  a reader can treat an accession without it as one that is still being pushed
* a resource whose manifest and file sizes at the destination match the staged ones is
  skipped, so pushing again only copies what is missing, was left incomplete by an
  interrupted push, or has changed since it was pushed

``push`` never deletes the staged accessions, and never deletes anything at the
destination except the files of a resource that it is replacing with a changed one.
Cleaning up either side is left to whatever reclaims them.

``check-push`` checks what has been pushed against the staging directory, reading every
file back to compare its checksum with the staged manifest, or with ``--sizes-only``
just comparing sizes. It logs every resource that is missing, incomplete or different,
and exits with a non-zero status if there are any, so a process that reclaims the
staged copies can run it to decide which are safe to delete.


.. _push-compatibility:

Compatibility with ais-edge's reclaimer
---------------------------------------

``push`` replaces the ``s3-uploader`` script of `ais-edge
<https://github.com/Australian-Imaging-Service/ais-edge>`_. Until ais-edge's reclaimer
and data-policy engine check the destination with ``check-push`` themselves, these
options keep them working as they did with the script:

``--marker-dir``
    writes a marker for each accession once it has been pushed, holding the same
    fingerprint of its staged files as the script did (the MD5 of their sorted relative
    paths, sizes and modification times), and skips an accession whose marker matches
    without checking the destination. A marker is removed once no stage directory
    under ``--marker-root`` (by default the parent of ``STAGED``) holds an accession of
    its name.
``--recopy-dir``
    where the reclaimer asks for an accession to be copied again in full, with a file
    named after it. The request is claimed by renaming it to ``<name>.claimed``, removed
    once the copy succeeds, and put back if it fails.
``--lock-file`` and ``--lock-wait``
    a lock file held with ``flock`` while each accession is copied, so it isn't copied
    while the writer or the reclaimer holds the same lock. If it isn't free within
    ``--lock-wait`` seconds (600 by default), the accession is skipped until the next
    pass; any other failure to take the lock stops the command.

Without them, the destination decides what is pushed. One consequence to be aware of
before dropping them: if something deletes accessions at the destination, e.g. once
the central node has deposited them, while the edge still holds its staged copies,
the next ``push`` copies them again, since nothing at the destination says they were
ever there. The markers are what prevent that today.
