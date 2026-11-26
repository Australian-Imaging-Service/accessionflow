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
    deprecated (Phase 1 does this for `collate folder --unlink-source`). Every change
    in CLI behaviour is recorded in `CHANGELOG.md`.
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

Status: In progress. The step functions (steps 0–20) are done; see
[`CHANGELOG.md`](CHANGELOG.md). So are the three design changes made since, recorded
there under "Phase 1 design records": a random run UID, the revised flow (labelling and
delivery to `<labels>_<run_uid>`), and moving leftover files to an unprocessed
directory.
The [composites](#composites) (C1–C5) are done too.

Collate is now split into two parts:

1. **Collate runs into run accessions.** Each run delivers the accessions it formed
   from the files it claimed, labelled and named `<project>.<subject>.<session>_<run_uid>`
   (`run_uid` is `YYYYMMDDHHMMSS_<6 hex>`). This is `collate_files`, which is done.
2. **The accession combiner** ([Combine](#combine)), a separate action. When a
   project.subject.session has had no new run accession for a given time, it combines
   that session's run accessions into a single accession and writes it to the output
   directory. This is planned.

What is left: the combiner, the option converters, moving the CLI onto `collate_files`
and the combiner (with the label options and the new directories), the removals, and
the tests listed below.

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
- **No wait period in collate.** `wait_period` was there to tell whether an accession
  had finished arriving. Collate no longer waits: each run delivers what has arrived as
  a run accession. Telling whether an accession is complete is the combiner's quiet
  period (see [Combine](#combine)), so `is_settled` and `select_settled` aren't
  needed.
- **Run accessions and combined accessions are kept apart.** Collate delivers its run
  accessions to a run-accessions directory, and the combiner writes the combined
  accessions to the output directory, which later stages read. The proposed default for
  the run-accessions directory is `<output_dir>/__runs__`. Later stages don't see it,
  because `list_session_dirs` skips directories whose names start with `__`.
- **Collated files are always consumed.** Once an accession is staged, its files are
  deleted from the processing area. The API has no `unlink_source` argument.

The CLI keeps its interface (see [CLI](#cli)). `--wait-period` becomes the combiner's
quiet period, and `--unlink-source` becomes a deprecated option that has no effect.

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
| 17 | `assign_labels` | `assign.py` | **per accession** |
| 18 | `move_to_target` | `save.py` | **per accession** |
| 19 | `finish_claim` | `claim.py` | batch |
| 20 | `remove_build_dir` | `api/staging.py` | batch |

Modules are in `accessionflow/api/collate/` unless shown otherwise. Steps 1–16, 19 and 20
run once per collation. Steps 17 and 18 run once per accession, and are the unit that a
flow maps over. Steps 1–3 only read and check the arguments, so they run before any step that
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
  (discarding the plan), makes a random run UID (`make_run_uid()`) and creates its
  build directory, `__build__/<run_uid>/`, exclusively, making another UID if it is
  taken, and removes it in a `finally`. The accessions still get `from_paths`' own run
  UID, a hash of the paths and the time, until it is removed.
- `api/collate_api.py::save_accessions_to_dir` imports `warn_if_hardlinks_unavailable`
  from `save.py`, and keeps today's loop with `wait_period` and `unlink_source`.
- The folder `collate()` still saves unlabelled accessions as `_.<uid>` for the `label`
  stage, which still labels them; `assign_labels` and `move_to_target` take over when
  the folder `collate()` moves onto the steps.
- `helpers/run_uid.py`'s `RUN_UID_RE` also matches `from_paths`' old run-UID form
  (a hash, then the time), so that the labelled names the `label` stage writes from
  those accessions are joined with `_` and parse back.

### Composites

Status: **Done** (2026-11-26). The composites, built in steps C1–C5, are recorded in
[`CHANGELOG.md`](CHANGELOG.md) (Step API, "Phase 1 composites"):
`collect_accessions` and `deliver_accessions` in `api/collate/composites.py`, and the
folder composite `collate_files` in `sources/folder/api/collate_api.py`, alongside
today's `collate()`. The tests of `from_paths` and of the old `collate()` have been
ported to them, as the regression net.

Next, the [CLI](#cli) step switches `collate folder` to `list_input_files` and
`collate_files`, and the removals step deletes `from_paths`, the old `collate()` and
`api/collate_api.py`, and renames `collate_files` to `collate` (see
[Removed](#removed)).

### Combine

Status: Planned. The accession combiner, the second part of collate. Names and
signatures are provisional, and are settled when it is reviewed.

**Run accessions** are what `collate_files` delivers: one accession per
project.subject.session per run, named `<labels>_<run_uid>`. The `output_dir` given to
`collate_files` becomes the run-accessions directory. Since every run's accessions have
their own names, collate never merges two runs' data. Only the combiner does.

**The quiet period.** A project.subject.session is combined once its newest run
accession is older than the quiet period. The age is taken from the time in the run
UID (`split_run_uid`, `helpers/run_uid.py`), not from file modification times. So it
doesn't depend on the file system, and a retried delivery doesn't reset it.

**The combined accession** is named `<labels>_<primary_label>`. `primary_label` is a
parameter of the combiner, and replaces the run UID.

**Clashes.** When two run accessions have the same acquisition and resource, the
`on_resource_clash` policies (`error`, `avoid`, `merge`, `overwrite`, optionally per
datatype) decide, as an option of the combiner.

The steps, in order:

| # | Step | Kind |
| --- | --- | --- |
| 1 | `list_run_accessions(runs_dir)`: groups the run-accession directories by their labels | batch |
| 2 | `select_quiet_groups(groups, quiet_period, now=None)`: the groups with no run accession newer than the quiet period | batch |
| 3 | `prepare_build_dir` (`api/staging.py`) | batch |
| 4 | `combine_accessions(run_dirs, on_resource_clash, ...)`: loads them (`Accession.load`) and merges their acquisitions and resources under the clash policy | **per group** |
| 5 | `deliver_combined(accession, build_dir, output_dir, primary_label)`: saves it into the build directory and moves it into place as `<labels>_<primary_label>`, as `move_to_target` does | **per group** |
| 6 | `remove_run_accessions(run_dirs)`: removes the run accessions that were combined | **per group** |
| 7 | `remove_build_dir` (`api/staging.py`) | batch |

Steps 4–6 run once per group, through `for_each_accession`, and are the unit a flow
maps over.

**The composite** `combine_run_accessions(runs_dir, output_dir, error_dir, quiet_period,
primary_label, *, on_resource_clash="error", raise_errors=False) -> list[str]` follows
the pattern of `collate_files`: checks, then a build directory, then the steps.

- A group that fails (e.g. a clash that the policy makes an error) has its run
  accessions moved to `<error_dir>/<labels>/`, with a record of the error, as
  `abandon_claim` does for a claim.
- It returns the error messages for the caller to log.
- The flows repository can run it as its own flow, on its own schedule.

**Races.** A run accession delivered while the combiner runs is either newer than the
quiet period, so its group isn't quiet, or it arrived after the listing, so it is left
for the next combine.

**Tests** (planned):

- grouping by labels
- quiet and not-quiet groups, with an injected `now`
- merging under each clash policy
- delivery as `<labels>_<primary_label>`, with the run accessions removed
- a failed group moved to the error directory
- a run accession that arrives during a combine
- through `collate folder`: the run accessions are delivered at once, and the combined
  accession only after the quiet period

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
4. warn once if `--unlink-source` (`ACFLOW_UNLINK_SOURCE`) is given: it is deprecated
   and has no effect
5. `run_on_interval(run_once, loop, "collate")`, where each run:
   1. calls `list_input_files(INPUT_PATHS, exclude_paths,
      metadata_table_paths=[t.table_file.fspath for t in metadata_tables])`. Listing
      again on every run picks up the files that arrived since the last one.
   2. calls `collate(...)` with the files it listed, the run-accessions directory as its
      output directory, and the arguments built by the option converters
   3. calls `combine_run_accessions(runs_dir, OUTPUT_DIR, ...,
      quiet_period=wait_period, primary_label=...)`
   4. logs the errors each returns with `log_stage_summary`

New options:

- `--runs-dir`, the run-accessions directory (by default `<output_dir>/__runs__`), and
  an option for the combiner's `primary_label`. Their names and defaults are settled
  with the CLI step.
- `--working-dir`, `--unprocessed-dir` and `--error-dir`, for the run directories, and
  the directories `finish_claim` and `abandon_claim` move them to. The working
  directory defaults to `<output_dir>/__processing__`; the other defaults are settled
  with the CLI step.
- **The label options**, as `assign_labels` needs them: the label fields (one per
  level), the constant labels, the acquisition field and the store type. Today each
  store's `label` command generates its own options from the store's levels (e.g.
  XNAT's project, subject and session), so `collate folder` needs to know the target
  store, e.g. by a store choice that brings in that store's label options.
- The `label` command stays accepted but is deprecated (principle 11) once every
  source labels in collate: the Orthanc source does in Phase 3.

These are changes in behaviour, recorded in `CHANGELOG.md` and, in Phase 10,
`MIGRATING.md`:

- **`--wait-period` is now the combiner's quiet period.** The files are collated on
  every run, whether or not more are still arriving, into run accessions. An accession
  is combined and delivered to `OUTPUT_DIR` once no new data has arrived for it for
  `--wait-period`. Before, collate skipped an accession whose files had changed within
  the period.
- **Collated files are always removed from the input directory**, whether or not
  `--unlink-source` is given. A run without it used to leave them there, to be collated
  again on every run.
- **Files that weren't recognised or were ignored** used to stay in the input
  directory. They are now moved into the processing area too, and stay there (see
  `finish_claim`).
- **`--metadata-table` files in an input directory are no longer collated.** They are
  left in place, so they are still there for later runs, and no longer need
  `--allow-unrecognised` to get past classification. A table whose name changes with
  every delivery (e.g. a timestamp) still has to be named on each run.
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
- From the collate API: `wait_period` (it becomes the combiner's `quiet_period`),
  `unlink_source` and `exclude_paths`, and directories and glob patterns as input.
- `accessionflow/api/collate_api.py`. References to it are updated to
  `accessionflow.api.collate` in `accessionflow/api/__init__.py`,
  `accessionflow/sources/README.md:23`, `docs/source/developer/plugins.rst:56` and
  `docs/source/reference/api.rst:17`. References to `Accession.from_paths` are updated
  in `docs/source/reference/api.rst:55` and `docs/source/developer/data_model.rst:19`.
  `MIGRATING.md:293` is updated in Phase 10.
- The old folder `collate(input_paths, ...)`. `collate_files` (composites step C4) is
  renamed `collate`. The tests that call the old one with `input_paths=...` are
  dropped: C5 recorded each one's counterpart (see [Composites](#composites)).
- The `from_paths` parameter of the `collect` fixtures in `model/tests/test_accession.py`
  and `api/tests/test_collate.py`, and `test_recursive_collect_prunes_on_match`. The
  tests then call `collect_like_from_paths` only. It can be renamed, or the tests moved
  to `api/tests/collate/`.

### Staging layout

When the folder `collate()` starts claiming, record under **Staging layout** in
`CHANGELOG.md`: each run's directory, `<working_dir>/<run_uid>/` (by default under
`<output_dir>/__processing__`), holding `claimed.json` and the claimed files under
`files/`; and where a run directory goes when files are left
(`<unprocessed_dir>/<run_uid>/`) or the run fails (`<error_dir>/<run_uid>/`). The
per-run build directory, the `.staged` marker, the `<labels>_<run_uid>` names and the
unprocessed and error directories' contents are already recorded there. Data already
staged doesn't need draining.

### Tests

- **CLI contract snapshot**, taken before the refactor starts: the option names, types,
  defaults and environment variables of `collate folder` and `collate orthanc`. They
  must still match afterwards. Only the help text changes: `--unlink-source` says it is
  deprecated, and `--wait-period` describes the combiner's quiet period. Later phases extend the
  snapshot to their commands.
- **The tests of `_recursive_collect` and `_datatype_resource_label`** in
  `model/tests/test_accession.py` move with those helpers at the removals step
  (`_recursive_collect`'s is already ported as
  `test_expand_recursion_prunes_on_directory_datatypes`).
- **Tests that change because the behaviour changes**:
  - `cli/tests/test_cli.py::test_stage_wait_period` (L721), which checks that a recent
    accession is skipped. It is rewritten to check that the run accessions are
    delivered at once, and the combined accession only after `--wait-period`. Its patch
    of `accessionflow.api.collate_api.time` (L746) goes, and the combiner is given
    `now` instead.
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
  `move_to_target` again after a failure part way through a save gives the same output
  as a clean run.
- Document that the flows repository chooses the files to collate (e.g. with
  `list_input_files`), and passes them to the collate API as `list[Path]`.
- Document the step order and per-accession unit for the flows repository (the table in
  Phase 1): the batch steps once, then one task per accession for `assign_labels` and
  `move_to_target`.
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
  1. check that the study has settled (L270-288). Whether this becomes the combiner
     (see Phase 1, [Combine](#combine)), as for the folder source, is decided in
     Phase 3. But the processed-label change detection relies
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

Status: Planned. Outline. **To be replanned:** labelling has moved into collate
(`assign_labels`, Phase 1), so the `label` command is deprecated once every source
labels in collate, and kept until then (the Orthanc source, Phase 3). The split below
applies only if `label` is still needed by then.

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
  steps also have variants that take and return paths? `Accession` objects do pickle
  (checked by C2's tests).
- Can the Orthanc source reuse `save_accessions_to_dir` (see Phase 3)?
- How does the flows repository pin its `accessionflow` version, and which release first
  publishes the collate step API?
- Two runs at the same time now build in separate directories and deliver run
  accessions with their own names, so collate never merges. Two combiners running at
  the same time could still combine the same group. Does the combiner need a lock per
  group, or is one combiner at a time a requirement?
- If `<labels>_<primary_label>` already exists in the output directory (data that
  arrived after a combine), does the combiner merge into it, raise and leave the group
  in place, or write under another name?
- Is `primary_label` fixed for a run of the combiner (e.g. a constant), or worked out
  per group (e.g. from metadata, or from the newest run UID)?
- Should the processing area's location be configurable (a new optional CLI option
  such as `--processing-dir`), for input directories on a different file system from
  the staging directory?
