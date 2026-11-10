.. _source-folder:

Folders
=======

``collate folder`` reads files from directories on a local path or a mounted file
system, reads each file's metadata (DICOM tags by default), and collates the files into
accessions, acquisitions and resources in ``OUTPUT_DIR``, ready to be labelled (see
:ref:`concepts-staging` for the layout).

.. code-block:: console

    $ accessionflow collate folder /data/incoming/*.dcm /data/staging/collated

* ``INPUT_PATHS`` — one or more directories, or glob patterns that select the files
  directly (``ACFLOW_INPUT_PATHS``)
* ``OUTPUT_DIR`` — where the collated accessions are written (``ACFLOW_OUTPUT_DIR``)

Add ``--unlink-source all`` to remove each source file once it has been collated (see
:ref:`concepts-unlink-source`).


.. _source-folder-grouping:

Grouping files into accessions, acquisitions and resources
----------------------------------------------------------

Three options decide which accession, acquisition and resource each file belongs to,
each taking a :ref:`specifier <concepts-specifiers>` and the datatype it applies to:

* ``--session`` — files with the same value are collated into the same accession.
  Defaults to ``StudyInstanceUID`` for DICOM
* ``--scan`` — files with the same value are collated into the same acquisition.
  Defaults to ``SeriesNumber`` for DICOM. If no ``--scan`` spec matches a fileset, its
  acquisition is named after its resource
* ``--resource`` — names the resource. If no ``--resource`` spec matches a fileset, its
  resource is named after its type, e.g. ``dicom-series`` or ``vectra-export``

There are no defaults for formats other than DICOM. Each option can be repeated to treat
datatypes differently.

Non-DICOM data (raw exports, image files, vendor directory formats) needs ``--datatype``
set to the relevant `FileFormats <https://arcanaframework.github.io/fileformats/>`_
MIME-like type(s), and usually its own ``--session``/``--scan``/``--resource`` specs,
since the DICOM defaults won't apply. Any format that FileFormats can read metadata from
can be collated (see :doc:`/developer/file_formats`).


.. _source-folder-path-metadata:

Pulling extra metadata from file and directory paths
----------------------------------------------------

Not everything you need is necessarily readable from a file's own headers: a raw format
might carry no metadata at all, or your incoming data might already be organised into
directories that encode something useful (a cohort label, a scanner ID, ...) that never
made it into the DICOM tags. ``--path-metadata-regex`` pulls extra metadata fields out
of a resource's own file or directory path instead, through the named groups of a Python
regular expression. It is often the easiest way to get a field that the data store needs
(e.g. a project ID) when the instrument itself doesn't write it anywhere in the file:

.. code-block:: console

    $ accessionflow collate folder /data/incoming/cohort-A /data/staging/collated \
        --path-metadata-regex '.*/(?P<cohort>[^/]+)$' medimage/dicom-series

Here, anything found under a ``.../cohort-A/...`` directory gets a ``cohort`` metadata
field set to ``cohort-A``, alongside whatever is read from its DICOM headers. It can be
used anywhere a metadata field can, e.g. in a ``--project`` or ``--level`` specifier
when labelling.

* The regex is matched (with ``re.match``, so from the start of the string, but not
  necessarily the whole of it unless you anchor it with ``$`` as above) against the
  resource's own directory, or its file path for single-file formats, not against the
  whole ``INPUT_PATHS`` argument.
* The second argument restricts which datatype the pattern applies to. It is matched
  with ``isinstance``, so a broader datatype like ``medimage/dicom-collection`` also
  matches ``medimage/dicom-series``.
* It can be repeated for different datatypes and patterns.
* If a resource matches the datatype but its path doesn't match the regex, that's a
  hard error: it aborts the whole run rather than skipping that one accession, so keep
  the pattern narrow enough that it only applies to data you know follows the
  convention.


.. _source-folder-metadata-tables:

Joining metadata from a table
-----------------------------

``--metadata-table <path> <row-frequency> <join-exprs>`` merges the columns of a CSV or
TSV table into the metadata, e.g. a spreadsheet exported alongside the images:

* ``<path>`` — the table. Its format is detected from its extension; a different format
  can be forced by appending its MIME type in square brackets, e.g.
  ``path/to/table.dat[text/csv]``
* ``<row-frequency>`` — what each row describes: ``session``, ``scan``, ``resource``,
  ``fileset``, or ``fileset[<mime-type>]`` to join only files of those types (several can
  be ``|``-separated, e.g. ``fileset[image/png|image/jpeg]``)
* ``<join-exprs>`` — a comma-separated list of ``<column-name>=<cell-value>``
  expressions, all of which must hold for a row to match. A ``<cell-value>`` is a
  metadata field, or a format string over several, e.g. ``{PatientID}_{SessionID}``

All the columns of the matching row are merged into the target's metadata. This
example extracts the relative path of each image with ``--path-metadata-regex`` and
uses it to join a table whose ``ImagePath`` column holds spreadsheet ``HYPERLINK()``
formulas:

.. code-block:: console

    $ accessionflow collate folder ... \
        --path-metadata-regex '.*/(?P<relpath>[\w-]+/[\w-]+\.(?:png|jpg))' 'image/png|image/jpeg' \
        --metadata-table path/to/table.csv[text/csv] 'fileset[image/png|image/jpeg]' \
            'ImagePath=HYPERLINK("{relpath}")'


.. _source-folder-recursive:

Recursing into nested directory formats
---------------------------------------

``--recursive`` descends into the input directories. For plain file datatypes it just
flattens the tree. When a ``--datatype`` (or ``--ignore-datatype``) is a *directory*
format, the walk instead stops descending into a directory as soon as it validates as
one of them: a ``--datatype`` match is taken whole (its contents are never looked at
individually), an ``--ignore-datatype`` match is skipped whole, and anything else is
descended. This is how you pull a nested directory format out of a larger vendor
export:

.. code-block:: console

    $ accessionflow collate folder /data/incoming /data/staging/collated --recursive \
        --datatype medimage/vnd.canfield.whole-body-analysis-dir \
        --datatype medimage/vnd.canfield.dexi-data-dir \
        --exclude-path '*/*/*.png'

``generic/directory`` and ``generic/file-set`` can't be used as a ``--datatype`` with
``--recursive``, since they match every directory, at every depth.


.. _source-folder-skip:

Deciding what to skip
---------------------

Anything found under the input paths that no ``--datatype`` recognises is a hard error
by default. Three options relax that, from most to least targeted:

* ``--exclude-path <glob>`` drops a path *before* it is classified, matching the path
  **relative to its input directory**. So it removes a path even if a ``--datatype``
  would have claimed it, e.g. a vendor thumbnail that happens to be a valid
  ``image/png`` three directories deep, while keeping your real ``image/png`` two deep.
  ``*`` does not cross ``/``, ``**`` does. Repeatable.
* ``--ignore-datatype <mime>`` names a datatype that *is* recognised but isn't wanted:
  its filesets are dropped from the result, and (with ``--recursive``) matching
  directories are skipped without descending. Repeatable.
* ``--allow-unrecognised <regex>`` matches the **basename** of any leftover path that no
  datatype recognised, and skips it instead of raising. ``--allow-unrecognised '.*'``
  tolerates every stray file. It never affects a recognised fileset.

A path that matches none of these, nor a ``--datatype``, still aborts the run.


.. _source-folder-clashes:

Handling resource-name clashes
------------------------------

If two filesets resolve to the same acquisition and resource name, the run aborts unless
you say what to do about it. ``--on-resource-clash`` takes ``<policy> <scope>`` and is
repeatable; a clash is resolved by the first entry whose ``<scope>`` (a MIME-like, a
``|``-union, or ``all``) covers **both** filesets:

* ``merge`` folds them into a single ``SetOf[...]`` resource, e.g. the PNG and JPEG
  views of one lesion, with ``--on-resource-clash merge 'image/png|image/jpeg'``
* ``avoid`` appends a ``__2``/``__3`` suffix
* ``overwrite`` replaces the existing resource

A clash that no entry's scope covers (e.g. a PNG colliding with a directory format)
always raises. Tighten ``--scan``/``--resource`` so the two don't collide, or add a scope
that deliberately covers both.


.. _source-folder-layout:

Laying out the files of a resource
----------------------------------

``--collate-resources <mime-type> <collation>`` flattens the files of a datatype into
their resource directory as they are collated, regardless of how they were laid out at
the source. ``<collation>`` is one of ``any``, ``siblings`` or ``adjacent`` (the default
is ``siblings``).


Series without numbers
----------------------

The default ``--scan`` spec, ``SeriesNumber``, must resolve for every DICOM series. For
sources that don't number their series, give an explicit
``--scan SeriesInstanceUID medimage/dicom-collection`` instead. (``collate orthanc``
falls back to the ``SeriesInstanceUID`` automatically, see :ref:`source-orthanc-fallbacks`.)
