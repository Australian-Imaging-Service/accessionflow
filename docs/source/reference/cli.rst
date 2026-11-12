.. _cli:

Command-line interface
======================

*AccessionFlow*'s command-line interface is a set of subcommands of the
``accessionflow`` command (or its shorter alias, ``acflow``). See :doc:`/concepts` for
how they fit together into a pipeline.

The ``collate`` stage has a subcommand for each :ref:`source <sources>`, e.g.
``accessionflow collate folder``, and the ``label``, ``store`` and ``check-store``
stages have one for each :ref:`data store <stores>`, e.g. ``accessionflow label xnat``.
Most options can also be set by environment variables, listed in
:doc:`environment`.


Sources
-------

.. click:: accessionflow.sources.folder.cli.collate_cli:collate_cmd
   :prog: accessionflow collate folder

.. click:: accessionflow.sources.orthanc.cli.collate_cli:collate_cmd
   :prog: accessionflow collate orthanc


Stages
------

.. click:: accessionflow.cli.attach_cli:attach_cmd
   :prog: accessionflow attach

.. click:: accessionflow.cli.deidentify_cli:deidentify_cmd
   :prog: accessionflow deidentify

.. click:: accessionflow.cli.package_cli:package_cmd
   :prog: accessionflow package

.. click:: accessionflow.cli.annotate_cli:annotate_cmd
   :prog: accessionflow annotate


Folder store
------------

.. click:: accessionflow.stores.folder.cli.label_cli:label_cmd
   :prog: accessionflow label folder

.. click:: accessionflow.stores.folder.cli.store_cli:store_cmd
   :prog: accessionflow store folder

.. click:: accessionflow.stores.folder.cli.check_store_cli:check_store_cmd
   :prog: accessionflow check-store folder


XNAT
----

.. click:: accessionflow.stores.xnat.cli.label_cli:label_cmd
   :prog: accessionflow label xnat

.. click:: accessionflow.stores.xnat.cli.store_cli:store_cmd
   :prog: accessionflow store xnat

.. click:: accessionflow.stores.xnat.cli.check_store_cli:check_store_cmd
   :prog: accessionflow check-store xnat
