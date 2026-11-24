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

Status: In progress. Steps 0–14 are done.

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
  with `list_input_files` (below), and the flows repository can do the same.
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

The table lists the steps in the order they run. Line numbers are in
`accessionflow/model/accession.py` unless the source names another file.

| # | Step | From | Kind |
| --- | --- | --- | --- |
| 0 | `list_input_files` | L920-971, `_drop_excluded_paths` L231 | before collate, used by the CLI. **Done** |
| 1 | `check_datatypes` | L888-897 | batch, checks the arguments, **the first step of the API**. **Done** |
| 2 | `plan_recursion` | L899-918 | batch, checks the arguments. **Done** |
| 3 | `load_metadata_tables` | `MetadataTable.table` | batch, reads and checks the metadata tables. **Done** |
| 4 | `make_run_uid` | L980-988 | batch. **Done** |
| 5 | `prepare_build_dir` | `sources/folder/api/collate_api.py:293-297` | shared, `api/staging.py`. Builds in `__build__/<run_uid>/`. **Done** |
| 6 | `claim_input_files` | new | batch, the first step that changes the input. **Done** |
| 7 | `expand_claimed_paths` | L920-968 | batch. **Done** |
| 8 | `classify_paths` | L990-999 | batch. **Done** |
| 9 | `disable_metadata_reading` | L1000-1007 | batch. **Done** |
| 10 | `drop_ignored_filesets` | L1009-1019 | batch. **Done** |
| 11 | `apply_path_metadata` | L1021-1035 | batch. **Done** |
| 12 | `tag_fileset_types` | L1037-1041 | batch. **Done** |
| 13 | `inject_fileset_tables` | L1043 | batch. **Done** |
| 14 | `group_into_accessions` | L1045-1118 | batch. **Done** |
| 15 | `inject_accession_tables` | L1119-1128 | batch |
| 16 | `warn_if_hardlinks_unavailable` | `api/collate_api.py:122-172` | batch |
| 17 | `stage_accession` | `api/collate_api.py:83-106` | **per accession** |
| 18 | `finish_claim` | new | batch |
| 19 | `remove_build_dir` | new | shared, `api/staging.py`. **Done** |

Steps 1–16, 18 and 19 run once per collation. Step 17 runs once per accession, and is the
unit that a flow maps over. Steps 1–3 only read and check the arguments, so they run
before any step that changes the file system (principle 12): a bad combination of
options, or a metadata table that can't be read or doesn't have its join columns,
such as `--recursive` with `generic/directory`, fails before any input file has been
moved into the processing area. Compared with the current code, the existence check
(L973-978) is no longer needed, because the claim step handles missing files.

### `accessionflow/api/collate/discover.py`

Choosing the files, before collation starts. Not part of the collate API itself.

| Step | From | Notes |
| --- | --- | --- |
| `list_input_files(input_paths, exclude_paths=()) -> list[Path]` | L920-971, `_drop_excluded_paths` L231 | **Done.** Expands directories and glob patterns into a sorted list of files without duplicates, as the CLI's `INPUT_PATHS` and `--exclude-path` do today, and applies `fix_long_path`. Every directory is listed in full, so a directory datatype in it (e.g. a DICOM directory) is kept whole. The listing is the same with or without `--recursive`, which only changes classification (step 7), so the function has no `recursive` argument. Hidden files and directories are skipped at every depth, since they are often uploads in progress; a hidden file named as an input path is still listed. Symlinked directories aren't followed. An exclude pattern that matches a directory excludes everything in it. Excluded files are never listed, so they are never moved. |

### `accessionflow/api/collate/claim.py`

Taking ownership of the files. New.

| Step | Notes |
| --- | --- |
| `make_run_uid(input_files, now=None) -> str` | **Done.** L939-947. The first 6 hex characters of a SHA-256 over the files' sorted absolute paths, then the UTC time as `YYYYMMDDHHMMSS` (injectable clock, principle 5): the same format as today, with no `.`, so it still follows the labels in a staged directory's name. It names the run's build directory (`__build__/<run_uid>/`), its claim directory and its accessions. Made once per run; a retry passes the same value on. Until the CLI passes the listed files, the folder `collate()` makes it from its input paths, and `from_paths` makes its own for the accessions. |
| `claim_input_files(input_files, processing_dir, run_uid, source_roots=None) -> ClaimedFiles` | **Done.** Moves each file into `processing_dir / run_uid`, keeping its path relative to the common directory of the source roots, so that directory datatypes and file names that repeat across directories survive. The roots default to each file's directory; the CLI will pass its input directories. On the same file system a claim is an atomic `os.rename`. Across file systems (`EXDEV`) the file is copied to a hidden temporary name, the source is checked to be unchanged (size and modification time), the copy is renamed into place and the source is deleted. A changed source is left for the next run. A file that has disappeared since it was listed is logged and skipped. Checks the run UID and the roots before anything is moved (principle 12). With no files, nothing is created. Known limits: on one file system, a file still being written is moved and goes on growing in the processing area (completeness is checked by a later step); across file systems, two runs claiming the same file at once can both copy it. |
| `ClaimedFiles` | **Done.** A frozen attrs record that pickles: the run directory, the base the layout is relative to, the source roots, and each claimed file's original path. The files are claimed into `files_dir`, the run directory's `files/` subdirectory (`CLAIMED_FILES_DIRNAME`), apart from the plan, so that no input file can clash with `claimed.json`. `claimed_roots` gives the roots' equivalents in `files_dir`, for step 7, and `original_of` the original path of a claimed file or of a directory that holds claimed files (e.g. a directory datatype), for step 11. `ClaimedFiles.load(run_dir)` rebuilds it from `claimed.json`. `run_dir` is always absolute, as file-sets' paths are, and `original_of` accepts relative paths too. The plan is written atomically once, before any file moves; it isn't rewritten after each move, which would be quadratic for large runs. A retry with the same `run_uid` uses the saved plan and reads each file's state from the file system: a file already claimed is skipped, and a source left behind by a crash after a copy across file systems is deleted if it is unchanged (principle 9). |
| `finish_claim(claimed) -> list[Path]` | After staging: removes the run directory if it's empty. Otherwise it leaves it in place and returns, and logs, what is left: files that weren't recognised or were ignored, and the files of accessions that failed to stage. |

`PROCESSING_NAME_DEFAULT = "__processing__"` and `CLAIMED_MANIFEST = "claimed.json"` are
exported with the steps. The processing area defaults to `<output_dir>/__processing__`, on the same file system
as the staging directory, so that saving into the build directory can still hard-link.
The claim is only atomic when the source is on that file system too.
`warn_if_hardlinks_unavailable` gets a counterpart that warns once when claims will be
copies.

### `accessionflow/api/collate/classify.py`

Turning the claimed files into file-sets.

| Step | From | Notes |
| --- | --- | --- |
| `check_datatypes(datatypes, ignore_datatypes=()) -> None` | L888-897 | **Done.** Raises if no datatype is given (`fileformats.core.from_paths` with no candidates tries every installed format), or if a datatype is both wanted and ignored, naming the datatypes by MIME-like name. Called first by the folder `collate()`. `from_paths` keeps its own copy of the check until it is removed, since the model can't import from the API. |
| `plan_recursion(datatypes, ignore_datatypes=(), recursive=False) -> RecursionPlan` | L899-918 | **Done.** Pure: returns a new `ignore_datatypes` list and doesn't change its input. `RecursionPlan` is a `NamedTuple` of `(recurse_into_dirs, ignore_datatypes)`. Rejects the generic directory and file-set types with `recursive`, naming the datatypes by MIME-like name. For recursion over files only, adds `Directory` to the ignored datatypes. The folder `collate()` calls it before `prepare_build_dir`, discarding the result until step 7 uses it; `from_paths` keeps its own copy until it is removed. |
| `expand_claimed_paths(claimed, datatypes, recursion, recursive=False) -> list[Path]` | L920-968 | **Done.** Takes the `RecursionPlan` from step 2. Applies today's expansion rules to the outermost claimed roots: without `recursive`, each root's top-level entries (so a subdirectory such as a DICOM directory is classified whole); with `recursive` and only file datatypes, every claimed file (the directories that today's glob also lists, only for `Directory` to drop them, are left out); with `recursive` and a directory format among the wanted or ignored datatypes, the prune-on-match walk, copied from `_recursive_collect` (L265) as `_walk_pruning`, so `--recursive` and directory datatypes behave as they do now. Only claimed files and the directories that hold them are returned, so a leftover temporary file or anything else in the run directory is never classified. A root inside another root is dropped, so nothing is listed twice; the caller claims with its input directories as the source roots to get today's top-level entries. `from_paths` keeps `_recursive_collect` until it is removed. |
| `classify_paths(fspaths, datatypes, ignore_datatypes=(), allow_unrecognised=()) -> list[FileSet]` | L990-999 | **Done.** `fileformats.core.from_paths` with the wanted datatypes before the ignored ones, so the first match wins and a wanted datatype beats an ignored one. `ignore_datatypes` is `RecursionPlan.ignore_datatypes` from step 2. File-sets of ignored datatypes are returned; step 10 drops them. The `allow_unrecognised` regular expressions are matched from the start of each path's base name, and any other unrecognised path raises `FormatMismatchError`. |
| `disable_metadata_reading(filesets, dont_read_metadata=()) -> list[FileSet]` | L1000-1007 | **Done.** Sets the public `fileset.metadata.read_disabled` (in `fileformats` 0.22.8, the minimum version) on each file-set that is an instance of one of the datatypes, so a subclass matches too. Changes the file-sets in place and returns the same ones. `from_paths` now uses the public setter too, which resolves its TODO. |
| `drop_ignored_filesets(filesets, datatypes, ignore_datatypes=()) -> list[FileSet]` | L1009-1019 | **Done.** Returns a new list without the file-sets of the ignored datatypes (`RecursionPlan.ignore_datatypes`), matched with `isinstance`. A wanted datatype wins, so a wanted `DirectoryOf[Json]` isn't dropped because `Directory` is ignored. The dropped file-sets' files stay in the processing area, for `finish_claim` to report. |

### `accessionflow/api/collate/metadata.py`

Adding metadata from paths and tables.

| Step | From | Notes |
| --- | --- | --- |
| `apply_path_metadata(filesets, path_metadata_regex=(), claimed=None) -> list[FileSet]` | L1021-1035 | **Done.** Matches each regular expression, in order, against the path of each file-set of its datatype (`fspath`, or `parent` for a file-set of several files such as a DICOM series), mapped back to its **original** path with `claimed.original_of`, so `--path-metadata` and `--path-metadata-regex` patterns, including ones anchored with `/`, match the same paths as today. A later pattern wins for the same field. A pattern that doesn't match raises `ValueError` naming the original path. Changes the file-sets' metadata in place and returns them. No progress bar. Without `claimed`, the file-sets' own paths are matched. |
| `tag_fileset_types(filesets) -> list[FileSet]` | L1037-1041 | **Done.** Sets each file-set's `__datatype__` field (`Accession.TYPE_METADATA_KEY`) to its `type_name`, e.g. `DicomSeries`, for use in `--accession`, `--acquisition` and `--resource` specs. Uses `setdefault`, so a value already set is kept: a path-metadata group of the same name (step 11 runs first) or a header field. The metadata tables (step 13) come after it and can override it. Changes the file-sets in place and returns them. |
| `load_metadata_tables(metadata_tables=None) -> list[MetadataTable]` | `MetadataTable.table` (lazy today) | **Done.** Step 3. Reads every `--metadata-table` into memory and checks that its join columns are in it, before the claim. A table is often delivered with the data (the Canfield export writes its CSV into the input directory), so it is claimed with the files around it and is no longer at its path when the tables are injected; the loaded rows are kept in the `MetadataTable`, which pickles with them. A missing, unreadable or mismatched table fails before anything is created or moved. |
| `inject_fileset_tables(filesets, metadata_tables=None) -> list[FileSet]` | L1043 | **Done.** `MetadataTable.inject_list` on the file-sets: only `fileset` tables apply, joined on the file-sets' metadata (e.g. a path-metadata field), and every column of the one matching row is merged; several matching rows raise `ValueError`. Changes the file-sets in place and returns them. |
| `inject_accession_tables(accessions, metadata_tables) -> list[Accession]` | L1119-1128 | At the accession, acquisition and resource levels. |

### `accessionflow/api/collate/group.py`

Grouping file-sets into accessions, acquisitions and resources.

| Step | From | Notes |
| --- | --- | --- |
| `resource_label_for(fileset, resource_field=()) -> (label, derived)` | L1054-1072 | **Done.** A DICOM collection from the `ImageType` of its first file (`dicom_image_type_to_resource_label`), or 'DICOM'; with no `--resource` spec, from the file-set's type (`_datatype_resource_label`, L169), marked derived; otherwise from the matching `--resource` spec. |
| `acquisition_id_for(fileset, acquisition_id_field, resource_label) -> (acquisition_id, derived)` | L1073-1081 | **Done.** From the `--acquisition` spec that matches the file-set's datatype, or, if none does, the resource's label, marked derived. The `_DERIVED_ID` sentinel (L66) stays inside. |
| `clash_hint_for(acquisition_derived, resource_derived) -> str \| None` | L1082-1096 | **Done.** The hint added to a resource-name clash when the IDs were derived, naming the specs to give. |
| `group_into_accessions(filesets, accession_uid_field, acquisition_id_field=(), resource_field=(), on_resource_clash="error", run_uid=None) -> list[Accession]` | L1045-1118 | **Done.** Uses the three steps above and `Accession.add_resource`, which applies the clash policy. Returns the accessions in the order their first file-sets came in, each with the run UID. Keeps its progress bar: this is where the file-sets' headers are first read for their ID fields, which can take minutes for a large DICOM delivery. |

`dicom_image_type_to_resource_label` stays in `model/accession.py`, because the Orthanc
source uses it too. Until `from_paths` is removed, `group.py` imports
`_datatype_resource_label` and `_DERIVED_ID` from the model, which still uses them; they
move into `group.py` with the removal.

### `accessionflow/api/collate/save.py`

Saving accessions into the staging directory. From `accessionflow/api/collate_api.py`.

| Step | From | Notes |
| --- | --- | --- |
| `warn_if_hardlinks_unavailable(accessions, build_dir, copy_mode, conversion_map)` | L122-172 | Unchanged. It now compares the processing area, not the source, with the build directory. |
| `save_to_build_dir(accession, build_dir, copy_mode, collation_map, conversion_map) -> Path` | L87-97 | Clears the accession's scratch directory first (principle 9). |
| `remove_claimed_files(accession)` | L100-106 | Deletes the accession's files from the processing area. Always run, replacing the optional `unlink_source`. |
| `stage_accession(accession, build_dir, output_dir, copy_mode, collation_map, conversion_map) -> Path` | L83-106 | **The per-accession unit**: `save_to_build_dir`, then `move_into_place`, then `remove_claimed_files`. Raises on failure, which leaves the accession's files in the processing area. |

The wait-period check (L71-81) is removed, with `Accession.last_modified`
(`model/accession.py:2026`), which nothing else uses.

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

Each run builds in its own `__build__/<run_uid>/`, instead of directly in the shared
`__build__/`, so that runs writing to the same output directory at the same time don't
collide. `remove_build_dir` removes it at the end of the run, or leaves it and reports
what a failed save left in it. **Done.**

`__processing__/<run_uid>/` is new in the output directory. Each run directory holds the
plan, `claimed.json`, and the claimed files under `files/`, laid out as they were
relative to the source roots' common directory. A run directory that is left behind holds the files `finish_claim`
reported. Record this under **Staging layout** in `CHANGELOG.md`. Data already staged
doesn't need draining, since the accession directories don't change.

### Tests

- **CLI contract snapshot**, taken before the refactor starts: the option names, types,
  defaults and environment variables of `collate folder` and `collate orthanc`. They
  must still match afterwards. Only the help text of `--wait-period` and
  `--unlink-source` changes, to say that they are deprecated. Later phases extend the
  snapshot to their commands.
- **Unit tests** for each step module, under `accessionflow/api/tests/collate/`. The
  pure steps need no DICOM fixtures. The claim tests (**done**,
  `api/tests/collate/test_claim.py`) cover:
  - a move on one file system, and a copy across file systems (simulated)
  - a source that changes during the copy, and one that disappears after it was listed
  - a retry with the same `run_uid` after a crash part way, picking up from
    `claimed.json`, and a retry after a crash between a copy and deleting its source
  - repeated file names in different directories, and directory datatypes kept whole
  - source roots, and files outside them
  - `ClaimedFiles` pickling and loading

  Path metadata matching the original paths, including patterns anchored with `/`, is
  tested with step 11 (**done**, `api/tests/collate/test_metadata.py`). Still to come:
  `finish_claim` with and without files left over (step 18).
- **A race test**: files are added to the input directory while a collation runs. Only
  the files listed at the start are collated, and the new ones stay for the next run.
  The claim's part is done (`test_claim_leaves_files_that_arrive_after_listing`); the
  end-to-end test comes when the folder `collate()` uses the claim.
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
