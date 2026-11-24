# Prefect migration roadmap

AccessionFlow is moving to a workflow orchestrated by [Prefect](https://www.prefect.io/).
Each stage is driven today by one or two large API functions (`collate()`, `label()`,
`deidentify()`, `package()`, `store()`, …). Prefect needs smaller units to give each
piece of work its own retries, state and per-accession fan-out. Each large function is
therefore split into many small, single-purpose **step functions**.

- The step functions live in this repository, in the `api` packages of the core and of
  the source and store plugins.
- Prefect tasks and flows that wrap them are built in a **separate repository**. This
  repository has no Prefect code or dependency.
- The CLI keeps its current interface and moves onto the same step functions. Only the
  CLI is kept backwards compatible. The Python API, its import paths and the on-disk
  staging layout can change.

This document lists all the planned changes. [`CHANGELOG.md`](CHANGELOG.md) records the
changes that have been made.

## How to use this document

- Each phase and item has a status: `Planned`, `In progress` or `Done`.
- When a PR implements an item, it updates the item's status here and adds an entry to
  [`CHANGELOG.md`](CHANGELOG.md) in the same PR.
- Phases are worked on in order. Phases 0–2 are detailed. Later phases are outlines,
  detailed here when their work starts.
- Line numbers cited for current code are as of commit `670a0e4` on `main`.

## Design principles for step functions

These apply to every stage.

1. **One job per function.** A step has explicit inputs and an explicit return value. It
   has no CLI or click concerns, no logging set-up, and no loops or sleeps.
2. **No hidden out-parameters.** A step returns its results. It doesn't append to a
   list the caller passed in (as the Orthanc source's `errors=` argument does now).
3. **Per-accession unit of work.** Batch steps (discover, classify, group) take and
   return collections. The expensive or fallible steps (save, move, unlink, convert,
   upload) work on **one accession**, so that a flow can map them over the accessions
   with per-accession retries and state.
4. **Steps raise; composites collect.** A step raises when it fails. The `raise_errors`
   behaviour and the list of error messages move up into one shared helper,
   `for_each_accession`, used by the plain-Python composites.
5. **Injectable clocks.** Time-dependent steps (the wait period, the run UID) take a
   `now` argument that defaults to the real clock, so tests and retries are
   deterministic.
6. **No Prefect in this repository.** Tasks and flows are built in the separate flows
   repository, which imports the step functions. `accessionflow` has no Prefect imports
   or dependency, and no step assumes how it will be wrapped: no Prefect decorators,
   loggers, contexts or result types.
7. **Steps are a documented public API.** The flows repository depends on them, so each
   step:
   - is exported from a documented module (`accessionflow.api.<stage>`, or a source or
     store plugin's `api` package) and listed in its `__all__`
   - has full type hints and a numpydoc docstring, and takes keyword arguments whose
     defaults match the CLI's
   - can be renamed or changed when needed, without a deprecation period. Every such
     change is recorded under **Step API** in [`CHANGELOG.md`](CHANGELOG.md) so the
     flows repository can follow it
8. **Arguments and results that pickle.** Step arguments and return values must
   round-trip through `pickle`, so the flows repository can use Prefect's result
   persistence, caching and process-based task runners. A contract test checks this
   for each step. Between stages, the hand-off is the staging directory's path, not
   in-memory objects.
9. **Safe to retry.** A task may be re-run after it failed part way. A per-accession step
   clears its own scratch directory under `__build__` before it starts. It leaves the
   output directory either untouched or complete, by building the accession and then
   moving it into place.
10. **One step sequence, two consumers.** Each stage has one plain-Python composite, a
    straight-line sequence of step calls, which the CLI uses (e.g. the folder source's
    `collate()`). This roadmap documents each stage's step order and per-accession unit,
    so the flows repository can wrap the same steps in the same order.
11. **Only the CLI is backwards compatible.** Commands, arguments, options, `ACFLOW_*`
    environment variables and defaults stay the same, and a snapshot test guards them.
    Nothing else is kept:
    - Python functions, signatures and import paths. A large function is replaced by
      its steps, not wrapped, and its callers and tests are updated in the same change
      (e.g. `Accession.from_paths` and `accessionflow/api/collate_api.py`).
    - The on-disk staging layout: directory names, `__build__`, manifests and metadata
      files. It can change where the steps need it to. Each change is recorded under
      **Staging layout** in [`CHANGELOG.md`](CHANGELOG.md), saying whether data staged
      by an earlier version must be drained before upgrading.

## Target layout

```text
accessionflow/api/staging.py       shared by all stages: build directory, move into
                                   place, per-accession runner
accessionflow/api/collate/         core, source-agnostic collate steps, one module per
                                   step group (replaces accessionflow/api/collate_api.py)
accessionflow/api/<stage>/         the same for each later stage
accessionflow/sources/<src>/api/   source-specific steps and the source's collate()
accessionflow/stores/<store>/api/  store-specific steps and the store's store()
accessionflow/cli/runner.py        shared CLI helpers: interval loop, summary logging,
                                   option checks
```

Prefect tasks and flows live in the flows repository, not here.

## Phases

The phases follow the pipeline order:
`collate → [attach] → label → [annotate] → [deidentify] → [package] → store`.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | [Foundations](#phase-0-foundations): these documents, the shared `api/staging.py` and `cli/runner.py` | Done |
| 1 | [Collate, core and folder source](#phase-1-collate-core-and-folder-source) | Planned |
| 2 | [Collate step API hand-off](#phase-2-collate-step-api-hand-off) to the flows repository, proving the pattern before it is repeated | Planned |
| 3 | [Collate, Orthanc source](#phase-3-collate-orthanc-source) | Planned |
| 4 | [Attach](#phase-4-attach) | Planned |
| 5 | [Label](#phase-5-label) | Planned |
| 6 | [Annotate](#phase-6-annotate) | Planned |
| 7 | [Deidentify](#phase-7-deidentify) | Planned |
| 8 | [Package](#phase-8-package) | Planned |
| 9 | [Stores](#phase-9-stores) | Planned |
| 10 | [Wrap-up](#phase-10-wrap-up) | Planned |

Each of phases 3–9 ends with the same hand-off as Phase 2: exports, API reference docs,
the pickle and retry contract tests, an extension of the CLI snapshot test, and a
**Step API** changelog entry.

## Phase 0: Foundations

| Item | Status |
| --- | --- |
| `prefect-migration-docs/` with `ROADMAP.md` and `CHANGELOG.md` | Done |
| `accessionflow/api/staging.py` | Done |
| `accessionflow/cli/runner.py` | Done |

Phase 0 adds the shared helpers and moves `BUILD_NAME_DEFAULT` and
`check_loop_options` into them. Each stage starts using `prepare_build_dir`,
`move_into_place`, `for_each_accession`, `run_on_interval` and `log_stage_summary` in
its own phase, starting with collate in Phase 1.

### `accessionflow/api/staging.py`

Helpers that every stage repeats today.

- `BUILD_NAME_DEFAULT`, moved from `accessionflow/api/collate_api.py`. Its importers are
  updated to the new path: `api/label_api.py`, `api/deidentify_api.py`,
  `api/annotate_api.py`, `api/package_api.py`, both source plugins and
  `api/tests/test_collate.py`.
- `prepare_build_dir(output_dir) -> Path` replaces the `output_dir / BUILD_NAME_DEFAULT`
  and `mkdir` lines repeated in the stages and sources.
- `move_into_place(saved_dir, output_dir, relpath) -> Path` wraps `Accession.move_dir`.
  Collate, label (see the comment at `api/label_api.py:254`), deidentify and annotate
  all build an accession and then move it into place.
- `for_each_accession(accessions, step, desc, raise_errors, name_of) -> list[str]` is the
  progress loop that every stage repeats: run `step` on each accession, and either raise
  or log the error and collect its message. `name_of` names an accession in the
  messages, by default by its `name` or else its `uid`, so it also works on the
  listings that the later stages iterate over.

### `accessionflow/cli/runner.py`

Helpers shared by the CLI commands.

- `run_on_interval(run_once, loop, name, monotonic, sleep)` replaces the `while True` … `time.sleep` block
  repeated in 9 CLI modules: `collate folder`, `collate orthanc`, `label`, `attach`,
  `annotate`, `deidentify`, `package`, `store folder` and `store xnat`. Collate adopts it
  in Phase 1 and the other commands in their phases.
  `cli/tests/test_loop_interval.py` must stay green.
- `check_loop_options(raise_errors, loop)`, moved from `cli/collate_cli.py`. The source
  CLIs import it from here.
- `log_stage_summary(errors, stage)` logs the "completed with N errors" summary.

## Phase 1: Collate, core and folder source

Status: Planned.

The current call chain is:

1. the `collate folder` command, `sources/folder/cli/collate_cli.py::collate_cmd`
2. `sources/folder/api/collate_api.py::collate()`
3. `Accession.from_paths()` (`model/accession.py:792-1129`)
4. `api/collate_api.py::save_accessions_to_dir()` (`api/collate_api.py:18-119`)

The table lists the steps they become, in the order they run. Line numbers are in
`accessionflow/model/accession.py` unless the source line names another file.

| # | Step | From | Kind |
| --- | --- | --- | --- |
| 1 | `prepare_build_dir` | `sources/folder/api/collate_api.py:293-297` | shared (Phase 0) |
| 2 | `check_datatypes` | L888-897 | batch |
| 3 | `plan_recursion` | L899-918 | batch |
| 4 | `expand_input_paths` | L920-968 | batch |
| 5 | `drop_excluded_paths` | L970-971, `_drop_excluded_paths` L231 | batch |
| 6 | `check_paths_exist` | L973-978 | batch |
| 7 | `make_run_uid` | L980-988 | batch |
| 8 | `classify_paths` | L990-999 | batch |
| 9 | `disable_metadata_reading` | L1000-1007 | batch |
| 10 | `drop_ignored_filesets` | L1009-1019 | batch |
| 11 | `apply_path_metadata` | L1021-1035 | batch |
| 12 | `tag_fileset_types` | L1037-1041 | batch |
| 13 | `inject_fileset_tables` | L1043 | batch |
| 14 | `group_into_accessions` | L1045-1118 | batch |
| 15 | `inject_accession_tables` | L1119-1128 | batch |
| 16 | `warn_if_hardlinks_unavailable` | `api/collate_api.py:122-172` | batch |
| 17 | `select_settled` | `api/collate_api.py:70-81` | batch |
| 18 | `stage_accession` | `api/collate_api.py:83-106` | **per accession** |

Steps 1–17 run once per collation. Step 18 runs once per accession, and is the unit
that a flow maps over.

### `accessionflow/api/collate/discover.py`

Finding the input paths.

| Step | From | Notes |
| --- | --- | --- |
| `check_datatypes(datatypes, ignore_datatypes)` | L888-897 | Raises if a datatype is both wanted and ignored. |
| `plan_recursion(datatypes, ignore_datatypes, recursive) -> (recurse_into_dirs, ignore_datatypes)` | L899-918 | Pure. Rejects the generic directory and file-set types with `recursive`. |
| `expand_input_paths(input_paths, datatypes, ignore_datatypes, recursive, recurse_into_dirs) -> (fspaths, input_dirs)` | L920-968 | Directory listing, recursive glob, the prune-on-match walk (`_recursive_collect`, L296), glob patterns and `fix_long_path`. |
| `drop_excluded_paths(fspaths, input_dirs, exclude_paths) -> list[Path]` | `_drop_excluded_paths`, L231 | Made public, with `_glob_to_regex` (L189). |
| `check_paths_exist(fspaths)` | L973-978 | |
| `make_run_uid(fspaths, now=None) -> str` | L980-988 | Injectable clock. |

### `accessionflow/api/collate/classify.py`

Turning paths into file-sets.

| Step | From |
| --- | --- |
| `classify_paths(fspaths, datatypes, ignore_datatypes, allow_unrecognised) -> list[FileSet]` | L990-999 |
| `disable_metadata_reading(filesets, dont_read_metadata) -> list[FileSet]` | L1000-1007 |
| `drop_ignored_filesets(filesets, datatypes, ignore_datatypes) -> list[FileSet]` | L1009-1019 |

### `accessionflow/api/collate/metadata.py`

Adding metadata from paths and tables.

| Step | From |
| --- | --- |
| `apply_path_metadata(filesets, path_metadata_regex) -> list[FileSet]` | L1021-1035 |
| `tag_fileset_types(filesets) -> list[FileSet]` | L1037-1041 |
| `inject_fileset_tables(filesets, metadata_tables) -> list[FileSet]` | L1043 |
| `inject_accession_tables(accessions, metadata_tables) -> list[Accession]` | L1119-1128, at the accession, acquisition and resource levels |

### `accessionflow/api/collate/group.py`

Grouping file-sets into accessions, acquisitions and resources.

| Step | From | Notes |
| --- | --- | --- |
| `resource_label_for(fileset, resource_field) -> (label, derived)` | L1054-1072 | From the DICOM ImageType, the fileset's type (`_datatype_resource_label`, L168) or a `--resource` spec. |
| `acquisition_id_for(fileset, acquisition_id_field, resource_label) -> (acquisition_id, derived)` | L1073-1081 | Takes `_DERIVED_ID` (L65) with it. |
| `clash_hint_for(acquisition_derived, resource_derived) -> str \| None` | L1082-1096 | |
| `group_into_accessions(filesets, accession_uid_field, acquisition_id_field, resource_field, on_resource_clash, run_uid) -> list[Accession]` | L1045-1118 | Uses the three steps above. |

`dicom_image_type_to_resource_label` stays in `model/accession.py`, because the Orthanc
source uses it too.

### `accessionflow/api/collate/save.py`

Saving accessions into the staging directory. From `accessionflow/api/collate_api.py`.

| Step | From | Notes |
| --- | --- | --- |
| `warn_if_hardlinks_unavailable(accessions, build_dir, copy_mode, conversion_map)` | L122-172 | Unchanged. |
| `is_settled(accession, wait_period, now_ns=None) -> bool` | L71-73 | Pure. |
| `select_settled(accessions, wait_period, now_ns=None) -> list[Accession]` | L70-81 | Filters, and logs the accessions it skips. |
| `save_to_build_dir(accession, build_dir, copy_mode, collation_map, conversion_map) -> Path` | L87-97 | Clears the accession's scratch directory first (principle 9). |
| `unlink_source(accession, unlink_source)` | L100-106 | |
| `stage_accession(accession, build_dir, output_dir, copy_mode, collation_map, conversion_map, unlink_source) -> Path` | L83-106 | **The per-accession unit**: `save_to_build_dir`, then `move_into_place`, then `unlink_source`. Raises on failure. |

### Composites

Plain-Python sequences of the steps. Their signatures can change.

- `accessionflow.api.collate.collect_accessions(...)` runs steps 2–15: discover,
  classify, add metadata, group.
- `accessionflow.api.collate.save_accessions_to_dir(...)` runs steps 16–18:
  `warn_if_hardlinks_unavailable`, `select_settled`, then
  `for_each_accession(stage_accession)`.
- `sources/folder/api/collate_api.py::collate()` runs `prepare_build_dir`,
  `collect_accessions` (with the patterns from `merge_path_metadata`),
  `save_accessions_to_dir` and `log_stage_summary`.
  `path_metadata_pattern_to_regex` and `merge_path_metadata` stay in the folder plugin.

### Option converters

`collation_map_from(specs)` and `conversion_map_from(converts)` in
`accessionflow/helpers/arg_types.py` turn CLI option values into API arguments. They
replace the inline dict comprehensions at `sources/folder/cli/collate_cli.py:386-387`
and `sources/orthanc/cli/collate_cli.py:119`, and the flows repository can use them to
build arguments from its own parameters.

### CLI

`sources/folder/cli/collate_cli.py` keeps its options and environment variables. The
body of `collate_cmd` becomes:

1. resolve the deprecated `--accession-uid` and `--acquisition-id` aliases
2. `check_loop_options`
3. `set_logger_handling`
4. `run_on_interval(lambda: collate(...), loop, "collate")`, with the arguments built by
   the option converters

### Removed

- `Accession.from_paths`, with the private helpers that move to
  `api/collate/discover.py` and `api/collate/group.py`: `_glob_to_regex`,
  `_drop_excluded_paths`, `_recursive_collect`, `_datatype_resource_label` and
  `_DERIVED_ID`. The model no longer holds collation logic, so the model doesn't import
  from the API.
- `accessionflow/api/collate_api.py`. References to it are updated to
  `accessionflow.api.collate` in `accessionflow/api/__init__.py`,
  `accessionflow/sources/README.md:23`, `docs/source/developer/plugins.rst:56` and
  `docs/source/reference/api.rst:17`. References to `Accession.from_paths` are updated
  in `docs/source/reference/api.rst:55` and `docs/source/developer/data_model.rst:19`.
  `MIGRATING.md:293` is updated in Phase 10.

### Tests

- **CLI contract snapshot**, taken before the refactor starts: the `--help` text, option
  names, defaults and environment variables of `collate folder` and `collate orthanc`.
  It must still match afterwards. Later phases extend it to their commands.
- **Unit tests** for each step module, under `accessionflow/api/tests/collate/`. The
  pure steps need no DICOM fixtures.
- **Ported tests**, keeping their assertions as the regression net:
  - the 15 calls to `Accession.from_paths` in `model/tests/test_accession.py` and the 2
    in `api/tests/test_collate.py`, which call `collect_accessions` instead
  - the tests of `_glob_to_regex`, `_recursive_collect` and `_datatype_resource_label` in
    `model/tests/test_accession.py`, which move with those helpers
  - `cli/tests/test_cli.py:746`, which patches `accessionflow.api.collate_api.time` and
    uses the `now_ns` argument of `api/collate/save.py` instead
- **Unchanged**: the CLI tests must pass with their assertions as they are:
  `cli/tests/test_cli.py`, `cli/tests/test_collate_commands.py`,
  `cli/tests/test_loop_interval.py`, `sources/folder/tests/test_collate_api.py` and
  `sources/orthanc/tests/test_orthanc_cli.py`. The real-world scripts in `real-tests/`
  use the CLI, so they need no changes.

## Phase 2: Collate step API hand-off

Status: Planned.

- Export the Phase 1 steps and composites from `accessionflow.api.collate` (`__all__`),
  and document them in `docs/source/reference/api.rst`.
- **Pickle contract test**: each step's arguments and return values round-trip through
  `pickle`, including `Accession`, `FileSet`, `Path` and the option types. Anything that
  fails is fixed here, not worked around in the flows repository.
- **Retry test**: running `stage_accession` again after a failure part way through a
  save gives the same output as a clean run.
- Document the step order and per-accession unit for the flows repository (the table in
  Phase 1): the batch steps once, then one task per accession for `stage_accession`.
- Release, with a **Step API** changelog entry that names the new functions.

The tasks, flows, deployments and schedules are out of scope: they belong to the flows
repository. A Prefect schedule takes the place of `--loop` there.

## Phase 3: Collate, Orthanc source

Status: Planned. Outline.

The current entry points are `sources/orthanc/api/collate_api.py::collate()` and
`sources/orthanc/staging.py::stage_studies()` (L63-526), which does all the work in
nested closures. The expected steps are:

- an Orthanc client (URL and credentials) that pickles, replacing the `get_json` and
  `_find_studies` closures, for the steps to take as an argument
- `snapshot_label_format(processed_label)`: the snapshot label's prefix, digest length
  and pattern (L155-168)
- `find_candidate_studies(client, to_process_label, processed_label) -> list[str]`
  (L127-153, L180, L243)
- `reset_changed_studies(client, processed_label, ...)`: removes the labels of processed
  studies that changed after they were staged (L187-241)
- per study, the unit a flow maps over:
  1. check that the study has settled (L270-288)
  2. map its series to acquisitions and resources, with the fallbacks and clash checks
     for missing SeriesNumber or SeriesDescription (L306-377)
  3. link the instances from Orthanc's storage directory (L388-417)
  4. write the resource manifest (L419-420)
  5. convert, if a conversion applies (L422-431)
  6. write the accession's metadata (L433-445)
  7. check that the study didn't change while it was staged (L449-465)
  8. move the accession into place (L466-482)
  9. apply the processed and snapshot labels (L483-505)
- remove the `errors` out-parameter (principle 2). Failed studies are reported through
  `for_each_accession`.

Open: whether Orthanc staging can reference the files in place and reuse
`save_accessions_to_dir`, as the comment at `sources/orthanc/api/collate_api.py:101`
asks.

## Phase 4: Attach

Status: Planned. Outline.

The current entry point is `api/attach_api.py::attach()` (L14-129). It runs two near
identical loops: one over the staged accessions, and one over metadata-only accessions
rebuilt from the YAML files in `__metadata__/` for accessions whose directories have
been removed. Split into listing both kinds of accession (batch), then one step per
accession that attaches the matching files, saves the accession and unlinks the
attached source files. The second loop then goes away.

## Phase 5: Label

Status: Planned. Outline.

The current entry point is `api/label_api.py::label()` (L65-333), called by each store's
`label` command (`stores/xnat/cli/label_cli.py`, `stores/folder/cli/label_cli.py`).
Split into listing the staged accessions and the UIDs already in `__invalid__`
(batch), then, per accession: loading and labelling it, and saving it (build, then move
into place) to the output directory, or to `__invalid__` if IDs are missing. The
existing helpers `_existing_invalid_uids` and `_acquisitions_with_several_resources`
become steps.

## Phase 6: Annotate

Status: Planned. Outline.

The current entry point is `api/annotate_api.py::annotate()` (L17-82). It is already
small: split into listing the staged accessions (batch), then, per accession, extracting
the fields from its metadata, saving it (build, then move into place) and unlinking its
source.

## Phase 7: Deidentify

Status: Planned. Outline.

The current entry point is `api/deidentify_api.py::deidentify()` (L32-228). Split into
loading the default recipes (`load_recipe_files` is already separate), then, per
accession: selecting the recipes for its project, de-identifying it, hashing its UID
(`_hash_uid`), saving it (build, then move into place), and writing its
re-identification record, encrypted if a key is given.

## Phase 8: Package

Status: Planned. Outline.

The current entry point is `api/package_api.py::package()` (L197-368). The per-accession
helper `_package_session` (L29-155) and the input-drift checks (`_file_states`,
`_session_files`, `_input_drift`) become steps, with `_package_session` split into
selecting, converting and saving the resources.

## Phase 9: Stores

Status: Planned. Outline.

The current entry points are the `store()` and `check_store()` functions of each store
plugin:

- `stores/xnat/api/store_api.py::store()` (L108-721) is the largest function in the
  code base. Its existing helpers (`select_files_to_upload`, `session_upload_verdict`,
  `repair_completed_message`, `_staged_upload_batch`, `_upload_session_fields`) become
  steps. The rest splits into connecting and listing (batch), then checking the
  session's identity, uploading, verifying and recording the outcome for one accession
  (per accession). The XNAT connection is passed in a form that pickles (principle 8).
- `stores/xnat/api/check_store_api.py::check_store()`
- `stores/folder/api/store_api.py::store()` (L25-128), with `_deposit_resource` as a step
- `stores/folder/api/check_store_api.py::check_store()`

## Phase 10: Wrap-up

Status: Planned.

- Rewrite the "Python API" and "Data that is already staged" sections of `MIGRATING.md`
  for the step API and any changes to the staging layout.
- Remove any internal helpers that are no longer used.

## Open questions

- Within a stage, will the flows repository pass `Accession` objects between tasks
  (which needs them to pickle, and somewhere to store results), or should the batch
  steps also have variants that take and return paths?
- Can the Orthanc source reuse `save_accessions_to_dir` (see Phase 3)?
- How does the flows repository pin its `accessionflow` version, and which release first
  publishes the collate step API?
