.. _home:

AccessionFlow
=============
.. image:: https://github.com/australian-imaging-service/accessionflow/actions/workflows/ci-cd.yml/badge.svg
   :target: https://github.com/australian-imaging-service/accessionflow/actions/workflows/ci-cd.yml
.. image:: https://codecov.io/gh/australian-imaging-service/accessionflow/branch/main/graph/badge.svg?token=UIS0OGPST7
   :target: https://codecov.io/gh/australian-imaging-service/accessionflow
.. image:: https://img.shields.io/pypi/v/accessionflow.svg
   :target: https://pypi.python.org/pypi/accessionflow/
   :alt: Latest Version
.. image:: https://img.shields.io/github/stars/australian-imaging-service/accessionflow?label=GitHub
   :alt: GitHub stars
   :target: https://github.com/australian-imaging-service/accessionflow


*AccessionFlow* is a toolkit for capturing data from instruments and depositing it in
a data store, such as an XNAT instance or a folder hierarchy on a local disk or in an
S3 bucket.

Data files coming straight off a scanner or other instrument aren't organised the way
a data store expects, and — particularly on clinical scanners — often still carry
patient-identifying information that needs stripping before they leave clinical
control. *AccessionFlow* contains tools for each step of this process:

* Collating files from a source, such as a folder or an Orthanc server, into
  accessions, acquisitions and resources
* Labelling each accession with where it belongs in the data store, e.g. its XNAT
  project, subject and session
* De-identifying files using flexible, file-format-specific methods
* Depositing the labelled accessions in the data store, and checking that they all
  made it

Each of these is a separate stage that reads the previous stage's output directory and
writes its own, so the stages can be chained together and left running continuously as
services, picking up new files as they arrive:

.. code-block:: text

    collate <source>  →  [attach]  →  label <store>  →  [deidentify]  →  [package]
                      →  store <store>  →  check-store <store>

Where the files come from and where they go are both plugins: :ref:`sources <sources>`
provide the ``collate`` subcommands, and :ref:`data stores <stores>` provide the
``label``, ``store`` and ``check-store`` subcommands. The stages in between work the same
way whatever the source and store.

.. figure:: /_static/images/diagrams/accessionflow-overview.svg
   :alt: accessionflow overview: an instrument's data passes through collate, attach, label, deidentify, annotate, package and store stages into XNAT, a folder store or other repositories
   :width: 100%
   :align: center
   :figclass: only-light

.. figure:: /_static/images/diagrams/accessionflow-overview-dark.svg
   :alt: accessionflow overview: an instrument's data passes through collate, attach, label, deidentify, annotate, package and store stages into XNAT, a folder store or other repositories
   :width: 100%
   :align: center
   :figclass: only-dark

Start with the :doc:`quick_start`, which collates sample data and deposits it in a
folder store and then in XNAT, then see:

* :doc:`concepts` — the ideas every stage relies on
* :ref:`Sources <sources>` — collating from folders or an Orthanc server
* :ref:`Stages <stages>` — attaching, labelling, de-identifying and packaging
* :ref:`Data stores <stores>` — depositing in XNAT or a folder store
* :doc:`deployment` — running an accession flow continuously with Docker or Kubernetes
* :doc:`reference/cli` — the full command-line reference


Installation
------------

The recommended way to run *AccessionFlow*, particularly for a long-running node, is the
published Docker image, which bundles the CLI as its entrypoint along with all of its
external dependencies (e.g. dcm2niix, MRtrix3):

.. code-block:: console

    $ docker run ghcr.io/australian-imaging-service/accessionflow --help

See :doc:`deployment` for how this fits into Docker Compose or Kubernetes.

Alternatively, *AccessionFlow* can be installed for Python >=3.11 using *pip*:

.. code-block:: console

    $ python3 -m pip install accessionflow

Depositing in a folder store on S3 or over SFTP needs the ``s3`` or ``ssh`` extra, e.g.
``python3 -m pip install accessionflow[s3]``.

The command is ``accessionflow``, which these docs use throughout. ``acflow`` is
installed as a shorter alias for it, matching the ``ACFLOW_`` prefix of the
:doc:`environment variables <reference/environment>`.


License
-------

This work is licensed under the
`Apache License, Version 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`_


.. toctree::
    :maxdepth: 2
    :caption: Getting started
    :hidden:

    quick_start
    concepts

.. toctree::
    :maxdepth: 2
    :caption: Sources
    :hidden:

    sources/index
    sources/folder
    sources/orthanc

.. toctree::
    :maxdepth: 2
    :caption: Stages
    :hidden:

    stages/index
    stages/attach
    stages/label
    stages/deidentify
    stages/package
    stages/select_fields

.. toctree::
    :maxdepth: 2
    :caption: Data stores
    :hidden:

    stores/index
    stores/folder
    stores/xnat

.. toctree::
    :maxdepth: 2
    :caption: Running it
    :hidden:

    deployment

.. toctree::
    :maxdepth: 2
    :caption: Developer
    :hidden:

    developer/contributing
    developer/data_model
    developer/file_formats
    developer/plugins

.. toctree::
    :maxdepth: 2
    :caption: Reference
    :hidden:

    reference/cli
    reference/environment
    reference/api
