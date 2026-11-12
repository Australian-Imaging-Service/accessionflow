.. _plugins:

Writing source and store plugins
================================

The :ref:`sources <sources>` that ``collate`` reads from and the
:ref:`data stores <stores>` that accessions are deposited in are plugins, found by the
same mechanism:

* each source plugin is a subpackage of the ``accessionflow.sources`` namespace package,
  e.g. ``accessionflow.sources.orthanc``
* each store plugin is a subpackage of the ``accessionflow.stores`` namespace package,
  e.g. ``accessionflow.stores.xnat``

.. figure:: /_static/images/diagrams/accessionflow-architecture.svg
   :alt: accessionflow architecture: interfaces, core stages and data model, and source and store plugins
   :width: 100%
   :align: center

``accessionflow``, ``accessionflow.sources`` and ``accessionflow.stores`` are namespace
packages, so none of them may contain an ``__init__.py``. That lets plugins be installed
from separate distributions, including editable installs, and still be found. A plugin
package ``accessionflow-mysource`` only needs to ship an
``accessionflow/sources/mysource/`` directory.

A plugin package defines its configuration in its ``__init__.py``, and may have a
``cli`` subpackage that registers its subcommands. The CLI imports the ``cli``
subpackage of each installed plugin the first time it looks up one of a stage's
subcommands. A plugin that fails to import is skipped with a warning, so that one broken
plugin doesn't stop the others' commands from running. The folder source and store,
included with *AccessionFlow*, are short worked examples of each kind.


Source plugins
--------------

A source plugin

* defines ``SOURCE``, an :class:`accessionflow.model.source.Source` naming the source,
  e.g. ``Source(name="mysource", title="My source")``. The name is the subcommand's,
  ``collate mysource``
* registers ``collate <name>`` with ``@accessionflow.cli.collate_group.command(...)``,
  decorated with ``@accessionflow.cli.collate_options`` for the options every source
  shares (``--loop``, ``--wait-period``, ``--copy-mode``, ``--convert``, ``--logger``,
  ``--additional-logger`` and ``--raise-errors``)
* saves the accessions it collates into the staging directory in the layout the later
  stages read (see :ref:`concepts-staging`), e.g. by building
  :class:`~accessionflow.model.accession.Accession` objects that reference the files at
  the source and passing them to :func:`accessionflow.api.save_accessions_to_dir`, which
  builds each one under ``__build__`` and moves it into place once it is complete

For example:

.. code-block:: python

    # accessionflow/sources/mysource/__init__.py
    from accessionflow.model.source import Source

    SOURCE = Source(name="mysource", title="My source")

.. code-block:: python

    # accessionflow/sources/mysource/cli/__init__.py
    from pathlib import Path

    import click

    from accessionflow.cli import collate_group, collate_options

    from ..api import collate


    @collate_group.command(name="mysource", help="Collates files from my source")
    @click.argument("output_dir", type=click.Path(path_type=Path))
    @collate_options
    def collate_cmd(output_dir: Path, loop: int, **kwargs) -> None:
        ...


Store plugins
-------------

A store plugin

* defines ``STORE``, an :class:`accessionflow.model.store.Store` that names the store's
  label levels (e.g. XNAT's project, subject and session) and their default metadata
  fields, or leaves them to be named when labelling (``labels=None``, as the folder store
  does), and what the store calls an acquisition (e.g. XNAT's scan)
* registers ``label <name>`` by calling
  ``accessionflow.cli.make_label_command(STORE)``, which builds the subcommand from the
  store's label levels
* registers ``store <name>`` and ``check-store <name>`` with
  ``@accessionflow.cli.store_group.command(name=...)`` and
  ``@accessionflow.cli.check_store_group.command(name=...)``

``store`` should refuse an accession that was labelled for a different kind of store,
which is recorded in its ``store_type`` (see :ref:`concepts-labels`).


Checking a plugin is found
--------------------------

``accessionflow collate --help`` and ``accessionflow store --help`` list the installed
plugins' subcommands. Running a stage with a name that isn't installed says which
plugins are, e.g.:

.. code-block:: console

    $ accessionflow collate mysource ...
    Error: Cannot run 'collate mysource': no source plugin named 'mysource' is installed.
    Source plugins are subpackages of 'accessionflow.sources', e.g.
    'accessionflow.sources.mysource' (sources available for 'collate': folder, orthanc)
