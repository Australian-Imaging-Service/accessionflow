.. _data-model:

Data model: building your own tools
===================================

The staging directories ``accessionflow`` reads and writes at every stage are
deliberately plain and human-readable, rather than a database or an opaque
intermediate format (see :ref:`concepts-staging` for the layout, and
:ref:`concepts-model` for what accessions, acquisitions and resources are).

Nothing stops you from reading the JSON files directly, but the
:doc:`model classes </reference/api>` give you a typed, correct way to work with the
same structure, handling checksums, de-identification and staging consistently with the
stages:

* :class:`~accessionflow.model.accession.Accession` — a whole accession: its labels,
  acquisitions, accession-level resources, metadata and fields. Load an existing one
  from disk with :meth:`Accession.load <accessionflow.model.accession.Accession.load>`,
  or build one from files with :meth:`Accession.from_paths
  <accessionflow.model.accession.Accession.from_paths>`.
* :class:`~accessionflow.model.acquisition.Acquisition` — one acquisition (e.g. a scan)
  within an accession, and the resources attached to it.
* :class:`~accessionflow.model.resource.Resource` — one resource: a ``FileSet``, its
  checksums, and its metadata.

A minimal example of a custom script that loads a staged accession and inspects it:

.. code-block:: python

    from pathlib import Path

    from accessionflow.model.accession import Accession

    accession = Accession.load(Path("/data/staging/labelled/MYPROJECT.subject1.1"))

    print(accession.labels)  # e.g. {"project": "MYPROJECT", "subject": "subject1", ...}
    for acquisition_id, acquisition in accession.acquisitions.items():
        print(acquisition_id, acquisition.type, list(acquisition.resources))
        print(acquisition.metadata.get("SeriesDescription"))

The :doc:`API functions </reference/api>` that back each CLI subcommand are themselves
plain Python functions built on these model classes, so they can be called directly from
a script, without going through the CLI, if that's a better fit for what you're building.

These classes were previously named ``ImagingSession``, ``ImagingScan`` and
``ImagingResource``, in the ``xnat_ingest.model.session``, ``.scan`` and ``.resource``
modules.
