.. _stores:

Data stores
===========

A data store is where the accessions are deposited at the end of the pipeline. Each
store provides three subcommands:

``label <store>``
    labels each accession with where it belongs in the store, using the store's own
    label levels (see :doc:`/stages/label`)
``store <store>``
    deposits the labelled accessions in the store
``check-store <store>``
    checks what has been deposited against the staging directory it was deposited
    from, and reports anything that is missing or different

Two stores are included:

:doc:`folder`
    A hierarchy of nested label folders on a local path, a mount, or a remote file
    system such as S3 or SFTP. You name its levels when labelling, so it can hold any
    kind of data in whatever layout suits it. It needs no server, so it is also the
    quickest way to try *AccessionFlow* out.
:doc:`xnat`
    An `XNAT <https://www.xnat.org/>`_ instance, with its fixed hierarchy of projects,
    subjects and sessions, each session holding scans and resources.

An accession is labelled for one kind of store (see :ref:`concepts-labels`), so the
``label``, ``store`` and ``check-store`` subcommands used for an accession must all be
for the same store. To deposit the same data in two stores, label it twice from the
same collated directory, as in the :doc:`/quick_start`.

``store`` and ``check-store`` can read the labelled accessions from a local staging
directory or from an S3 bucket (``s3://...``), downloading them to ``--temp-dir`` with
the ``--store-credentials`` given.

Run ``accessionflow store --help`` to list the stores that are installed. Stores are
plugins, so a site can add its own (see :doc:`/developer/plugins`).
