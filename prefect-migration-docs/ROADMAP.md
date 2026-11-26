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

Status: **Done** (2026-11-26). Recorded in [`CHANGELOG.md`](CHANGELOG.md) (Step API):
the step functions (steps 0–20), the three design changes made since ("Phase 1 design
records"), the composites (C1–C5), the accession combiner, the option converters, the
CLI, the removals and the tests. Collate is split into two parts:

1. **Collate runs into run accessions.** Each run delivers the accessions it formed
   from the files it claimed, labelled and named `<project>.<subject>.<session>_<run_uid>`
   (`run_uid` is `YYYYMMDDHHMMSS_<6 hex>`). This is the folder `collate`.
2. **The accession combiner** ([Combine](#combine)). When a project.subject.session has
   had no new run accession for a given time, it combines that session's run
   accessions into a single accession and writes it to the output directory.

The call chain before the CLI step was:

1. the `collate folder` command, `sources/folder/cli/collate_cli.py::collate_cmd`
2. `sources/folder/api/collate_api.py::collate()`
3. `Accession.from_paths()` (`model/accession.py:792-1129`)
4. `api/collate_api.py::save_accessions_to_dir()` (`api/collate_api.py:18-119`)

Since the CLI step, `collate_cmd` calls `list_input_files`, the folder `collate` (named
`collate_files` until the removals step) and `combine_run_accessions`. The removals
step deleted 2–4.

### The input model

The directory that collate reads from is written to all the time by external sources.
Before Phase 1, `Accession.from_paths` listed it with directory listings and globs, and
then read and copied the files it found while new files kept arriving and others were
still being written. To stop these races, Phase 1 changes what collate works on:

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

Status: **Done**. The 20 steps, their run order and the composites that group them are
recorded in [`CHANGELOG.md`](CHANGELOG.md) (Step API, "Phase 1 collate steps").

### Interim state

Status: **Done** (2026-11-26). The stopgaps kept while the old path ran went with the
removals (see [Removed](#removed)).

### Composites

Status: **Done** (2026-11-26). The composites, built in steps C1–C5, are recorded in
[`CHANGELOG.md`](CHANGELOG.md) (Step API, "Phase 1 composites"): the four composites in
`api/collate/composites.py`, each one stage of a run (`build_filesets`: steps 7–9,
`apply_fileset_metadata`: 10–13, `build_accessions`: 14–15, `move_accessions`: 16–18),
and the folder composite `collate_files` in `sources/folder/api/collate_api.py`,
alongside today's `collate()`. The tests of `from_paths` and of the old `collate()` have
been ported to them, as the regression net.

The [CLI](#cli) step switched `collate folder` to `list_input_files` and
`collate_files`, and the removals step deleted `from_paths`, the old `collate()` and
`api/collate_api.py`, and renamed `collate_files` to `collate` (see
[Removed](#removed)).

### Combine

Status: **Done** (2026-11-26). The accession combiner, the second part of collate, is
recorded in [`CHANGELOG.md`](CHANGELOG.md) (Step API, "Phase 1 combine"): the steps in
`api/collate/combine.py`, the composite `combine_run_accessions`, and the names
`<labels>_<primary_label>`. Wiring it into `collate folder`, with `--wait-period` as
the quiet period, is part of the [CLI](#cli) step.

### Option converters

Status: **Done** (2026-11-26). `collation_map_from(specs)` and
`conversion_map_from(converts)` in `accessionflow/helpers/arg_types.py` turn the values
of `--collate-resources` and `--convert` into the `collation_map` and `conversion_map`
API arguments. They replaced the inline dict comprehensions in
`sources/folder/cli/collate_cli.py` and `sources/orthanc/cli/collate_cli.py`, and the
flows repository can use them to build the same arguments from its own parameters.
Recorded in [`CHANGELOG.md`](CHANGELOG.md).

### CLI

Status: **Done** (2026-11-26), recorded in [`CHANGELOG.md`](CHANGELOG.md) (Added,
Changed and Staging layout). `collate folder` lists the input files on every run, and
calls `collate_files`, which delivers labelled run accessions to the run-accessions
directory, and then `combine_run_accessions`, which delivers the combined accessions to
OUTPUT_DIR, with `--wait-period` as the quiet period. It keeps its arguments, options
and environment variables, which the CLI contract snapshot checks. The decisions:

- **`--store`** (by default `xnat`) chooses the store the accessions are labelled for.
  `collate folder` has every installed store's label options, with the same names and
  environment variables as `label <store>` (built by `cli/label_options.py`), except
  that the folder store's `--acquisition` is `--folder-acquisition`, since
  `--acquisition` is already the acquisition ID.
- **`--primary-label`** (by default `combined`) names the combined accessions,
  `<labels>_<primary_label>`.
- **`--runs-dir`, `--working-dir`, `--unprocessed-dir` and `--error-dir`** default to
  `__runs__`, `__processing__`, `__unprocessed__` and `__error__` in OUTPUT_DIR.
- **The `label` command** stays accepted. It is deprecated (principle 11) once every
  source labels in collate: the Orthanc source does in Phase 3.

### Removed

Status: **Done** (2026-11-26), recorded in [`CHANGELOG.md`](CHANGELOG.md) (Removed,
Changed and Staging layout): `Accession.from_paths`, `Accession.last_modified`, the old
folder `collate()`, `api/collate_api.py` and `from_paths`' run-UID form. The folder
`collate_files` is renamed `collate`. The tests that ran on both `from_paths` and the
steps run on the steps, in `api/tests/collate/test_collect.py`. `MIGRATING.md:293` is
updated in Phase 10.

### Staging layout

Status: **Done** (2026-11-26), recorded in [`CHANGELOG.md`](CHANGELOG.md) (Staging
layout) with the CLI step.

### Tests

- **CLI contract snapshot**: done (2026-11-26), `cli/tests/test_cli_contract.py`, of
  `collate folder`, `collate orthanc`, `label xnat` and `label folder`. Later phases
  extend the snapshot to their commands.
- **The tests of `_recursive_collect` and `_datatype_resource_label`**: done with the
  removals (2026-11-26). `_recursive_collect`'s was dropped, since it is ported as
  `test_expand_recursion_prunes_on_directory_datatypes`, and
  `_datatype_resource_label`'s moved to `api/tests/collate/test_group.py`.
- **Tests that change because the behaviour changes**:
  - done with the CLI step (2026-11-26): `cli/tests/test_cli.py::test_stage_wait_period`
    is rewritten, the collate runs in `test_cli.py` give the label options, and
    `test_label_missing_id_field_collects_error` became
    `test_collate_missing_label_field_collects_error` (see `CHANGELOG.md`, Changed).
  - tests that collate the same input more than once, or reuse it after collating it,
    now find it consumed: done with the removals (2026-11-26). The tests that collect
    from a module-scoped DICOM directory (`api/tests/collate/test_collect.py`,
    `api/tests/test_label.py`) copy it into their own `tmp_path` first.
- **Unchanged otherwise**: done (2026-11-26). `cli/tests/test_collate_commands.py`,
  `sources/orthanc/tests/test_orthanc_cli.py` and the rest of `cli/tests/test_cli.py`
  pass with their assertions as they were: the filtered full suite after the removals
  gave 1078 passed, 101 deselected (the XNAT server and deidentify tests), in 9
  minutes. `cli/tests/test_loop_interval.py` follows the folder command onto
  `collate` and `run_on_interval`'s logger. `real-tests/uq_acemid_collate.py` gives
  `collate folder` the label options that `real-tests/uq_acemid_label.py` gave
  `label`, and collates a hard-linked copy of its input, since collate consumes it.
  `uq_acemid_label.py` is deleted. The USyd scripts, which had stopped importing, run
  on today's commands, and `usyd_transfer.py` is deleted, since its command was
  removed (see `CHANGELOG.md`, Changed). The XNAT server and deidentify tests in
  `cli/tests/test_cli.py` are left for Phase 7.

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

Open: whether Orthanc staging can reference the files in place and reuse the Phase 1
save steps (`save_to_build_dir`, `move_to_target`), as the comment at
`sources/orthanc/api/collate_api.py:101` asks of `save_accessions_to_dir`, which the
removals step deleted.

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

Phase 7 runs the XNAT server and deidentification tests again, which were left out
since 2026-11-26. In `cli/tests/test_cli.py`, the Phase 1 CLI step changed them
without running them: `collate folder` now labels (they give it `LABEL_ID_ARGS`), and
they look for the `<labels>_combined` directories and reid files that collate's
combined accessions give. Check those names first if they fail.

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
- Update the user docs of `collate folder` (`docs/source/sources/folder.rst`,
  `docs/source/concepts.rst`) for Phase 1: its label options, `--store`,
  `--primary-label`, the combiner and `--wait-period` as its quiet period, the
  directories it writes (`__runs__`, `__processing__`, `__unprocessed__`,
  `__error__`), and that it consumes its input. The 2026-11-26 tests follow-up only
  corrected the sentences that had become wrong.

## Open questions

- Within a stage, will the flows repository pass `Accession` objects between tasks
  (which needs them to pickle, and somewhere to store results), or should the batch
  steps also have variants that take and return paths? `Accession` objects do pickle
  (checked by C2's tests).
- Can the Orthanc source reuse the Phase 1 save steps (see Phase 3)?
- How does the flows repository pin its `accessionflow` version, and which release first
  publishes the collate step API?
- Two runs at the same time now build in separate directories and deliver run
  accessions with their own names, so collate never merges. Two combiners running at
  the same time could still combine the same group. Neither can overwrite the other's
  combined accession (the rename into place fails if it exists), but the second would
  move the group to the error directory. Is one combiner at a time a requirement, as
  `collate folder` gives, or does the combiner need a lock per group?
- Data for a session that arrives after it was combined now fails, because
  `<labels>_<primary_label>` exists, and goes to the error directory. Is that the
  workflow wanted, or should late data be delivered another way (e.g. a second
  combined accession)?
- Should the processing area's location be configurable? The CLI step added
  `--working-dir`, which moves it; is a separate file system for the input
  directories still a concern?
- A loaded accession's resource metadata merges the file's own fields over the saved
  ones the first time it is read (`Metadata.load` doesn't mark it read). The combiner
  stops this for its run accessions (2026-11-26, see `CHANGELOG.md`), but `label` and
  the later stages still read every file again, which adds the fields that
  `--dont-read-metadata` left out, can replace saved values, and is slow on a network
  file system. Should `Metadata.load` treat the saved file as complete, for every stage?
