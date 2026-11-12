# Stage plugins (work in progress)

**Status:** idea, not started. Recorded 2026-11-12.

## Goal

Let users add their own pipeline stages as plugins, in the same way that sources
(`accessionflow.sources`) and data stores (`accessionflow.stores`) are plugins. A
plugin stage should be usable everywhere a core stage is:

- as a top-level CLI command, e.g. `accessionflow radiomics ...`
- in a workflow spec, referenced by `command:` exactly like the core stages:

  ```yaml
  stages:
    - name: features
      command: radiomics      # resolved the same way as `deidentify`
      input: deidentify
      args: {copy_mode: copy}
  ```

## Current state

- Sources and stores are subpackages of namespace packages. Each declares a descriptor
  (`SOURCE` / `STORE`) in its `__init__.py`, and may have a `cli` subpackage that
  registers its subcommands. Discovery is in `accessionflow/helpers/plugins.py`
  (`plugin_names`, `get_plugin`, `load_cli_plugins`). See
  `docs/source/developer/plugins.rst`.
- The workflow syntax is on the `prefect-workflow` branch. There,
  `accessionflow/workflow/stages.py` holds a hard-coded `STAGES` dict that maps each
  `command:` to a `Stage(api_fn, build_kwargs, coerced_args, input_arg,
  takes_output_dir, ...)`. `workflow/spec.py` rejects any `command` not in
  `STAGE_NAMES`.
- `prefect-workflow` is behind `main` (by 43 commits as of 2026-11-12). It still uses
  the old names `repositories`, `collate-orthanc` and `upload`, from before
  sources and stores became plugins, and before `select-fields` was renamed
  `annotate` and `push` was added.

## Proposed design

### 1. The `accessionflow.stages` namespace

Each stage plugin is a subpackage `accessionflow.stages.<name>`, found the same way as
source and store plugins (`plugin_names` / `get_plugin` / `load_cli_plugins` with
package `"accessionflow.stages"`). Like `accessionflow/sources` and
`accessionflow/stores`, `accessionflow/stages` is a namespace package: no
`__init__.py`, only a `README.md`, so that plugins can be installed from separate
distributions.

The name is `stages` rather than `external` because it says what the plugins
provide, and sources and stores are just as "external".

### 2. A `STAGE` descriptor per plugin

Like `SOURCE` and `STORE`, each plugin declares its stage in its `__init__.py`. Both
the CLI and the workflow runner read this descriptor:

```python
# accessionflow/stages/radiomics/__init__.py
from accessionflow.model.stage import Stage
from accessionflow.helpers import coerce
from .api import radiomics

STAGE = Stage(
    name="radiomics",              # the CLI command and the workflow `command:`
    api_fn=radiomics,              # (input_dir, output_dir, **args) -> list[str] errors
    coerce={"copy_mode": coerce.copy_mode},   # args parsed from YAML/CLI strings
)
```

### 3. One registry for core and plugin stages

Move `Stage` from `workflow/stages.py` to `accessionflow/model/stage.py`, and declare
the core stages with the same class. Commands are then resolved by
`get_stage(command)`, which looks in the core stages first and then in
`accessionflow.stages.<command>`. This is what makes plugin stages referenceable
"like the core stages": there is only one lookup.

- `spec.py` validates against core plus installed plugin stages. Its "expected one of
  ..." error lists both.
- Core names win. A plugin that reuses a core name (e.g. `deidentify`) is skipped
  with a warning, as a plugin that fails to import is now.

### 4. A small plugin contract

At the moment every core stage has a hand-written `build_kwargs`. For plugins the
default should be convention-based:

- `input_dir` and `output_dir` are injected from the stage's `input:` and the
  workflow's work directory (`takes_output_dir=False` for terminal stages)
- `coerce` maps argument names to parsers. `coerced_args` is derived from its keys,
  which `spec._resolve_stage_args()` needs.
- all other args pass straight through. The existing `inspect.signature` check in
  `spec.py` already catches unknown or missing arguments.

`build_kwargs` stays available as an escape hatch for stages with quirks (as
`collate` and `label` have now).

### 5. The CLI

- The root `cli` group becomes a `click.Group` subclass that loads stage plugins
  lazily: only when a command isn't built in, or for `--help`. Built-in commands
  don't pay the import cost or see plugin warnings.
- Its `add_command` refuses a name that is already registered, so a plugin can't
  shadow a core command.
- For an unknown command, the error hints that stage plugins are subpackages of
  `accessionflow.stages`, as `PluginGroup.resolve_command` does for sources and
  stores.
- To start with, a plugin registers its command in an optional `cli` subpackage
  (`@accessionflow.cli.cli.command(name=...)`). Later, the command could be
  generated from the `STAGE` descriptor, so that authors only write the API function.
- A shared `stage_options` decorator, like `collate_options` (`--loop`, `--logger`,
  `--additional-logger`, `--raise-errors`), would save plugins from copying these
  options. The built-in stages currently each declare them.

### 6. Sources and stores in workflows

When `prefect-workflow` is rebased, `collate-orthanc` and `upload` become `collate`
with `source: orthanc` and `store` with `store: xnat`, resolved through the existing
source and store plugin lookups. Everything a workflow spec references is then
either a core stage or a plugin, found the same way.

## Plan

1. Rebase `prefect-workflow` onto `main`, porting it to sources/stores, `annotate`
   and `push`.
2. On a branch from there: add `model/stage.py`, move the core stages onto the
   `Stage` descriptor, and add the `accessionflow/stages` namespace, `get_stage()`
   and the root-group lazy loading.
3. Tests: a fake plugin stage put on `sys.path` in a temporary directory, checked to
   - run from the CLI
   - run from a workflow YAML spec
   - not be able to shadow a core stage name
   - be skipped with a warning if it fails to import
4. Docs: add a "Stage plugins" section to `docs/source/developer/plugins.rst`.

## Open questions

- Should step 2 go on `main` first, with `prefect-workflow` adopting it on rebase?
- Should plugin CLI commands be generated from `STAGE` from the start, rather than
  written by hand?
- Do plugin stages need to declare anything else the runner relies on, e.g. whether
  they need the staging-directory layout of a particular earlier stage?
