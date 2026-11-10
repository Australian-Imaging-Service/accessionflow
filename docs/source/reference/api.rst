.. _api:

API
===

The following functions mirror the command-line tools, and can be called from a Python
workflow to run the same stages (see :doc:`/developer/data_model`).


Sources
~~~~~~~

.. autofunction:: accessionflow.sources.folder.api.collate

.. autofunction:: accessionflow.sources.orthanc.api.collate

.. autofunction:: accessionflow.api.save_accessions_to_dir


Stages
~~~~~~

.. autofunction:: accessionflow.api.attach

.. autofunction:: accessionflow.api.label

.. autofunction:: accessionflow.api.deidentify

.. autofunction:: accessionflow.api.package

.. autofunction:: accessionflow.api.select_fields_api.select_fields


Data stores
~~~~~~~~~~~

.. autofunction:: accessionflow.stores.folder.api.store

.. autofunction:: accessionflow.stores.folder.api.check_store

.. autofunction:: accessionflow.stores.xnat.api.store

.. autofunction:: accessionflow.stores.xnat.api.check_store


Model classes
~~~~~~~~~~~~~

These classes represent an accession as it moves through the stages: an accession
contains acquisitions, each of which contains one or more resources, e.g. the original
DICOM files and a derived NIfTI conversion (see :ref:`concepts-model`).

.. autoclass:: accessionflow.model.accession.Accession
    :members: uid, labels, store_type, name, acquisitions, session_resources, run_uid,
        metadata, fields, from_paths, label, deidentify, attach_files, save, load

.. autoclass:: accessionflow.model.acquisition.Acquisition
    :members: id, type, resources, attached, metadata, save, load

.. autoclass:: accessionflow.model.resource.Resource
    :members: name, fileset, checksums, acquisition, metadata, save, load

.. autofunction:: accessionflow.model.accession.recipe_formats_for


Plugin configuration
~~~~~~~~~~~~~~~~~~~~

.. autoclass:: accessionflow.model.source.Source

.. autoclass:: accessionflow.model.store.Store

.. autoclass:: accessionflow.model.store.LabelLevel
