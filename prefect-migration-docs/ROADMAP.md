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
- Phases are worked on in order. Phases 1–2 are detailed. Later phases are outlines,
  detailed here when their work starts.
- A phase is removed from this document once it is done. Its record is in
  [`CHANGELOG.md`](CHANGELOG.md).
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
5. **Injectable clocks.** Time-dependent steps (e.g. the run UID) take a `now`
   argument that defaults to the real clock, so tests and retries are
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
    An option whose behaviour has to change stays accepted and is documented as
    deprecated (Phase 1 does this for `collate folder --wait-period` and
    `--unlink-source`). Every change in CLI behaviour is recorded in `CHANGELOG.md`.
    Nothing else is kept:
    - Python functions, signatures and import paths. A large function is replaced by
      its steps, not wrapped, and its callers and tests are updated in the same change
      (e.g. `Accession.from_paths` and `accessionflow/api/collate_api.py`).
    - The on-disk staging layout: directory names, `__build__`, manifests and metadata
      files. It can change where the steps need it to. Each change is recorded under
      **Staging layout** in [`CHANGELOG.md`](CHANGELOG.md), saying whether data staged
      by an earlier version must be drained before upgrading.

12. **Checks before side effects.** A step that only checks its arguments runs before
    any step that changes the file system, so that a run with invalid arguments fails
    without creating, moving or deleting anything. This matters most once collation
    moves its input files: a run that fails after the claim leaves them in the
    processing area.

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
| 0 | Foundations: these documents, the shared `api/staging.py` and `cli/runner.py`. See [`CHANGELOG.md`](CHANGELOG.md) | Done |
| 1 | [Collate, core and folder source](#phase-1-collate-core-and-folder-source) | In progress |
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

Phase 0 added shared helpers that no stage uses yet. Each stage starts using them in its
own phase, starting with collate in Phase 1:

- in its API, `prepare_build_dir`, `move_into_place` and `for_each_accession` from
  `accessionflow/api/staging.py`
- in its CLI command, `run_on_interval` and `log_stage_summary` from
  `accessionflow/cli/runner.py`, keeping `cli/tests/test_loop_interval.py` green

## Phase 1: Collate, core and folder source

Status: In progress. The step functions (steps 0–19) are done; see
[`CHANGELOG.md`](CHANGELOG.md). What is left: the composites, the option converters,
moving the folder `collate()` and the CLI onto the steps, the removals, and the tests
listed below.

The current call chain is:

1. the `collate folder` command, `sources/folder/cli/collate_cli.py::collate_cmd`
2. `sources/folder/api/collate_api.py::collate()`
3. `Accession.from_paths()` (`model/accession.py:792-1129`)
4. `api/collate_api.py::save_accessions_to_dir()` (`api/collate_api.py:18-119`)

### The input model

The directory that collate reads from is written to all the time by external sources.
Today `Accession.from_paths` lists it with directory listings and globs, and then reads
and copies the files it found while new files keep arriving and others are still being
written. To stop these races, Phase 1 changes what collate works on:

- **The API is given the files to collate**, as `input_files: list[pathlib.Path]`, not
  directories or glob patterns. Choosing the files is the caller's job: the CLI does it
  with `list_input_files` (step 0), and the flows repository can do the same.
- **The first step moves those files into a processing area**,
  `<output_dir>/__processing__/<run_uid>/`, which only this collation writes to. Every
  later step works on that fixed, known set of files. Later stages don't see the
  processing area, because `list_session_dirs` (`helpers/remotes.py:554`) skips
  directories whose names start with `__`.
- **No wait period in the API.** `wait_period` was there to tell whether an accession
  had finished arriving. That check becomes a separate, explicit step later in the
  workflow, so `is_settled` and `select_settled` aren't needed.
- **Collated files are always consumed.** Once an accession is staged, its files are
  deleted from the processing area. The API has no `unlink_source` argument.

The CLI keeps its interface (see [CLI](#cli)), including `--wait-period` and
`--unlink-source`, which become deprecated options that have no effect.

### Steps

All 20 steps are **done**. Their signatures, behaviour and the code each was taken from
are recorded in [`CHANGELOG.md`](CHANGELOG.md) (Step API, "Phase 1 collate steps").
The order, which the composites follow:

| # | Step | Module | Kind |
| --- | --- | --- | --- |
| 0 | `list_input_files` | `discover.py` | before collate, used by the CLI |
| 1 | `check_datatypes` | `classify.py` | checks the arguments, the first step of the API |
| 2 | `plan_recursion` | `classify.py` | checks the arguments |
| 3 | `load_metadata_tables` | `metadata.py` | reads and checks the metadata tables |
| 4 | `make_run_uid` | `claim.py` | batch |
| 5 | `prepare_build_dir` | `api/staging.py` | batch |
| 6 | `claim_input_files` | `claim.py` | batch, the first step that changes the input |
| 7 | `expand_claimed_paths` | `classify.py` | batch |
| 8 | `classify_paths` | `classify.py` | batch |
| 9 | `disable_metadata_reading` | `classify.py` | batch |
| 10 | `drop_ignored_filesets` | `classify.py` | batch |
| 11 | `apply_path_metadata` | `metadata.py` | batch |
| 12 | `tag_fileset_types` | `metadata.py` | batch |
| 13 | `inject_fileset_tables` | `metadata.py` | batch |
| 14 | `group_into_accessions` | `group.py` | batch |
| 15 | `inject_accession_tables` | `metadata.py` | batch |
| 16 | `warn_if_hardlinks_unavailable` | `save.py` | batch |
| 17 | `stage_accession` | `save.py` | **per accession** |
| 18 | `finish_claim` | `claim.py` | batch |
| 19 | `remove_build_dir` | `api/staging.py` | batch |

Modules are in `accessionflow/api/collate/` unless shown otherwise. Steps 1–16, 18 and 19
run once per collation. Step 17 runs once per accession, and is the unit that a flow maps
over. Steps 1–3 only read and check the arguments, so they run before any step that
changes the file system (principle 12).

### Interim state

Until the folder `collate()` moves onto the steps, the old path still runs, and these
stopgaps are in place. Each goes with the removal of `Accession.from_paths` (see
[Removed](#removed)):

- `from_paths` keeps its own copies of `check_datatypes`, `plan_recursion`, the
  exclusion filter (`_drop_excluded_paths`) and the prune-on-match walk
  (`_recursive_collect`), and its own grouping loop, run UID and unsorted file-set
  order, because the model can't import from the API.
- `group.py` imports `_datatype_resource_label` and `_DERIVED_ID` from the model, which
  still uses them; they move into `group.py`.
- The folder `collate()` already calls `check_datatypes` and `plan_recursion` first
  (discarding the plan), makes its run UID from its input paths rather than the listed
  files, and builds in `__build__/<run_uid>/`, removed in a `finally`.
- `api/collate_api.py::save_accessions_to_dir` imports `warn_if_hardlinks_unavailable`
  from `save.py`, and keeps today's loop with `wait_period` and `unlink_source`.

### Composites

Plain-Python sequences of the steps. Their signatures can change.

- `accessionflow.api.collate.collect_accessions(claimed, ...)` runs steps 7–15:
  expand, classify, add metadata, group.
- `accessionflow.api.collate.save_accessions_to_dir(...)` runs steps 16–17:
  `warn_if_hardlinks_unavailable`, then `for_each_accession(stage_accession)`.
- `sources/folder/api/collate_api.py::collate(input_files, output_dir, ...)` runs
  `check_datatypes`, `plan_recursion`, `load_metadata_tables`, `make_run_uid`,
  `prepare_build_dir`,
  `claim_input_files`, `collect_accessions` (with the patterns from
  `merge_path_metadata`), `save_accessions_to_dir`, `finish_claim`, `remove_build_dir`
  (in a `finally`, so that a run that raises doesn't leave an empty build directory)
  and `log_stage_summary`. A `FormatMismatchError` from classification names the
  claimed paths, so the composite adds their original paths to it (`original_of`,
  with `add_note`). Compared with today, it takes `input_files: list[Path]` and loses `wait_period`, `unlink_source`,
  `recursive`'s directory listing and `exclude_paths`. `recursive` stays, for directory
  datatypes. `path_metadata_pattern_to_regex` and `merge_path_metadata` stay in the
  folder plugin.

### Option converters

`collation_map_from(specs)` and `conversion_map_from(converts)` in
`accessionflow/helpers/arg_types.py` turn CLI option values into API arguments. They
replace the inline dict comprehensions at `sources/folder/cli/collate_cli.py:386-387`
and `sources/orthanc/cli/collate_cli.py:119`, and the flows repository can use them to
build arguments from its own parameters.

### CLI

`sources/folder/cli/collate_cli.py` keeps its arguments, options and environment
variables. The body of `collate_cmd` becomes:

1. resolve the deprecated `--accession-uid` and `--acquisition-id` aliases
2. `check_loop_options`
3. `set_logger_handling`
4. warn once if `--wait-period` (`ACFLOW_WAIT_PERIOD`) is above 0 or
   `--unlink-source` (`ACFLOW_UNLINK_SOURCE`) is given: both are deprecated and have no
   effect
5. `run_on_interval(run_once, loop, "collate")`, where each run calls
   `list_input_files(INPUT_PATHS, exclude_paths)` and then `collate(...)`
   with the files it listed and the arguments built by the option converters. Listing
   again on every run picks up the files that arrived since the last one.

These are changes in behaviour, recorded in `CHANGELOG.md` and, in Phase 10,
`MIGRATING.md`:

- **`--wait-period` no longer delays collation.** An accession is collated with
  whichever of its files have arrived. Telling whether an accession is complete is left
  to a later, explicit workflow step.
- **Collated files are always removed from the input directory**, whether or not
  `--unlink-source` is given. A run without it used to leave them there, to be collated
  again on every run.
- **Files that weren't recognised or were ignored** used to stay in the input
  directory. They are now moved into the processing area too, and stay there (see
  `finish_claim`).
- **Hidden files and directories are never collated.** They are left in the input
  directory. Before, a run without `--recursive` collated the hidden entries at the top
  level of an input directory.
- **With `--recursive`, an `--exclude-path` pattern that matches a directory excludes
  everything in it**, as it already did without `--recursive`. Before, it excluded only
  the directory itself, and its files were still collated.

### Removed

- `Accession.from_paths` and `Accession.last_modified`, with the private helpers that
  move to the new modules: `_drop_excluded_paths`, `_recursive_collect`, `_datatype_resource_label` and `_DERIVED_ID`. The model no
  longer holds collation logic, so the model doesn't import from the API.
  `_glob_to_regex` has already moved, as
  `accessionflow.helpers.glob2re.glob_to_regex` (step 0).
- From the API: `wait_period`, `unlink_source` and `exclude_paths`, and directories and
  glob patterns as input.
- `accessionflow/api/collate_api.py`. References to it are updated to
  `accessionflow.api.collate` in `accessionflow/api/__init__.py`,
  `accessionflow/sources/README.md:23`, `docs/source/developer/plugins.rst:56` and
  `docs/source/reference/api.rst:17`. References to `Accession.from_paths` are updated
  in `docs/source/reference/api.rst:55` and `docs/source/developer/data_model.rst:19`.
  `MIGRATING.md:293` is updated in Phase 10.

### Staging layout

`__processing__/<run_uid>/` is new in the output directory. Each run directory holds the
plan, `claimed.json`, and the claimed files under `files/`, laid out as they were
relative to the source roots' common directory. A run directory that is left behind
holds the files `finish_claim` reported. Record this under **Staging layout** in
`CHANGELOG.md` when the folder `collate()` starts claiming (the per-run build directory
and the `.staged` marker are already recorded there). Data already staged
doesn't need draining, since the accession directories don't change.

### Tests

- **CLI contract snapshot**, taken before the refactor starts: the option names, types,
  defaults and environment variables of `collate folder` and `collate orthanc`. They
  must still match afterwards. Only the help text of `--wait-period` and
  `--unlink-source` changes, to say that they are deprecated. Later phases extend the
  snapshot to their commands.
- **A race test**: files are added to the input directory while a collation runs. Only
  the files listed at the start are collated, and the new ones stay for the next run.
  The claim's part is already tested; this is the end-to-end test, through the folder
  `collate()`.
- **Ported tests**, keeping their assertions as the regression net:
  - the 15 calls to `Accession.from_paths` in `model/tests/test_accession.py` and the 2
    in `api/tests/test_collate.py`, which list and claim the files, then call
    `collect_accessions`
  - the tests of `_recursive_collect` and `_datatype_resource_label` in
    `model/tests/test_accession.py`, which move with those helpers
- **Tests that change because the behaviour changes**:
  - `cli/tests/test_cli.py::test_stage_wait_period` (L721), which checks that a recent
    accession is skipped. It is rewritten to check that `--wait-period` is accepted,
    warns that it is deprecated, and doesn't delay collation. Its patch of
    `accessionflow.api.collate_api.time` (L746) goes.
  - tests that collate the same input more than once, or reuse it after collating it,
    now find it consumed. In particular, `api/tests/test_collate.py` shares a
    module-scoped `dicom_dir` fixture (L25-29) between its tests. Each test copies the
    fixture's files into its own `tmp_path` first.
- **Unchanged otherwise**: `cli/tests/test_collate_commands.py`,
  `cli/tests/test_loop_interval.py`, `sources/folder/tests/test_collate_api.py`,
  `sources/orthanc/tests/test_orthanc_cli.py` and the rest of `cli/tests/test_cli.py`
  must pass with their assertions as they are. The scripts in `real-tests/` use the CLI.
  `real-tests/uq_acemid_collate.py` should be checked, since collating now consumes its
  input.

## Phase 2: Collate step API hand-off

Status: Planned.

- Export the Phase 1 steps and composites from `accessionflow.api.collate` (`__all__`),
  and document them in `docs/source/reference/api.rst`.
- **Pickle contract test**: each step's arguments and return values round-trip through
  `pickle`, including `Accession`, `FileSet`, `Path` and the option types. This includes
  datatype classes, e.g. in `RecursionPlan.ignore_datatypes`: check that parametrised
  ones such as `DirectoryOf[Json]` pickle. Anything that
  fails is fixed here, not worked around in the flows repository.
- **Retry tests**: running `claim_input_files` again with the same `run_uid` after it
  stopped part way claims the remaining files and nothing twice, and running
  `stage_accession` again after a failure part way through a save gives the same output
  as a clean run.
- Document that the flows repository chooses the files to collate (e.g. with
  `list_input_files`), and passes them to the collate API as `list[Path]`.
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
  1. check that the study has settled (L270-288). The API's `wait_period` is
     deprecated, as for the folder source (Phase 1), and the completeness check moves
     to the same later workflow step. But the processed-label change detection relies
     on a study having been quiet for at least a second (L169-179), so that minimum
     stays inside the step, or the change detection is redesigned.
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

Orthanc's storage files don't change once written, so the Phase 1 claim step isn't
needed: the study labels already mark which studies a run has taken.

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
- Where does the step that checks whether an accession is complete live, now that
  collate has no wait period: in the flows repository, or as a step in this repository
  that runs on the staging directory after collate?
- What happens to the run directories that `finish_claim` leaves in `__processing__`
  (unrecognised and ignored files, and failed accessions)? Retried automatically by a
  later run, moved to a separate area for someone to look at, or deleted after a
  while? This includes a run that raises after the claim, e.g. a `FormatMismatchError`
  for an unrecognised file: today its files stay in the input and the same error is
  raised on every run; once collate claims its input, the input directory moves on and
  the whole run directory waits in `__processing__`.
- Two runs at the same time now build in separate directories, but if both stage the
  same accession, `move_into_place` still merges them in the output directory. Is that
  acceptable, or does staging need a lock per accession?
- Should the processing area's location be configurable (a new optional CLI option
  such as `--processing-dir`), for input directories on a different file system from
  the staging directory?
