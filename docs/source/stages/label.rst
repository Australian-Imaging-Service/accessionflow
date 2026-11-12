.. _stage-label:

Label
=====

``label <store>`` reads the collated accessions and works out where each one belongs in
the data store, from its metadata, writing the labelled accessions to ``OUTPUT_DIR`` in
directories named by their labels (see :ref:`concepts-labels`). Each data store provides
its own subcommand, since each has its own label levels:

.. code-block:: console

    $ accessionflow label xnat /data/staging/collated /data/staging/labelled

    $ accessionflow label folder /data/staging/collated /data/staging/labelled \
        --level site SiteID --level subject PatientID

* ``INPUT_DIR`` — the ``collate`` output directory, or the output of ``attach`` if it
  ran after ``collate`` (``ACFLOW_INPUT_DIR``)
* ``OUTPUT_DIR`` — where the labelled accessions are written (``ACFLOW_OUTPUT_DIR``)

Each label is taken from a metadata field, or composed from several with a format
string, e.g. ``--subject '{PatientID}_{StudyDate:%Y}'`` (see
:ref:`concepts-specifiers`). This is the part of an accession flow most likely to need
adjusting for each site, since instruments populate different fields:

* :doc:`/stores/xnat` has an option for each of its levels, ``--project``,
  ``--subject`` and ``--session``, with defaults for DICOM, and ``--constant-project-id``
  to fix the project for everything a command labels
* :doc:`/stores/folder` has no fixed levels, so you name each one and the field it is
  labelled from with ``--level <name> <field>``, from the top, and can fix any of them
  with ``--constant-label <name> <value>``

Labelling also describes each acquisition, from ``SeriesDescription`` for DICOM by
default. The option is named after what the store calls an acquisition: ``--scan`` for
XNAT and ``--acquisition`` for a folder store. An acquisition whose description can't be
resolved is left without one.

An accession whose labels can't all be resolved is saved under ``__invalid__`` rather
than dropped (see :ref:`concepts-invalid`). ``--unlink-source`` removes the collated
input once an accession has been labelled (see :ref:`concepts-unlink-source`), and
``--loop`` keeps the stage running (see :ref:`concepts-looping`).


.. _stage-label-include:

Routing datatypes through separate labelling pathways
-----------------------------------------------------

Use repeatable ``--include`` options when different datatypes from one collated accession
need different labels, e.g. different projects. Each ``label`` command reads the same
collated input and writes only the matching resources:

.. code-block:: console

    $ accessionflow label xnat /data/staging/collated /data/staging/dicom-labelled \
        --include medimage/dicom-series --constant-project-id DICOM_PROJECT

    $ accessionflow label xnat /data/staging/collated /data/staging/report-labelled \
        --include application/pdf --constant-project-id REPORT_PROJECT

Multiple ``--include`` options match any of their datatypes. Filtering by datatype can't
be combined with ``--unlink-source``, because the collated data must remain available to
every labelling pathway.
