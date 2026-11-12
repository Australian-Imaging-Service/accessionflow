.. _quick-start:

Quick start
===========

This walks through a small accession flow on a synthetic sample DICOM series, so you don't
need real patient data to follow along. The series is collated once, then deposited
twice from the same collated copy: first in a folder store on your own disk, which
needs no server, then in an XNAT project. Only the ``label`` and ``store`` subcommands
change between the two, since collation doesn't depend on where the data is going.

See :doc:`concepts` for what each stage does, and :doc:`reference/cli` for every option.


1. Install
----------

.. code-block:: console

    $ python3 -m pip install accessionflow medimages4tests

`medimages4tests <https://github.com/Australian-Imaging-Service/medimages4tests>`_
generates synthetic DICOM series for exactly this kind of test-drive.


2. Get some sample data
-----------------------

.. code-block:: console

    $ python3 -c "
    from medimages4tests.dummy.dicom.mri.t1w.siemens.skyra.syngo_d13c import get_image
    print(get_image())
    "

This prints the path to a directory of DICOM files for a synthetic T1-weighted MRI
scan (downloaded and cached the first time it's run). Substitute your own directory of
DICOM files if you have some handy.


3. Collate
----------

Collate the files into accessions, acquisitions and resources:

.. code-block:: console

    $ accessionflow collate folder /path/to/dicom/series /tmp/quickstart/collated

DICOM files are grouped into an accession per study (``StudyInstanceUID``) and an
acquisition per series (``SeriesNumber``) by default. ``/tmp/quickstart/collated`` now
holds one accession, in a directory named ``_.`` followed by its study's UID.


4. Deposit in a folder store
----------------------------

A folder store has no fixed hierarchy, so you name its levels when labelling, along with
the metadata field each one is labelled from. Here the accession is filed by subject and
then by the date of the study:

.. code-block:: console

    $ accessionflow label folder /tmp/quickstart/collated /tmp/quickstart/labelled-folder \
        --level subject PatientID --level visit StudyDate

    $ accessionflow store folder /tmp/quickstart/labelled-folder /tmp/quickstart/archive

    $ accessionflow check-store folder /tmp/quickstart/labelled-folder /tmp/quickstart/archive

``/tmp/quickstart/archive`` now holds the series in a folder per label, then per
acquisition and resource, with a manifest of the files' checksums:

.. code-block:: text

    archive/
        Session_Label/                         # subject (PatientID)
            20180525/                          # visit (StudyDate)
                2.t1_mprage_sag_p2_iso_1/      # acquisition: <SeriesNumber>.<SeriesDescription>
                    DICOM/                     # resource
                        0.dcm  1.dcm  ...
                        __MANIFEST__.json

``check-store folder`` reads every file back and reports anything missing or
different. The destination could just as well be an S3 bucket
(``s3://my-bucket/archive``) — see :doc:`stores/folder`.


5. Deposit in XNAT
------------------

If you already have an XNAT instance and a project to upload to, skip the next command.
Otherwise, `xnat4tests <https://github.com/Australian-Imaging-Service/xnat4tests>`_ can
launch a disposable XNAT instance in a Docker container:

.. code-block:: console

    $ python3 -m pip install xnat4tests
    $ xnat4tests start

This starts XNAT at ``http://localhost:8080`` with the credentials ``admin``/``admin``.
Either way, log in to the web interface and create a project (e.g. ``MYPROJECT``) to
upload to — *AccessionFlow* doesn't create projects itself.

XNAT's hierarchy is fixed (project, subject and session), so ``label xnat`` has an
option for each level instead of ``--level``. The sample data doesn't populate
``StudyComments`` or ``AccessionNumber``, the fields ``label xnat`` uses for the project
and session by default, so fix the project and take the session from the
``StudyInstanceUID`` instead (see :doc:`stores/xnat` for the defaults):

.. code-block:: console

    $ accessionflow label xnat /tmp/quickstart/collated /tmp/quickstart/labelled-xnat \
        --constant-project-id MYPROJECT --session StudyInstanceUID

    $ accessionflow store xnat /tmp/quickstart/labelled-xnat http://localhost:8080 \
        --user admin --password admin

    $ accessionflow check-store xnat /tmp/quickstart/labelled-xnat http://localhost:8080 \
        --user admin --password admin

Open ``MYPROJECT`` in the XNAT web interface and you should see a new subject and
session containing the uploaded scan.


Next steps
----------

* :doc:`stages/deidentify` — strip patient-identifying data before it is deposited
* :doc:`sources/orthanc` — collate straight from an Orthanc server instead of a folder
* :doc:`deployment` — leave the stages running continuously
