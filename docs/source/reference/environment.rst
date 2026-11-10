.. _environment:

Environment variables
=====================

Most arguments and options can be set by an environment variable instead of on the
command line, which suits long-running deployments (see :doc:`/deployment`): set
connection details and credentials once, e.g. from a Kubernetes ``Secret``, rather than
passing them on every invocation. An option given on the command line takes precedence
over its environment variable.

An option that takes several values reads them from its variable separated by spaces,
unless its help says otherwise (e.g. ``ACFLOW_FIELDS`` takes ``;``-separated entries).
A variable can set different options in different commands, e.g. ``ACFLOW_STAGED`` sets
``STAGED`` for ``store`` and ``INPUT_DIR`` for ``check-store xnat``; see the
:doc:`cli` for what each option does.

This table is generated from the installed commands, so it lists the variables of any
source and store plugins installed when the docs were built.

.. acflow-envvars::
