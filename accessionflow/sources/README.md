# Source plugins

Each subpackage of `accessionflow.sources` adds support for one source of the
files that the `collate` stage collates into accessions, e.g.
`accessionflow/sources/folder` for folders on a local path or a mounted
file system, and `accessionflow/sources/orthanc` for an Orthanc server.

`accessionflow` and `accessionflow/sources` are namespace packages, so
neither may contain an `__init__.py`. That lets plugins be installed from
separate distributions, including editable installs, and still be found here.

A plugin package

- defines `SOURCE`, an `accessionflow.model.source.Source` that names the
  source, e.g. `Source(name="orthanc", title="Orthanc")`
- may have a `cli` subpackage, imported when the CLI first looks up a
  source's subcommand, that registers the plugin's `collate <source>`
  subcommand with `@accessionflow.cli.collate_group.command(name="orthanc")`,
  decorated with `@accessionflow.cli.collate_options` for the options that
  every source shares (`--loop`, `--copy-mode`, `--convert`,
  `--logger`, `--additional-logger` and `--raise-errors`)
- saves the accessions it collates into the staging directory, e.g. with
  `accessionflow.api.save_accessions_to_dir`, which saves each one directly
  into the staging directory

The store plugins in `accessionflow.stores` are found the same way.
