# Prefect migration changelog

This file records the changes made under the Prefect migration. The planned changes are
in [`ROADMAP.md`](ROADMAP.md).

Each PR that implements a roadmap item adds an entry here and updates the item's status
in `ROADMAP.md`, in the same PR. Each entry gives its date, its roadmap phase and item,
and its PR.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), with
two sections added:

- **Step API**: every step function added, changed or removed. The flows repository,
  which wraps the steps as Prefect tasks, follows this section to stay in step.
- **Staging layout**: every change to the on-disk staging layout, and whether data
  staged by an earlier version must be drained before upgrading. For operators.

Only the CLI is kept backwards compatible (see principle 11 in the roadmap). Removals
from the Python API are listed under **Removed**. A change to the CLI would break that
contract, so each entry says "CLI unchanged".

## [Unreleased]

### Added

- 2026-11-26, Phase 1, CLI: `collate folder` labels the accessions it collates, for the
  data store given by the new `--store` option (`ACFLOW_STORE`, by default `xnat`,
  one of the installed stores). New options:
  - **Each installed store's label options**, with the same names and environment
    variables as `label <store>`: XNAT's `--project`, `--subject`, `--session`,
    `--scan` and `--constant-project-id`, and the folder store's `--level`,
    `--constant-label` and `--folder-acquisition`. The folder store's acquisition
    option is `--acquisition` in `label folder`, but in `collate folder` that is the
    acquisition ID, so there it is named after its store
    (`ACFLOW_FOLDER_ACQUISITION`). The options of the chosen store default to the
    store's defaults. An option of another store given on the command line is an
    error; from the environment, which other stages share, it is ignored.
  - `--primary-label` (`ACFLOW_PRIMARY_LABEL`, by default `combined`), the suffix of
    the combined accessions' names.
  - `--runs-dir`, `--working-dir`, `--unprocessed-dir` and `--error-dir`
    (`ACFLOW_RUNS_DIR`, `ACFLOW_WORKING_DIR`, `ACFLOW_UNPROCESSED_DIR` and
    `ACFLOW_ERROR_DIR`), by default `__runs__`, `__processing__`, `__unprocessed__`
    and `__error__` in OUTPUT_DIR.
  - **Code:** `accessionflow/cli/label_options.py` (`store_label_options`,
    `resolve_label_options`, `StoreLabelOption`, `LabelOptions`), which `label <store>`
    now builds its options with, unchanged; the step `list_source_roots`; and the
    constants `RUNS_NAME_DEFAULT`, `UNPROCESSED_NAME_DEFAULT` and `ERROR_NAME_DEFAULT`.
  - **Tests:** the CLI contract snapshot, `cli/tests/test_cli_contract.py` with
    `cli/tests/snapshots/cli_contract.json`, taken before the change, of
    `collate folder`, `collate orthanc`, `label xnat` and `label folder`; and
    `sources/folder/tests/test_collate_cli.py`. PR: pending.

- 2026-11-26, Phase 1, option converters, `accessionflow/helpers/arg_types.py`:
  `collation_map_from(specs)` and `conversion_map_from(converts)`, which turn the values
  of `--collate-resources` (`CollationSpec`) and `--convert` (`Convert`) into the
  `collation_map` and `conversion_map` API arguments. A datatype given twice keeps its
  last entry, as before. Tests in `helpers/tests/test_arg_types.py`. PR: pending.
- 2026-11-26, Phase 1, Combine: the accession combiner, in
  `accessionflow/api/collate/combine.py` and `api/collate/composites.py`.
  `combine_run_accessions` takes each session whose run accessions (`<labels>_<run_uid>`,
  delivered by `collate_files`) have had no new one for a quiet period, and combines
  them into one accession, `<labels>_<primary_label>`, in the output directory.
  - **Steps:** `check_primary_label`, `list_run_accessions`, `select_quiet_groups`,
    `combine_accessions`, `deliver_combined`, `remove_run_accessions` and
    `abandon_group`, with the record `RunAccessionGroup`.
  - **Merging:** resource clashes follow `on_resource_clash`, and conflicting own
    metadata, fields or store types are errors.
  - **Existing accession:** one already in the output directory is never changed; the
    group goes to `<error_dir>/<labels>_<run_uid>/`, unless it is the group's own,
    delivered by a crashed attempt.
  - **Tests:** `api/tests/collate/test_combine.py`.

  Nothing calls it yet. The CLI step runs it from `collate folder`. CLI unchanged. PR:
  pending.
- 2026-11-26, Phase 1, composites step C5, tests only: the regression net for removing
  `Accession.from_paths` and the old folder `collate()`.
  - `api/tests/collate/from_paths_port.py`: `collect_like_from_paths`, which takes
    `from_paths`' arguments and runs `list_input_files`, `claim_input_files` and
    `collect_accessions`.
  - The 16 tests in `model/tests/test_accession.py` and `api/tests/test_collate.py`
    that called `Accession.from_paths` take a `collect` fixture, parametrized over
    `from_paths` and the steps, and keep their assertions. Both paths pass all of
    them.
  - `sources/folder/tests/test_collate_files.py`: `collate_files` counterparts of the
    six DICOM tests of the old `collate()` (labelled delivery and names, reloading,
    accession tables, conversion to zip, the hard-link warning, hashing once). The
    roadmap maps every old `collate()` test to its counterpart.

  CLI unchanged. PR: pending.
- 2026-11-26, Phase 1, composites step C4, `sources/folder/api/collate_api.py`:
  `collate_files`, the folder source's whole run on the collate steps, built alongside
  today's `collate()`, which the CLI still runs.
  - It checks the arguments before changing anything (`check_datatypes`,
    `plan_recursion`, `load_metadata_tables`, `merge_path_metadata`).
  - It makes the run UID and build directory, claims the given files, and runs
    `collect_accessions` and `deliver_accessions`.
  - It moves the files that weren't delivered to `<unprocessed_dir>/<run_uid>/`
    (`finish_claim`), or, if a step raises, the whole claim to `<error_dir>/<run_uid>/`
    (`abandon_claim`), including a claim that raised partway.
  - It returns the error messages without logging them, as the CLI step will do with
    `log_stage_summary`.

  Its ID-spec parameters take the steps' names (`accession_uid_field`,
  `acquisition_id_field`, `resource_field`). Tests in
  `sources/folder/tests/test_collate_files.py`, including the end-to-end race test.
  Nothing calls it yet. CLI unchanged. PR: pending.
- 2026-11-26, Phase 1, composites step C3, `accessionflow/api/collate/composites.py`:
  `deliver_accessions`. It runs `warn_if_hardlinks_unavailable` once, then
  `assign_labels` and `move_to_target` on each accession, through
  `for_each_accession`. It returns the accessions that failed with their error
  messages, ready for `finish_claim`. An accession that can't be labelled
  (`LabelsNotAssignedError`) or saved is skipped, and its files stay in the run
  directory. With `raise_errors`, the first failure is raised. Tests in
  `api/tests/collate/test_composites.py`. Nothing calls it yet. CLI unchanged. PR:
  pending.
- 2026-11-26, Phase 1, composites step C2, `accessionflow/api/collate/composites.py`:
  `collect_accessions`, which runs steps 7–15 in the order of the steps table and
  returns a `CollectedAccessions` record. The record holds the accessions and the
  file-sets of ignored datatypes, which `finish_claim` records as `ignored`. When a
  claimed file isn't recognised, a note on the `FormatMismatchError` lists the file's
  original path and the run directory. Tests in `api/tests/collate/test_composites.py`.
  Nothing calls it yet. CLI unchanged. PR: pending.
- 2026-11-25, Phase 1, step 17 (the next action "the revised flow"),
  `accessionflow/api/collate/assign.py`: `assign_labels`, which labels each accession
  from its metadata and raises `LabelsNotAssignedError` (new in
  `accessionflow/exceptions.py`) if a label field is missing. With
  `accessionflow/helpers/run_uid.py`: `RUN_UID_RE`, `RUN_UID_SEPARATOR` and
  `split_run_uid`, which recognise the run UID at the end of a directory name. Tests in
  `api/tests/collate/test_assign.py` and `helpers/tests/test_run_uid.py`. CLI
  unchanged. PR: pending.
- 2026-11-24, Phase 0, documents: created `prefect-migration-docs/` with `ROADMAP.md`
  and `CHANGELOG.md`. The roadmap sets out the design principles for step functions,
  the phases of the migration, and the decomposition of the collate stage (core and
  folder source) into step functions. CLI unchanged. PR: pending.
- 2026-11-24, Phase 0, `accessionflow/api/staging.py`: the helpers every stage repeats
  for writing accessions into a staging directory. Tests in
  `accessionflow/api/tests/test_staging.py`. CLI unchanged. PR: pending.
  - `BUILD_NAME_DEFAULT`, moved from `accessionflow/api/collate_api.py`.
  - `prepare_build_dir(output_dir) -> Path` replaces the `output_dir / BUILD_NAME_DEFAULT`
    and `mkdir` lines repeated in the stages and sources.
  - `move_into_place(saved_dir, output_dir, relpath) -> Path` wraps
    `Accession.move_dir`. Collate, label (see the comment at `api/label_api.py:254`),
    deidentify and annotate all build an accession and then move it into place.
  - `for_each_accession(accessions, step, desc, raise_errors, name_of) -> list[str]` is
    the progress loop that every stage repeats: it runs `step` on each accession, and
    either raises or logs the error and collects its message. `name_of` names an
    accession in the messages, by default by its `name` or else its `uid`, so it also
    works on the listings that the later stages iterate over.

  No stage uses `prepare_build_dir`, `move_into_place` or `for_each_accession` yet;
  each starts in its own phase, collate in Phase 1.
- 2026-11-24, Phase 0, `accessionflow/cli/runner.py`: the helpers the CLI commands
  repeat. Tests in `accessionflow/cli/tests/test_runner.py`. CLI unchanged. PR: pending.
  - `run_on_interval(run_once, loop, name, monotonic, sleep)` will replace the
    `while True` … `time.sleep` block repeated in 9 CLI modules: `collate folder`,
    `collate orthanc`, `label`, `attach`, `annotate`, `deidentify`, `package`,
    `store folder` and `store xnat`. It keeps the timings as the first arguments of its
    log message, as `cli/tests/test_loop_interval.py` checks.
  - `check_loop_options(raise_errors, loop)`, moved from `cli/collate_cli.py`. The
    source CLIs import it from here.
  - `log_stage_summary(errors, stage)` logs the "completed with N errors" summary.

  No command uses `run_on_interval` or `log_stage_summary` yet; collate starts in
  Phase 1.

- 2026-11-24, Phase 1, step 0, `accessionflow/api/collate/discover.py`: the new
  `accessionflow.api.collate` package, with `list_input_files`, which lists the files
  to collate from directories and glob patterns, applying `--exclude-path`. It skips
  hidden files and directories, and an exclude pattern that matches a directory
  excludes its contents. Tests in `accessionflow/api/tests/collate/test_discover.py`.
  Nothing calls it yet: the folder `collate` command starts using it once the claim
  steps exist. CLI unchanged. PR: pending.

- 2026-11-24, Phase 1, step 1, `accessionflow/api/collate/classify.py`: with
  `check_datatypes`, which raises if a datatype is both wanted and ignored. Tests in
  `accessionflow/api/tests/collate/test_classify.py`. PR: pending.

- 2026-11-24, Phase 1, step 2, `accessionflow/api/collate/classify.py`:
  `plan_recursion` and its result, `RecursionPlan`, which check the datatypes can be
  used with `--recursive` and work out how the claimed files will be expanded. Tests in
  `accessionflow/api/tests/collate/test_classify.py`. PR: pending.

- 2026-11-24, Phase 1, step 3, `accessionflow/api/collate/claim.py`: with
  `make_run_uid`, which makes a run's UID from the files it collates and the time
  (injectable). Same format as `from_paths` makes today, with the paths hashed in
  sorted order. Tests in `accessionflow/api/tests/collate/test_claim.py`. PR: pending.
- 2026-11-24, Phase 1, step 18, `accessionflow/api/staging.py`: `remove_build_dir`,
  which removes a run's build directory once it is empty, and otherwise leaves it and
  reports what is left. Tests in `accessionflow/api/tests/test_staging.py`. PR:
  pending.

- 2026-11-24, Phase 1, step 5, `accessionflow/api/collate/claim.py`:
  `claim_input_files` and its result, `ClaimedFiles`, which move the files to collate
  into the run's own directory in the processing area, `<processing_dir>/<run_uid>/`,
  so that the rest of the run works on a fixed set of files. Same file system: atomic
  rename. Across file systems: copy, check the source is unchanged, rename into place,
  delete the source. The plan is saved to `claimed.json` first, so a retry with the
  same run UID picks up where it stopped. With the constants `PROCESSING_NAME_DEFAULT`
  and `CLAIMED_MANIFEST`. Tests in `accessionflow/api/tests/collate/test_claim.py`.
  Nothing calls them yet: the folder `collate()` switches to the claim once the
  expand and path-metadata steps exist. CLI unchanged. PR: pending.

- 2026-11-24, Phase 1, step 6, `accessionflow/api/collate/classify.py`:
  `expand_claimed_paths`, which turns the claimed source roots into the paths to
  classify, with the same rules the input directories had (top-level entries, flat
  recursion, or the prune-on-match walk for directory datatypes), and only ever returns
  claimed entries. Tests in `accessionflow/api/tests/collate/test_classify.py`. Nothing
  calls it yet. CLI unchanged. PR: pending.

- 2026-11-24, Phase 1, step 7, `accessionflow/api/collate/classify.py`:
  `classify_paths`, which classifies the expanded paths into file-sets of the wanted
  and ignored datatypes, as `from_paths` does today. Tests in
  `accessionflow/api/tests/collate/test_classify.py`, including the steps so far run
  together. Nothing calls it yet. CLI unchanged. PR: pending.

- 2026-11-24, Phase 1, step 8, `accessionflow/api/collate/classify.py`:
  `disable_metadata_reading`, which stops the files of the `--dont-read-metadata`
  datatypes being read for metadata. Tests in
  `accessionflow/api/tests/collate/test_classify.py`. Nothing calls it yet. CLI
  unchanged. PR: pending.

- 2026-11-24, Phase 1, step 9, `accessionflow/api/collate/classify.py`:
  `drop_ignored_filesets`, which drops the file-sets of the ignored datatypes, keeping
  any that is also a wanted datatype. Tests in
  `accessionflow/api/tests/collate/test_classify.py`, and the steps-so-far test now
  ends with the same file-sets `from_paths` collates. Nothing calls it yet. CLI
  unchanged. PR: pending.

- 2026-11-24, Phase 1, step 10, `accessionflow/api/collate/metadata.py`:
  `apply_path_metadata`, which adds the fields that `--path-metadata` and
  `--path-metadata-regex` extract from each file-set's original path, from before it
  was claimed. Tests in `accessionflow/api/tests/collate/test_metadata.py`. Nothing
  calls it yet. CLI unchanged. PR: pending.

- 2026-11-24, Phase 1, step 11, `accessionflow/api/collate/metadata.py`:
  `tag_fileset_types`, which sets each file-set's `__datatype__` metadata field to the
  name of its type, unless it is already set. Tests in
  `accessionflow/api/tests/collate/test_metadata.py`. Nothing calls it yet. CLI
  unchanged. PR: pending.

- 2026-11-24, Phase 1, steps 3 and 13, `accessionflow/api/collate/metadata.py`:
  `load_metadata_tables`, which reads every metadata table into memory and checks its
  join columns before the claim, and `inject_fileset_tables`, which merges the rows of
  the `fileset` tables into the file-sets. Tests in
  `accessionflow/api/tests/collate/test_metadata.py`, including a table delivered in
  the input directory and claimed with the data. Nothing calls them yet. CLI unchanged.
  PR: pending.

- 2026-11-24, Phase 1, step 14, `accessionflow/api/collate/group.py`:
  `group_into_accessions`, which groups the file-sets into accessions, acquisitions and
  resources, and the helpers it uses, `resource_label_for`, `acquisition_id_for` and
  `clash_hint_for`. Tests in `accessionflow/api/tests/collate/test_group.py`, including
  steps 7–14 together giving the same accessions as two `from_paths` tests. Nothing
  calls them yet. CLI unchanged. PR: pending.

- 2026-11-24, Phase 1, step 15, `accessionflow/api/collate/metadata.py`:
  `inject_accession_tables`, which merges the rows of the accession, acquisition and
  resource metadata tables into the grouped accessions. Tests in
  `accessionflow/api/tests/collate/test_metadata.py`. Nothing calls it yet. CLI
  unchanged. PR: pending.

- 2026-11-24, Phase 1, step 16, `accessionflow/api/collate/save.py`:
  `warn_if_hardlinks_unavailable`, moved from `accessionflow/api/collate_api.py`. Tests
  in `accessionflow/api/tests/collate/test_save.py`. CLI unchanged: the folder
  `collate()` logs the same warning. PR: pending.

- 2026-11-24, Phase 1, step 17, `accessionflow/api/collate/save.py`:
  `stage_accession`, the per-accession unit, which saves an accession into the build
  directory (`save_to_build_dir`), moves it into place, and deletes its claimed files
  (`remove_claimed_files`), with a marker that makes a retry after a failed delete
  skip the save and the move. Tests in `accessionflow/api/tests/collate/test_save.py`.
  Nothing calls them yet. CLI unchanged. PR: pending.

- 2026-11-24, Phase 1, step 18, `accessionflow/api/collate/claim.py`: `finish_claim`,
  which removes a run's directory from the processing area once its accessions are
  staged, or keeps it with its plan and reports the files left in it. With
  `accessionflow.api.staging.prune_empty_dirs`, taken out of `remove_build_dir`. Tests
  in `accessionflow/api/tests/collate/test_claim.py`, including every step run end to
  end from claim to `finish_claim`. Nothing calls it yet. CLI unchanged. PR: pending.

### Changed

- 2026-11-27, Phase 1, step classes: the steps of a collate run are classes on the new
  base class `accessionflow.api.step.Step`, made with their configuration, which
  `check_configuration()` checks, and run with `act(...)`, which never checks it (see
  Step API). The folder `collate` makes its eight steps, checks every one, and then
  runs them, so a bad configuration in any step fails before anything is created. Its
  signature is unchanged. Two changes in behaviour:
  - Constant labels that aren't label levels now fail the run in
    `MoveAccessions.check_configuration`, before the claim. Before, each accession
    failed with the error as it was labelled.
  - Empty `label_fields` fail the same way.

  Tests: `api/tests/test_step.py`, the configuration tests in
  `api/tests/collate/test_composites.py`, and
  `test_bad_configuration_fails_before_anything_is_created` in
  `sources/folder/tests/test_collate.py`. The tests of the eight functions call the
  steps. CLI unchanged. PR: pending.
- 2026-11-26, documents, `ROADMAP.md` only: adds the Phase 1 section "Store-neutral
  labels" (steps N1–N5), the next step of Phase 1, before Phase 2. Collate will label
  every accession with project, subject and session only, with no `--store` and no
  `store_type`, and each store will build its own naming from the labels and the
  metadata at the start of the store stage. The `--store` and per-store label options
  that the CLI step added to `collate folder` are to be removed in N1, before they are
  released. Phase 1 is in progress again. No code changes. PR: pending.
- 2026-11-26, Phase 1, tests follow-up:
  - The help of the `collate` group no longer says the accessions are "ready to be
    labelled": `collate folder` labels them, and the accessions of other sources are
    labelled by `label`. `docs/source/sources/index.rst` and
    `docs/source/sources/folder.rst` say the same, and `folder.rst` no longer suggests
    `--unlink-source all`, which has no effect. Its full update is left to Phase 10.
  - `real-tests/`: the USyd scripts, which had all stopped importing
    (`accessionflow.utils.show_cli_trace` and the `sort` and `transfer` commands were
    removed), run again:
    - `usyd_stage.py` runs `collate folder` in place of `sort`, with the same
      datatypes, ID fields and labels (`--project PatientComments`, `--subject
      PatientID`, `--session AccessionNumber`) as options. It collates `INBOX/`, a
      hard-linked copy of the export, since collate consumes its input, and
      `USYD_TBP_DIR` points it at another copy. Checked on a dummy PET DICOM export,
      run twice.
    - `usyd_upload.py` and `usyd_check_upload.py` define `show_cli_trace`, and
      `usyd_upload.py` drops `ACFLOW_DELETE` and `ACFLOW_CLEANUP_OLDER_THAN`, which
      no option reads. They need the XNAT server and the S3 bucket, so they weren't
      run.
    - `usyd_transfer.py` is deleted: the `transfer` command was removed before
      Phase 1, and nothing replaces it. `usyd_stage.py` says to copy the staged
      accessions to the bucket instead.

  `collate folder`'s parameters are unchanged. PR: pending.
- 2026-11-26, Phase 1, tests, `real-tests/`: `uq_acemid_collate.py` gives
  `collate folder` the label options (`--subject SubjectID`, `--session
  "{SubjectID}_{CaptureDate:%Y%m%d}"`, `--constant-project-id ACEMID`), since collate
  now labels for XNAT, whose default fields the export doesn't have. Collate consumes
  its input, so each run collates `inbox/`, a hard-linked copy of `input/`, and
  `input/` is left as it is. `UQ_ACEMID_DIR` points it at another copy of the export,
  and it prints the traceback of a failed run. `uq_acemid_label.py` is deleted:
  `collate folder` gives the labels it gave, and it no longer imported
  (`accessionflow.cli.label_cmd` became `label <store>`). Checked on a small tree of
  one image and its table, run twice. Tests: the filtered full suite after the CLI
  and removals steps gave 1078 passed, 101 deselected, in 9 minutes. The 101 are the
  XNAT server and deidentify tests, left for Phase 7. CLI unchanged. PR: pending.
- 2026-11-26, Phase 1, removals, `sources/folder/api/collate_api.py`: `collate_files`
  is renamed `collate` (`accessionflow.sources.folder.api.collate`), and takes the old
  `collate()`'s place. Tests:
  - The tests that ran on both `from_paths` and the steps (C5) run on the steps, in
    `api/tests/collate/test_collect.py`, with the helper `collect_files`
    (`api/tests/collate/collect.py`, which was `from_paths_port.py`). The
    `test_from_paths_*` tests are named `test_collect_*`.
  - `api/tests/test_collate.py` is deleted: C5 recorded each of its old `collate()`
    tests' counterparts. `test_recursive_collect_prunes_on_match` is deleted (ported
    as `test_expand_recursion_prunes_on_directory_datatypes`), and
    `test_datatype_resource_label` moved to `api/tests/collate/test_group.py`.
  - `api/tests/test_label.py`, `api/tests/test_load_ignores_hidden_entries.py` and
    `model/tests/test_load_duplicate_scan_id.py` stage their input with
    `stage_unlabelled` (`api/tests/collate/collect.py`), which saves unlabelled
    accessions as the old `collate()` did, and keep their assertions.
  - `sources/folder/tests/test_collate_files.py` is renamed
    `sources/folder/tests/test_collate.py`.

  CLI unchanged. PR: pending.
- 2026-11-26, Phase 1, CLI, `accessionflow/api/collate/combine.py`:
  `combine_accessions` uses the metadata of the run accessions' resources as collate
  saved it, and no longer reads their files again. A loaded resource's `Metadata`
  merges the file's own fields over the saved ones on first access, which added the
  fields that `--dont-read-metadata` left out, and could replace a saved value (e.g.
  from the path) with the file's. Found by
  `cli/tests/test_cli.py::test_collate_dont_read_metadata[False]`. Test
  `test_combine_accessions_keeps_the_metadata_collate_saved` in
  `api/tests/collate/test_combine.py`. Other stages that load an accession (e.g.
  `label`) still read the files again, as before. PR: pending.
- 2026-11-26, Phase 1, CLI: `collate folder` runs on the collate steps:
  `list_input_files`, `list_source_roots`, `collate_files`, which delivers labelled run
  accessions to the run-accessions directory, and `combine_run_accessions`, which
  delivers the combined accessions to OUTPUT_DIR. It loops with
  `accessionflow.cli.runner.run_on_interval` and logs with `log_stage_summary`. Its
  existing arguments, options and environment variables are unchanged (the snapshot
  test checks them), except for the help of `--wait-period` and `--unlink-source`.
  `collate orthanc` is unchanged until Phase 3. These are changes in behaviour, for
  `MIGRATING.md` in Phase 10:
  - **Collate labels the accessions.** With no options, it labels for XNAT with
    XNAT's default fields (`StudyComments`, `PatientID`, `AccessionNumber` and
    `SeriesDescription`). A run whose data lacks them needs the label options given to
    `collate folder` as well as to `label`. An accession whose label fields are
    missing isn't delivered: it is reported as an error and its files go to the
    unprocessed directory. Before, `label` saved it under `__invalid__`.
  - **OUTPUT_DIR holds the combined accessions**, named `<labels>_combined` (see
    `--primary-label`). Before, it held unlabelled accessions named `_.<uid>`.
    `label` still accepts them, and relabels them.
  - **`--wait-period` is now the combiner's quiet period.** The files are collated on
    every run, into run accessions, whether or not more are still arriving. An
    accession is combined and delivered to OUTPUT_DIR once it has had no new run
    accession for `--wait-period`. Before, collate skipped an accession whose files had
    changed within the period.
  - **Collated files are always moved out of the input directory**, whether or not
    `--unlink-source` is given. `--unlink-source` is deprecated, has no effect, and
    logs a warning.
  - **Files that weren't recognised or were ignored** used to stay in the input
    directory. They are moved into the processing area too, and then to the
    unprocessed directory.
  - **`--metadata-table` files in an input directory are no longer collated.** They are
    left in place, and no longer need `--allow-unrecognised`.
  - **Hidden files and directories are never collated.** They are left in the input
    directory.
  - **With `--recursive`, an `--exclude-path` pattern that matches a directory excludes
    everything in it**, as it already did without `--recursive`.
  - **Tests:** `cli/tests/test_cli.py::test_stage_wait_period` is rewritten to check
    that the run accession is delivered at once and the combined accession only after
    the wait period (an hour, which collating its large fixture can't use up, with the
    combiner's clock moved on). `test_label_missing_id_field_collects_error` became
    `test_collate_missing_label_field_collects_error`.
    `test_sort_orthanc_collate_resources` gives each of its two runs its own copy of
    the input, which collating consumes. The collate runs in `test_cli.py` give the
    label options. The XNAT server and deidentification tests
    there (`test_stage_and_upload`, `test_deidentify_cli_dicom*`) look for
    `<labels>_combined` directories and reid files, but aren't run until Phase 7.
    `cli/tests/test_loop_interval.py` patches `collate_files`, and
    `accessionflow.cli.runner.logger` too. PR: pending.

- 2026-11-26, Phase 1, option converters: `collate folder`
  (`sources/folder/cli/collate_cli.py`) and `collate orthanc`
  (`sources/orthanc/cli/collate_cli.py`) build their `collation_map` and
  `conversion_map` with `collation_map_from` and `conversion_map_from` instead of
  inline dict comprehensions, giving the same values. CLI unchanged. PR: pending.
- 2026-11-26, documents: the roadmap's finished Phase 1 sections moved to the Step API
  section: the Combine design, as "Phase 1 combine", and the steps' run-order table,
  into "Phase 1 collate steps". The roadmap keeps short pointers. No code changes. PR:
  pending.
- 2026-11-26, Phase 1, Combine:
  - **Names that end in a primary label** (`<labels>_<primary_label>`) are read with
    the labels saved in the accession's metadata (`__labels__`), as the name alone
    can't tell the primary label from a label with `_` in it.
    - `helpers/run_uid.py` gains `PRIMARY_LABEL_RE`, `split_name_suffix` and
      `run_uid_time`.
    - `Accession._labels_from_dirname` uses `split_name_suffix`.
    - `SessionListing.ids` returns the saved labels when there are any (new
      `saved_labels`). The S3 listing downloads its metadata once and keeps it, for
      both `saved_labels` and `grouping_uid`.
  - **`Accession.staging_dirname`** now joins any suffix that is a valid primary label
    with `_`, not only a run UID. A suffix like `abc123`, which used to give
    `a.b.c.d.abc123`, now gives `a.b.c.d_abc123`. Both load, because the saved labels
    are used.
  - **`create_run_directory`** (was the folder source's `_create_run_directory`) is in
    `api/collate/claim.py`, shared by `collate_files` and the combiner. With it,
    `RUN_UID_ATTEMPTS` and `write_error_record`, which `abandon_claim` now uses.

  CLI unchanged. PR: pending.
- 2026-11-26, Phase 1, `accessionflow/api/collate/composites.py`: the composites are
  restructured, one per stage of a run, following the groups of the step reference.
  - `build_filesets` (steps 7–9) runs `expand_claimed_paths`, `classify_paths` and
    `drop_ignored_filesets`. It returns a `ClassifiedFilesets(filesets, ignored)`
    record, and keeps the original-path note on `FormatMismatchError`.
  - `apply_fileset_metadata` (steps 10–13) runs `disable_metadata_reading`,
    `apply_path_metadata`, `tag_fileset_types` and `inject_fileset_tables`.
  - `build_accessions` (steps 14–15) runs `group_into_accessions` and
    `inject_accession_tables`.
  - `move_accessions` (steps 16–18) is `deliver_accessions`, renamed.
  - `drop_ignored_filesets` now runs before `disable_metadata_reading`, so they are
    steps 9 and 10. Disabling only sets a flag, so results don't change.
  - Removed: `collect_accessions`, `CollectedAccessions` and `deliver_accessions`.
    `collate_files` and `api/tests/collate/from_paths_port.py` call the four
    composites.
  - Tests: `api/tests/collate/test_composites.py` chains the first three where it
    called `collect_accessions`, with its assertions unchanged. The `deliver_*` tests
    are renamed `test_move_accessions_*`, and there is a new test for each of the
    first three composites on its own. The race test in `test_collate_files.py`
    patches `build_filesets`.

  CLI unchanged. PR: pending.
- 2026-11-26, Phase 1: `merge_path_metadata` moves from the folder source into the core
  collate API, so the core no longer depends on a source for it.
  - `merge_path_metadata` is now in `accessionflow/api/collate/metadata.py`, and is
    exported from `accessionflow.api.collate`.
  - The pattern parser, `path_metadata_pattern_to_regex` (with `_PATTERN_TOKEN_RE`), is
    in a new `accessionflow/helpers/path_pattern.py`.
  - Both are removed from `sources/folder/api/collate_api.py`, and
    `path_metadata_pattern_to_regex` from `accessionflow.sources.folder.api`. The folder
    `collate()` and `collate_files` import `merge_path_metadata` from the core.
  - The code is unchanged. Its tests move from the deleted
    `sources/folder/tests/test_collate_api.py` to `helpers/tests/test_path_pattern.py`
    and `api/tests/collate/test_metadata.py`, with the same assertions.

  CLI unchanged. PR: pending.
- 2026-11-26, Phase 1 design, `ROADMAP.md` only: collate is split into two parts.
  - **Collate runs** deliver run accessions, `<labels>_<run_uid>` (`collate_files`,
    done).
  - **A new accession combiner** (the Combine section, planned) waits until a
    project.subject.session has had no new run accession for a quiet period. It then
    combines them into one accession, `<labels>_<primary_label>`, in the output
    directory. `primary_label` is a parameter.
  - **Clashes** use the `on_resource_clash` policies.
  - **`collate folder`** runs the combiner after each collate run, with run accessions
    in a run-accessions directory (proposed `<output_dir>/__runs__`).
  - **`--wait-period`** becomes the combiner's quiet period, so it is no longer
    deprecated.
  - **Open questions:** the one on where the completeness check lives is answered.
    Added: concurrent combiners, an existing combined accession, and how
    `primary_label` is chosen.

  No code changes. PR: pending.
- 2026-11-26, documents: the Composites section of `ROADMAP.md` (C1–C5) and its two
  finished test items (the race test and the ported tests) moved to the Step API
  section, as "Phase 1 composites". No code changes. PR: pending.
- 2026-11-26, Phase 1, composites step C4:
  - `expand_claimed_paths` (`api/collate/classify.py`): with `--recursive`, a
    directory that matches an ignored directory format (e.g. `DirectoryOf[Csv]`) is
    yielded whole instead of skipped. It is classified and then dropped as ignored, so
    `collect_accessions` returns it in `ignored` and `finish_claim` records its files
    as `ignored`, where it recorded them as `unrecognised`. The accessions don't change.
    Tests updated in `test_classify.py` and `test_composites.py`.
  - The folder `collate()` makes its run UID and build directory with
    `_create_run_directory(output_dir)`, shared with `collate_files`. No change in behaviour.

  CLI unchanged. PR: pending.
- 2026-11-26, Phase 1, composites step C3, tests only:
  `test_steps_end_to_end_with_a_leftover` moved from `api/tests/collate/test_claim.py`
  to `test_composites.py` as `test_deliver_one_of_each_case`. It now runs on
  `collect_accessions` and `deliver_accessions`, and keeps its assertions on
  `finish_claim`. CLI unchanged. PR: pending.
- 2026-11-26, Phase 1, composites step C2, tests only: the tests that chained steps 7–14
  by hand (`test_steps_7_to_14_like_from_paths_datatype_field` and `..._recursive` in
  `test_group.py`, and `test_steps_7_to_11_together` in `test_metadata.py`) moved to
  `api/tests/collate/test_composites.py`. They now call `collect_accessions` and keep
  their assertions. CLI unchanged. PR: pending.
- 2026-11-25, Phase 1, composites step C1: `accessionflow.api.staging.for_each_accession`
  returns `list[tuple[T, str]]`, each accession the step failed on with its error
  message (traceback included), instead of the messages alone, so that the failed
  accessions can be passed to `finish_claim`. The messages are unchanged, and are what
  `log_stage_summary` is given. Tests in `api/tests/test_staging.py`. Nothing outside
  its tests used it. CLI unchanged. PR: pending.
- 2026-11-25, Phase 1 design, `ROADMAP.md` only: the Composites section is planned as
  five steps: C1, `for_each_accession` returns the failed items with their errors; C2,
  `collect_accessions` (steps 7–15), returning the accessions and the ignored
  file-sets; C3, `deliver_accessions` (steps 16–18); C4, the folder composite
  `collate_files`, built alongside today's `collate()` until the CLI moves onto it; and
  C5, porting the `from_paths` tests. No code changes. PR: pending.
- 2026-11-25, Phase 1 (the next action "the revised flow"):
  - `move_to_target` (step 18) replaces `stage_accession`: it delivers a labelled
    accession to `<output_dir>/<labels>_<run_uid>/`. `finish_claim` and
    `remove_build_dir` become steps 19 and 20.
  - `Accession.staging_dirname` joins a recognisable run UID with `_` instead of `.`,
    so every stage that saves a labelled accession (label, deidentify, annotate,
    package) names it `<labels>_<run_uid>`. A run UID that isn't recognisable keeps
    `.`. `Accession._labels_from_dirname` and `SessionListing.ids` find the run UID by
    its whole pattern at the end of the name, and still read `<labels>.<run_uid>` and
    the legacy `-`-delimited names.
  - `claim_input_files` takes `working_dir`, renamed from `processing_dir`.

  Tests in `api/tests/collate/test_save.py`, `api/tests/collate/test_claim.py` and
  `model/tests/test_labels.py`. CLI options unchanged; labelled output directories are
  named `<labels>_<run_uid>` instead of `<labels>.<run_uid>`. PR: pending.
- 2026-11-25, Phase 1, step 18 (the next action "leftover files to an unprocessed
  directory"): `finish_claim` takes an `unprocessed_dir`, and the accessions that
  failed to stage and the file-sets that were ignored, and moves a run directory with
  files left in it to `<unprocessed_dir>/<run_uid>/`, recording why each file was left
  in `unprocessed.json`, instead of keeping it in the processing area. The new
  `abandon_claim` moves the claim of a run that raised to an error directory, with the
  error in `error.json`. Tests in `api/tests/collate/test_claim.py`. Nothing calls
  them yet. CLI unchanged. PR: pending.
- 2026-11-25, Phase 1, steps 4 and 5 (the next action "a random run UID"):
  `make_run_uid` makes the UTC time, `_` and 6 random hex characters, instead of a hash
  of the input paths and the time, so two runs that list the same files in the same
  second no longer share a UID, and it no longer takes the files.
  `prepare_build_dir` takes `exclusive`, and the folder `collate()` creates its build
  directory exclusively, making another UID if one is taken. Tests in
  `api/tests/collate/test_claim.py`, `api/tests/test_staging.py` and
  `api/tests/test_collate.py::test_collate_makes_a_new_run_uid_on_a_clash`. CLI
  unchanged. PR: pending.
- 2026-11-25, Phase 1, step 0: `list_input_files` takes `metadata_table_paths` and
  leaves those files out of the listing, wherever they are listed from. A
  `--metadata-table` file kept in an input directory is then never claimed, stays in
  place for later runs, and doesn't need `--allow-unrecognised`. This reverses the
  earlier choice to claim a table with the data. Tests in
  `accessionflow/api/tests/collate/test_discover.py`. CLI unchanged. PR: pending.
- 2026-11-25, Phase 1 design, `ROADMAP.md` only: a next action for `finish_claim` to
  move any files left after staging to an unprocessed directory given as a parameter,
  and then remove the run directory. This answers the open question about the run
  directories it used to leave in the processing area. No code changes yet. PR:
  pending.
- 2026-11-25, Phase 1 design, `ROADMAP.md` only: a next action revising the collate
  flow. Each run works in `<working_dir>/<run_uid>/`, a new parameter;
  `stage_accession` comes out of the flow; an assign step labels each accession
  (`project.subject.session`) from its metadata in its place; and a new step moves each
  accession's files to the target directory as `<project>.<subject>.<session>-<run_uid>`
  for the next process. No code changes yet. PR: pending.
- 2026-11-25, Phase 1 design, `ROADMAP.md` only: a next action to make the run UID
  the UTC timestamp followed by random characters instead of a hash of the input paths,
  with the run's build directory created exclusively. Two runs that list the same files
  in the same second would otherwise get the same UID and share a claim. No code
  changes yet. PR: pending.
- 2026-11-24, Phase 1, step 17 (a fix to step 5's `remove_build_dir`): it removes
  empty subdirectories before deciding whether the run's build directory is empty.
  `Accession.save` leaves an empty `__build__` in the directory it saves into, so
  since step 5 every collate run that staged an accession kept its
  `__build__/<run_uid>/` directory and logged "Leaving build directory". Now guarded by
  `api/tests/test_collate.py::test_collate_creates_pre_label_session_dir`. CLI
  unchanged. PR: pending.
- 2026-11-24, Phase 1, step 16: `warn_if_hardlinks_unavailable` returns one file of
  each resource that can't be hard-linked, and works out the output directory it names
  from the build directory instead of assuming its layout. `claim_input_files` logs one
  warning when it has copied files into the processing area from a different file
  system. CLI unchanged. PR: pending.
- 2026-11-24, Phase 1, step 15 (a revision of step 8): `classify_paths` returns the
  file-sets sorted by path. `fileformats` returns them in an order that can change from
  run to run (with Python's hash randomisation), which made the order of the grouped
  accessions change too. `Accession.from_paths` still has the unsorted order until it
  is removed. CLI unchanged. PR: pending.
- 2026-11-24, Phase 1 design, `ROADMAP.md`: a new step 3, `load_metadata_tables`,
  runs with the argument checks, before the claim, because a metadata table delivered
  with the data (as the Canfield export does) is claimed with it and is no longer at
  its path when the tables are injected. Every later step moves up by one:
  `make_run_uid` is now step 4, `prepare_build_dir` 5, `claim_input_files` 6, and so
  on to `remove_build_dir`, now 19. Earlier entries in this changelog keep the numbers
  they had when they were written. PR: pending.
- 2026-11-24, Phase 1, step 10 (a revision of step 5): `claim_input_files` makes the
  run directory absolute, and `ClaimedFiles.original_of` accepts relative paths, so
  that a relative processing directory still maps the file-sets' absolute paths back to
  the original ones. CLI unchanged. PR: pending.
- 2026-11-24, Phase 1, step 8: `Accession.from_paths` disables reading metadata with
  the public `fileset.metadata.read_disabled` setter instead of the private
  `_read_disabled`, now that `fileformats` 0.22.8, the minimum version, has it. Same
  behaviour. CLI unchanged. PR: pending.
- 2026-11-24, Phase 1, step 7: `check_datatypes` rejects an empty `datatypes`, which
  would make classification try every installed format. The folder `collate()` calls
  it first, so it now raises before anything is created. CLI options unchanged; an
  explicitly empty `--datatype` is now an error. PR: pending.
- 2026-11-24, Phase 1, step 6 (a revision of step 5): `claim_input_files` claims the
  files into `<run_dir>/files/` (`CLAIMED_FILES_DIRNAME`, `ClaimedFiles.files_dir`)
  instead of directly into the run directory, so that an input file named
  `claimed.json` can't clash with the plan. `ClaimedFiles.original_of` now also maps a
  directory that holds claimed files, and raises `ValueError`, not `KeyError`, for a
  path outside `files_dir`. Nothing used the claim yet, so nothing needs migrating. CLI
  unchanged. PR: pending.
- 2026-11-24, Phase 1, step 5: the run UID check in `prepare_build_dir` moved to
  `accessionflow.api.staging.check_run_uid(run_uid, purpose)`, which the claim uses
  too. Same rule and message. CLI unchanged. PR: pending.
- 2026-11-24, Phase 1 design, `ROADMAP.md`: `make_run_uid` (now step 3) runs before
  `prepare_build_dir` (now step 4), because the run UID names the run's build
  directory. New final step 18, `remove_build_dir`. PR: pending.
- 2026-11-24, Phase 1, step 4: `prepare_build_dir(output_dir, run_uid)` creates the
  run's own build directory, `<output_dir>/__build__/<run_uid>/`, so that parallel runs
  don't collide, and rejects a run UID that isn't a plain directory name. The folder
  `collate()` makes a run UID from its input paths, builds in that directory, and
  removes it afterwards, even when it raises. `warn_if_hardlinks_unavailable` still
  names the output directory in its warning. Tests revised in `test_staging.py` and
  `test_collate.py`, with a new test that the build directory is removed when collate
  raises. CLI unchanged. PR: pending.
- 2026-11-24, Phase 1, step 2: the folder source's `collate()` calls `plan_recursion`
  after `check_datatypes`, so `--recursive` with `generic/directory` or
  `generic/file-set` as a datatype fails before the build directory is created. The
  error names the datatypes by MIME-like name instead of by class. New test
  `api/tests/test_collate.py::test_collate_recursive_generic_directory_raises`. CLI
  options unchanged; the error text changes. PR: pending.
- 2026-11-24, Phase 1, step 1: the folder source's `collate()` calls
  `check_datatypes` first, so a datatype given to both `--datatype` and
  `--ignore-datatype` fails before the build directory is created. The error names
  the datatypes by MIME-like name (e.g. `['medimage/dicom-series']`) instead of by
  class. `api/tests/test_collate.py::test_collate_ignore_datatypes_contradicting_datatype_raises`
  no longer needs DICOM data, and checks that nothing is created. CLI options
  unchanged; the error text changes. PR: pending.
- 2026-11-24, Phase 1 design, `ROADMAP.md` only: the collate steps are reordered so
  that the argument checks, `check_datatypes` and `plan_recursion`, run first (steps 1
  and 2), before `prepare_build_dir` (now step 3) and the claim (now step 5). A run with
  invalid options now fails before any input file is moved. New design principle 12,
  checks before side effects. No code changes. PR: pending.
- 2026-11-24, Phase 1, `prepare_build_dir` (step 1 when done, now step 3): the folder
  source's `collate()` creates its build
  directory with `accessionflow.api.staging.prepare_build_dir`, instead of inline code
  that did the same. `api/tests/test_collate.py::test_collate_creates_build_dir` now
  also checks that collate creates an output directory that doesn't exist yet. CLI
  unchanged. PR: pending.
- 2026-11-24, Phase 1, step 0: `accessionflow.model.accession._glob_to_regex` moved to
  `accessionflow.helpers.glob2re.glob_to_regex`, unchanged, so that the model and the
  collate steps share it. Its test moved to `helpers/tests/test_glob2re.py`. CLI
  unchanged. PR: pending.

- 2026-11-24, Phase 1 design, `ROADMAP.md` only: the collate API will take the files
  to collate as `list[Path]`, and its first step will move them into a processing area
  (`<output_dir>/__processing__/<run_uid>/`), so that the rest of the collation works
  on a fixed set of files while the input directory keeps changing. `wait_period` and
  `unlink_source` are dropped from the API: completeness is checked by a later
  workflow step, and collated files are always consumed. The CLI keeps `--wait-period`
  and `--unlink-source` as deprecated options with no effect. No code changes yet.
  PR: pending.
- 2026-11-24, Phase 0: `label_api`, `deidentify_api`, `annotate_api`, `package_api`,
  the folder and Orthanc sources and `api/tests/test_collate.py` import
  `BUILD_NAME_DEFAULT` from `accessionflow.api.staging`. The folder and Orthanc
  `collate` commands import `check_loop_options` from `accessionflow.cli.runner`. CLI
  unchanged. PR: pending.

### Removed

- 2026-11-26, Phase 1, removals: the old collate path, which only tests still called
  since the CLI step.
  - `Accession.from_paths` and `Accession.last_modified`. Use the collate steps in
    `accessionflow.api.collate`, or the folder `collate`.
  - The old folder `collate(input_paths, ...)`, with its `wait_period`,
    `unlink_source` and `exclude_paths` arguments and its directories and glob
    patterns as input. Use `list_input_files`, the folder `collate` and
    `combine_run_accessions`, as `collate folder` does.
  - `accessionflow/api/collate_api.py`, with `save_accessions_to_dir`, which
    `accessionflow.api` no longer exports. Use `save_to_build_dir` and
    `move_to_target`.
  - The model's private `_drop_excluded_paths` and `_recursive_collect`, which
    `discover.py` and `classify.py` had copied. `_datatype_resource_label` and
    `_DERIVED_ID` moved to `accessionflow/api/collate/group.py`.
  - `from_paths`' run-UID form, `<6 hex>YYYYMMDDHHMMSS`, from
    `accessionflow.helpers.run_uid` (`RUN_UID_RE`, `split_run_uid` and
    `run_uid_time`).

  CLI unchanged. PR: pending.
- 2026-11-25, Phase 1: `accessionflow.api.collate.stage_accession`. Use
  `assign_labels` and then `move_to_target`. PR: pending.
- 2026-11-24, Phase 1, step 16:
  `accessionflow.api.collate_api.warn_if_hardlinks_unavailable`. Use
  `accessionflow.api.collate.warn_if_hardlinks_unavailable`. PR: pending.
- 2026-11-24, Phase 0: `accessionflow.api.collate_api.BUILD_NAME_DEFAULT`. Use
  `accessionflow.api.staging.BUILD_NAME_DEFAULT`, or `accessionflow.api.BUILD_NAME_DEFAULT`,
  which is still exported. PR: pending.
- 2026-11-24, Phase 0: `accessionflow.cli.collate_cli.check_loop_options`. Use
  `accessionflow.cli.runner.check_loop_options`. PR: pending.

### Step API

#### Phase 1 collate steps

A reference for the collate step functions, moved from `ROADMAP.md` when they were
done (2026-11-24). The dated entries below record how each was added and changed. The
"From" column gives the code each step was taken from, as of commit `670a0e4` on `main`:
line numbers are in `accessionflow/model/accession.py` unless another file is named.

The run order, moved from `ROADMAP.md` (2026-11-26), with the kind of each step:

| # | Step | Module | Kind |
| --- | --- | --- | --- |
| 0 | `list_input_files` | `discover.py` | before collate, used by the CLI |
| 1 | `check_datatypes` | `classify.py` | checks the arguments, the first step of the API |
| 2 | `plan_recursion` | `classify.py` | checks the arguments |
| 3 | `load_metadata_tables` | `metadata.py` | reads and checks the metadata tables |
| – | `merge_path_metadata` | `metadata.py` | checks and translates the path-metadata patterns, for step 11 |
| 4 | `make_run_uid` | `claim.py` | batch |
| 5 | `prepare_build_dir` | `api/staging.py` | batch |
| 6 | `claim_input_files` | `claim.py` | batch, the first step that changes the input |
| 7 | `expand_claimed_paths` | `classify.py` | batch |
| 8 | `classify_paths` | `classify.py` | batch |
| 9 | `drop_ignored_filesets` | `classify.py` | batch |
| 10 | `disable_metadata_reading` | `classify.py` | batch |
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
flow maps over. Steps 1–3 and `merge_path_metadata` only read and check the arguments, so
they run before any step that changes the file system (principle 12).

The steps fall into eight groups. In the table, `#` is the step's number in the run
order; the steps in a group marked `–` are helpers that the numbered step uses,
or the record a step returns. Each group's table gives each step's signature, its
module in `accessionflow/api/collate/` (unless another path is shown), where it was
taken from, and what it does. Steps 9 and 10 were swapped on 2026-11-26, when the
composites were restructured to follow these groups (see the dated entries).

| Group | Steps |
| --- | --- |
| List input files | 0 `list_input_files` |
| Check parameters | 1 `check_datatypes`, 2 `plan_recursion`, 3 `load_metadata_tables` |
| Set up the run directory | 4 `make_run_uid`, 5 `prepare_build_dir`, 6 `claim_input_files` |
| Determine the file-sets | 7 `expand_claimed_paths`, 8 `classify_paths`, 9 `drop_ignored_filesets` |
| Apply metadata | 10 `disable_metadata_reading`, 11 `apply_path_metadata`, 12 `tag_fileset_types`, 13 `inject_fileset_tables` |
| Form accessions | 14 `group_into_accessions`, 15 `inject_accession_tables` |
| Assign and deliver | 16 `warn_if_hardlinks_unavailable`, 17 `assign_labels`, 18 `move_to_target` |
| Clean up | 19 `finish_claim`, 20 `remove_build_dir` |

Steps 1–16, 19 and 20 run once per collation; steps 17 and 18 run once per accession. Within
the groups, `drop_ignored_filesets` (10) is listed with the file-set steps and
`disable_metadata_reading` (9) with the metadata steps; the two are independent (neither
reads metadata), so either order gives the same result. The existence check in
`from_paths` (L973-978) isn't needed, because the claim handles missing files.

##### List input files

Choosing the files, before collation starts. Not part of the collate API itself.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 0 | `list_input_files(input_paths, exclude_paths=(), metadata_table_paths=()) -> list[Path]` | `discover.py` | L920-971, `_drop_excluded_paths` L231 | Expands directories and glob patterns into a sorted list of files without duplicates, as the CLI's `INPUT_PATHS` and `--exclude-path` do today, and applies `fix_long_path`. Every directory is listed in full, so a directory datatype in it (e.g. a DICOM directory) is kept whole. The listing is the same with or without `--recursive`, which only changes classification (step 7), so the function has no `recursive` argument. Hidden files and directories are skipped at every depth, since they are often uploads in progress; a hidden file named as an input path is still listed. Symlinked directories aren't followed. An exclude pattern that matches a directory excludes everything in it. Excluded files are never listed, so they are never moved The files of the metadata tables (`metadata_table_paths`) are left out wherever they are listed from, compared as files (`os.path.samefile`, for files with a table's base name), so a table kept in an input directory stays in place. |

##### Check parameters

Only read and check, so a bad configuration fails before anything is created or moved (principle 12).

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 1 | `check_datatypes(datatypes, ignore_datatypes=()) -> None` | `classify.py` | L888-897 | Raises if no datatype is given (`fileformats.core.from_paths` with no candidates tries every installed format), or if a datatype is both wanted and ignored, naming the datatypes by MIME-like name. Called first by the folder `collate()`. `from_paths` keeps its own copy of the check until it is removed, since the model can't import from the API |
| 2 | `plan_recursion(datatypes, ignore_datatypes=(), recursive=False) -> RecursionPlan` | `classify.py` | L899-918 | Pure: returns a new `ignore_datatypes` list and doesn't change its input. `RecursionPlan` is a `NamedTuple` of `(recurse_into_dirs, ignore_datatypes)`. Rejects the generic directory and file-set types with `recursive`, naming the datatypes by MIME-like name. For recursion over files only, adds `Directory` to the ignored datatypes. The folder `collate()` calls it before `prepare_build_dir`, discarding the result until step 7 uses it; `from_paths` keeps its own copy until it is removed |
| 3 | `load_metadata_tables(metadata_tables=None) -> list[MetadataTable]` | `metadata.py` | `MetadataTable.table` (lazy today) | Reads every `--metadata-table` into memory and checks that its join columns are in it, before the claim. A table is often delivered with the data (the Canfield export writes its CSV into the input directory), so it is claimed with the files around it and is no longer at its path when the tables are injected; the loaded rows are kept in the `MetadataTable`, which pickles with them. A missing, unreadable or mismatched table fails before anything is created or moved Since `list_input_files` leaves the tables out, a table in an input directory is no longer claimed; loading early still fails a bad table before the claim, and lets the tables be passed between tasks. |
| – | `merge_path_metadata(path_metadata=(), path_metadata_regex=()) -> list[PathMetadataRegex]` | `metadata.py` | `sources/folder/api/collate_api.py` | Translates the glob-like `--path-metadata` patterns (`accessionflow.helpers.path_pattern.path_metadata_pattern_to_regex`) and merges them with `--path-metadata-regex`, patterns first. Raises `ValueError` on a bad pattern, so it runs with the checks. Its result is given to `apply_path_metadata` (step 11). Moved from the folder source on 2026-11-26 |

##### Set up the run directory

Make the run's UID and build directory, and take ownership of the input files.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 4 | `make_run_uid(now=None, rng=None) -> str` | `claim.py` | L980-988 | The UTC time as `YYYYMMDDHHMMSS`, an underscore, and 6 random hex characters (`secrets.token_hex(3)`), e.g. `20261125073856_a3f09c`; the clock and the random source can be injected (principle 5). UIDs sort by time, and two runs in the same second get different ones. No `.` or `-`, so it still follows the labels in a staged directory's name. It names the run's build directory, its claim directory and its accessions. Made once per run; a new run creates its build directory exclusively and makes another UID if it is taken, and a retry passes the same UID on. Until 2026-11-25 it was the first 6 hex characters of a SHA-256 over the files' sorted absolute paths, then the time, which gave two runs listing the same files in the same second the same UID. |
| 5 | `prepare_build_dir(output_dir, run_uid, exclusive=False) -> Path` | `api/staging.py` | `sources/folder/api/collate_api.py:293-297` | Creates and returns the run's own build directory, `<output_dir>/__build__/<run_uid>/`, so that runs writing to the same output directory at the same time don't collide. With `exclusive=True`, for a new run, raises `FileExistsError` if it already exists, so a UID another run has taken is caught; by default it reuses it, for a retry. Checks the run UID first (`check_run_uid`): a single path component, not hidden, not starting with `__`. Added in Phase 0; given the run UID and `exclusive` in Phase 1. |
| 6 | `claim_input_files(input_files, processing_dir, run_uid, source_roots=None) -> ClaimedFiles` | `claim.py` | new | Moves each file into `processing_dir / run_uid`, keeping its path relative to the common directory of the source roots, so that directory datatypes and file names that repeat across directories survive. The roots default to each file's directory; the CLI will pass its input directories. On the same file system a claim is an atomic `os.rename`. Across file systems (`EXDEV`) the file is copied to a hidden temporary name, the source is checked to be unchanged (size and modification time), the copy is renamed into place and the source is deleted. A changed source is left for the next run. A file that has disappeared since it was listed is logged and skipped. Checks the run UID and the roots before anything is moved (principle 12). With no files, nothing is created. Known limits: on one file system, a file still being written is moved and goes on growing in the processing area (completeness is checked by a later step); across file systems, two runs claiming the same file at once can both copy it |
| – | `ClaimedFiles` | `claim.py` | new | A frozen attrs record that pickles: the run directory, the base the layout is relative to, the source roots, and each claimed file's original path. The files are claimed into `files_dir`, the run directory's `files/` subdirectory (`CLAIMED_FILES_DIRNAME`), apart from the plan, so that no input file can clash with `claimed.json`. `claimed_roots` gives the roots' equivalents in `files_dir`, for step 7, and `original_of` the original path of a claimed file or of a directory that holds claimed files (e.g. a directory datatype), for step 11. `ClaimedFiles.load(run_dir)` rebuilds it from `claimed.json`. `run_dir` is always absolute, as file-sets' paths are, and `original_of` accepts relative paths too. The plan is written atomically once, before any file moves; it isn't rewritten after each move, which would be quadratic for large runs. A retry with the same `run_uid` uses the saved plan and reads each file's state from the file system: a file already claimed is skipped, and a source left behind by a crash after a copy across file systems is deleted if it is unchanged (principle 9) |

`PROCESSING_NAME_DEFAULT = "__processing__"` and `CLAIMED_MANIFEST = "claimed.json"` are
exported with the steps. The processing area defaults to `<output_dir>/__processing__`, on the same file system
as the staging directory, so that saving into the build directory can still hard-link.
The claim is only atomic when the source is on that file system too.
`claim_input_files` logs one warning when it has copied files across file systems,
the claim's counterpart to `warn_if_hardlinks_unavailable`; only the claim
knows whether it renamed or copied, so there is no separate step.

##### Determine the file-sets

Turn the claimed files into file-sets of the wanted datatypes.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 7 | `expand_claimed_paths(claimed, datatypes, recursion, recursive=False) -> list[Path]` | `classify.py` | L920-968 | Takes the `RecursionPlan` from step 2. Applies today's expansion rules to the outermost claimed roots: without `recursive`, each root's top-level entries (so a subdirectory such as a DICOM directory is classified whole); with `recursive` and only file datatypes, every claimed file (the directories that today's glob also lists, only for `Directory` to drop them, are left out); with `recursive` and a directory format among the wanted or ignored datatypes, the prune-on-match walk, copied from `_recursive_collect` (L265) as `_walk_pruning`, so `--recursive` and directory datatypes behave as they do now. Only claimed files and the directories that hold them are returned, so a leftover temporary file or anything else in the run directory is never classified. A root inside another root is dropped, so nothing is listed twice; the caller claims with its input directories as the source roots to get today's top-level entries. `from_paths` keeps `_recursive_collect` until it is removed |
| 8 | `classify_paths(fspaths, datatypes, ignore_datatypes=(), allow_unrecognised=()) -> list[FileSet]` | `classify.py` | L990-999 | `fileformats.core.from_paths` with the wanted datatypes before the ignored ones, so the first match wins and a wanted datatype beats an ignored one. The file-sets are returned sorted by path, because `fileformats` returns them in an order that changes from run to run, and with it the order of the accessions. `ignore_datatypes` is `RecursionPlan.ignore_datatypes` from step 2. File-sets of ignored datatypes are returned; step 10 drops them. The `allow_unrecognised` regular expressions are matched from the start of each path's base name, and any other unrecognised path raises `FormatMismatchError` |
| 9 | `drop_ignored_filesets(filesets, datatypes, ignore_datatypes=()) -> list[FileSet]` | `classify.py` | L1009-1019 | Returns a new list without the file-sets of the ignored datatypes (`RecursionPlan.ignore_datatypes`), matched with `isinstance`. A wanted datatype wins, so a wanted `DirectoryOf[Json]` isn't dropped because `Directory` is ignored. The dropped file-sets' files stay in the processing area, for `finish_claim` to report |

##### Apply metadata

Add metadata to the file-sets from their paths, their types and the metadata tables.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 10 | `disable_metadata_reading(filesets, dont_read_metadata=()) -> list[FileSet]` | `classify.py` | L1000-1007 | Sets the public `fileset.metadata.read_disabled` (in `fileformats` 0.22.8, the minimum version) on each file-set that is an instance of one of the datatypes, so a subclass matches too. Changes the file-sets in place and returns the same ones. `from_paths` now uses the public setter too, which resolves its TODO |
| 11 | `apply_path_metadata(filesets, path_metadata_regex=(), claimed=None) -> list[FileSet]` | `metadata.py` | L1021-1035 | Matches each regular expression, in order, against the path of each file-set of its datatype (`fspath`, or `parent` for a file-set of several files such as a DICOM series), mapped back to its **original** path with `claimed.original_of`, so `--path-metadata` and `--path-metadata-regex` patterns, including ones anchored with `/`, match the same paths as today. A later pattern wins for the same field. A pattern that doesn't match raises `ValueError` naming the original path. Changes the file-sets' metadata in place and returns them. No progress bar. Without `claimed`, the file-sets' own paths are matched |
| 12 | `tag_fileset_types(filesets) -> list[FileSet]` | `metadata.py` | L1037-1041 | Sets each file-set's `__datatype__` field (`Accession.TYPE_METADATA_KEY`) to its `type_name`, e.g. `DicomSeries`, for use in `--accession`, `--acquisition` and `--resource` specs. Uses `setdefault`, so a value already set is kept: a path-metadata group of the same name (step 11 runs first) or a header field. The metadata tables (step 13) come after it and can override it. Changes the file-sets in place and returns them |
| 13 | `inject_fileset_tables(filesets, metadata_tables=None) -> list[FileSet]` | `metadata.py` | L1043 | `MetadataTable.inject_list` on the file-sets: only `fileset` tables apply, joined on the file-sets' metadata (e.g. a path-metadata field), and every column of the one matching row is merged; several matching rows raise `ValueError`. Changes the file-sets in place and returns them |

##### Form accessions

Group the file-sets into accessions, acquisitions and resources, and add the accession-level tables.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 14 | `group_into_accessions(filesets, accession_uid_field, acquisition_id_field=(), resource_field=(), on_resource_clash="error", run_uid=None) -> list[Accession]` | `group.py` | L1045-1118 | Uses the three steps above and `Accession.add_resource`, which applies the clash policy. Returns the accessions in the order their first file-sets came in, each with the run UID. Keeps its progress bar: this is where the file-sets' headers are first read for their ID fields, which can take minutes for a large DICOM delivery |
| – | `resource_label_for(fileset, resource_field=()) -> (label, derived)` | `group.py` | L1054-1072 | A DICOM collection from the `ImageType` of its first file (`dicom_image_type_to_resource_label`), or 'DICOM'; with no `--resource` spec, from the file-set's type (`_datatype_resource_label`, L169), marked derived; otherwise from the matching `--resource` spec |
| – | `acquisition_id_for(fileset, acquisition_id_field, resource_label) -> (acquisition_id, derived)` | `group.py` | L1073-1081 | From the `--acquisition` spec that matches the file-set's datatype, or, if none does, the resource's label, marked derived. The `_DERIVED_ID` sentinel (L66) stays inside |
| – | `clash_hint_for(acquisition_derived, resource_derived) -> str \| None` | `group.py` | L1082-1096 | The hint added to a resource-name clash when the IDs were derived, naming the specs to give |
| 15 | `inject_accession_tables(accessions, metadata_tables=None) -> list[Accession]` | `metadata.py` | L1119-1128 | `MetadataTable.inject_list` on the accessions, then their acquisitions, then their resources, as today; only tables of the matching row frequency apply. An accession's or acquisition's metadata includes the fields its file-sets agree on, so it can join on e.g. `PatientID`. Changes the metadata in place and returns the same accessions |

`dicom_image_type_to_resource_label` stays in `model/accession.py`, because the Orthanc
source uses it too. Until `from_paths` is removed, `group.py` imports
`_datatype_resource_label` and `_DERIVED_ID` from the model, which still uses them; they
move into `group.py` with the removal.

##### Assign and deliver

Label each accession and deliver it to the target directory as `<labels>_<run_uid>`. `assign_labels` and `move_to_target` are the per-accession unit. Until 2026-11-25 step 17 was `stage_accession`, which delivered unlabelled accessions as `_.<uid>` for the `label` stage.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 16 | `warn_if_hardlinks_unavailable(accessions, build_dir, copy_mode, conversion_map=None) -> list[Path]` | `save.py` | L118-169 | Moved here from `api/collate_api.py`, which imports it. Same checks and warning, now also returning one file of each resource that can't be hard-linked. The output directory it names is worked out from the build directory (`<output_dir>/__build__/<run_uid>`), or is the build directory itself if it isn't in a `__build__` directory. Once collate claims its input, it compares the processing area, not the source, with the build directory, so it only warns if the processing area is put elsewhere |
| 17 | `assign_labels(accession, label_fields, acquisition_field=None, constant_labels=None, store_type=None) -> Accession` | `assign.py` | `api/label_api.py`, `Accession.label` | Labels the accession from its metadata, e.g. XNAT's project, subject and session, with constant labels, an acquisition description and the store type. Raises `LabelsNotAssignedError` (an `AccessionParseError`) naming the missing fields, instead of using placeholder labels, so the accession is passed to `finish_claim` as failed. Changes the accession in place and returns it. |
| 18 | `move_to_target(accession, build_dir, output_dir, claimed, copy_mode=hardlink_or_copy, collation_map=None, conversion_map=None) -> Path` | `save.py` | `api/collate_api.py:83-106` | Delivers a labelled accession to `<output_dir>/<labels>_<run_uid>/` (`Accession.staging_dirname`): `save_to_build_dir`, then `move_into_place`, then `remove_claimed_files`. Raises `ValueError` if the accession isn't labelled. Raises on failure; a failure before the move leaves the target untouched and the files in the processing area. Once the move succeeds it writes a marker, `build_dir/<dirname>.staged` (`STAGED_MARKER_SUFFIX`), so a retry after a failed delete skips the save and the move and only deletes; a crash in the instant between the move and the marker still makes the retry fail on the move, without losing data. Replaces `stage_accession`. |
| – | `save_to_build_dir(accession, build_dir, copy_mode=hardlink_or_copy, collation_map=None, conversion_map=None) -> Path` | `save.py` | L87-97 | Removes the accession's scratch directory (`build_dir/<staging_dirname>`) left by an earlier attempt, then `Accession.save`s it there (principle 9). Doesn't touch the run's shared `build_dir/__build__` |
| – | `remove_claimed_files(accession, claimed) -> list[Path]` | `save.py` | L100-106 | Deletes the accession's files from the processing area (a directory datatype's directory with `rmtree`), skipping any already gone, so it can be retried. Refuses, before deleting anything, if any file isn't in `claimed.files_dir`, so it never deletes from a live input. Always run, replacing the optional `unlink_source`. Empty directories are left for `finish_claim` |

The wait-period check (L71-81) is removed, with `Accession.last_modified`
(`model/accession.py:2026`), which nothing else uses.

##### Clean up

Remove what the run leaves in the processing area and the build directory.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 19 | `finish_claim(claimed, unprocessed_dir, failed=(), ignored=()) -> list[Path]` | `claim.py` | new | After staging: deletes any hidden `.<name>.claiming` file left by a copy across file systems that was stopped part way (its source is still in the input), and prunes the empty directories (`prune_empty_dirs`). If no files are left, removes the run directory. Otherwise writes `unprocessed.json` (`UNPROCESSED_MANIFEST`) into it, giving for each file left its path, its original path and why it was left (`failed`, with the accession and its error, for the files of the `failed` accessions; `ignored`, with its datatype, for the `ignored` file-sets; otherwise `unrecognised`), and moves the whole run directory, plan included, to `<unprocessed_dir>/<run_uid>/`. Returns the files' new paths. Safe to retry. |
| 20 | `remove_build_dir(build_dir) -> list[Path]` | `api/staging.py` | new | Removes empty subdirectories first (`prune_empty_dirs`), including the empty `__build__` that `Accession.save` leaves, then the run's build directory if no files are left. Otherwise keeps it, logs a warning and returns what is left. `__build__` itself stays, as other runs share it. |
| – | `abandon_claim(claimed, error_dir, error) -> Path` | `claim.py` | new | For a run that raises after the claim: tidies the run directory as `finish_claim` does, writes the error (type, message and traceback) to `error.json` (`ERROR_MANIFEST`) in it, and moves it to `<error_dir>/<run_uid>/`. The composite calls it in an `except` and re-raises. |

#### Phase 1 design records

The design changes made to Phase 1 after its steps were first planned, moved from
`ROADMAP.md` when they were done (2026-11-25). Each gives the decisions taken, then the
plan as it was written. They also settled the roadmap's open question about the run
directories `finish_claim` used to leave in `__processing__`: their files go to an
unprocessed directory, and a run that raises after the claim goes to an error
directory.

##### a random run UID

Status: **Done** (2026-11-25). The UID is `YYYYMMDDHHMMSS_<6 random hex characters>`,
e.g. `20261125073856_a3f09c`; the underscore makes it easier to read and is safe
everywhere the UID goes. `prepare_build_dir(output_dir, run_uid, exclusive=False)`
creates a new run's directory exclusively with `exclusive=True`, and the folder
`collate()` makes up to five UIDs until one is free. See `CHANGELOG.md`.

**Keep the timestamp and replace the path hash with random characters.** Today
`make_run_uid` (step 4) is the first 6 hex characters of a SHA-256 over the files' paths,
then the UTC time to the second. The timestamp is worth keeping: run directories sort
by time, and a staged accession's name (`<labels>.<run_uid>`) shows when it was
collated. The hash adds little:

- It's too short to identify or check the file list, and the timestamp already makes
  every run's UID different, so it doesn't make the UID reproducible either. A retry
  has to be passed the original UID whichever way it is made.
- **Two runs that list the same files in the same second get the same UID.** This is
  the race the claim exists for, e.g. two workers polling one input directory. The
  second run would find the first's `claimed.json`, take itself for a retry, use the
  first's plan, count the files the first moved as already claimed, and both would
  process the same files in the same run and build directories. With a random part,
  they get separate run directories, and each file's atomic rename goes to exactly one
  of them.
- It costs about 3 µs a file (3 s for a million files), only to build and sort the
  path strings.

A random name checked for existence before it is created would still race: two runs
can both see it free. The directory is instead created exclusively, so a clash is
caught rather than only unlikely.

Changes:

- **`make_run_uid(now=None, rng=None) -> str`** returns the UTC time as
  `YYYYMMDDHHMMSS` followed by random hex characters (e.g. `secrets.token_hex(3)`, 6
  characters, or more). It no longer takes the input files. The random source can be
  injected for tests, as the clock can (principle 5). The UID still holds no `.`, so it
  still parses back from staged directory names (`_labels_from_dirname`).
- **The run's directories are created exclusively.** The first directory a run
  creates, its build directory (`prepare_build_dir`, step 5), uses `mkdir` without
  `exist_ok`, and the run makes a new UID if that raises `FileExistsError`. A retry
  passes its UID on and skips the creation (e.g. an `exist_ok`/`retry` argument), and
  the claim keeps reading an existing `claimed.json` as a retry, which a real retry
  relies on.
- **The interim call in the folder `collate()`** (`make_run_uid` on its input paths)
  becomes `make_run_uid()`.
- **Tests:**
  - the format: time first, then the random part, with no `.`
  - an injected clock and random source give a fixed UID
  - two calls in the same second differ
  - an exclusive-create clash gives a fresh UID
  - the round trip through `_labels_from_dirname`
  - the pinned-hash, file-order and relative-path tests in
    `api/tests/collate/test_claim.py` go
- **Records:** the step 4 rows of the CHANGELOG reference, a Step API entry for the
  changed signature, and a Staging layout entry for the new run-directory names (data
  already staged doesn't need draining: old and new UIDs both parse).

##### the revised flow

Status: **Done** (2026-11-25), with these decisions:

- The run directory, `<working_dir>/<run_uid>/`, holds only the claimed input
  (`claimed.json` and `files/`); `claim_input_files` takes `working_dir` (renamed from
  `processing_dir`). Accessions are built in `<output_dir>/__build__/<run_uid>/`, on
  the target's file system, so the final rename is atomic.
- `output_dir` is the target directory.
- Step 17, `assign_labels`, labels each accession from its metadata (`Accession.label`)
  and raises `LabelsNotAssignedError` instead of using placeholder labels, so an
  accession that can't be labelled is passed to `finish_claim` as failed and its files
  go to the unprocessed directory.
- Step 18, `move_to_target`, replaces `stage_accession`: it saves the labelled
  accession, moves it to `<output_dir>/<labels>_<run_uid>/` and deletes its claimed
  files, with the same retry marker.
- Labelled directories are named `<labels>_<run_uid>` by every stage
  (`Accession.staging_dirname`). The run UID contains `_` itself, so it is recognised by
  its whole pattern at the end of the name (`helpers/run_uid.py`, `split_run_uid`);
  `_` also avoids the legacy `-` delimiter. A run UID that isn't recognisable keeps
  `.`. Old `<labels>.<run_uid>` names still load.
- The `label` command is retired once every source labels in collate (see the CLI
  section and Phase 5).

The plan as it was written:

The collate flow changes in four ways:

1. **Each run works in `<working_dir>/<run_uid>/`.** `working_dir` is a new parameter
   of the collate API. It replaces the run's two areas under the output directory,
   `__processing__/<run_uid>/` (the claimed input) and `__build__/<run_uid>/` (the
   scratch for saving), with one directory per run.
2. **`stage_accession` (step 17) comes out of the flow.** Accessions are no longer
   saved to the output directory under a pre-label name (`_.<uid>`) for a separate
   `label` stage to pick up.
3. **An assign step takes its place.** It assigns each accession its labels,
   `project.subject.session`, from its metadata. This is the job the `label` stage
   does today (`api/label_api.py::label`, `Accession.label` at
   `model/accession.py:1088`), brought into collate.
4. **A new step after the assign step moves each accession's files to the target
   directory** for the next process, in a directory named
   `<project>.<subject>.<session>-<run_uid>`.

The order after grouping (step 14) becomes:

| Step | Replaces | Kind |
| --- | --- | --- |
| `inject_accession_tables` | step 15, unchanged | batch |
| `warn_if_hardlinks_unavailable` | step 16, now comparing `working_dir` with the target directory | batch |
| assign: label each accession from its metadata | step 17, `stage_accession` | per accession |
| move to the target directory, `<project>.<subject>.<session>-<run_uid>/` | new | per accession |
| finish the run: move what is left to the unprocessed directory (`finish_claim`), or to the error directory if the run raised (`abandon_claim`), and remove the run directory | steps 18 and 19, `finish_claim` and `remove_build_dir` | batch |

Steps 0–14 are unchanged, except that `prepare_build_dir` (step 5) and
`claim_input_files` (step 6) use `<working_dir>/<run_uid>/` instead of the two areas
under the output directory.

To confirm before the design is detailed:

- **The layout inside `<working_dir>/<run_uid>/`:** e.g. `claimed.json`, `claimed/`
  for the claimed input and `build/` for saving, so that the input, which is the only
  copy until it has been moved on, stays apart from disposable scratch.
- **Labelling options:** which options supply the label fields, the constant labels
  and the acquisition description. Today they belong to each store's `label` command
  (`--label`, store type), and would be new options on `collate folder`. Adding options
  keeps the CLI backwards compatible (principle 11).
- **Accessions whose labels can't be assigned** (a field missing from the metadata):
  today the `label` stage saves them to `__invalid__`. Are they left in the run
  directory for `finish`, or moved to an invalid area of the target directory?
- **What the move step moves:** the claimed files themselves, renamed into the target
  layout (one rename per file, no copy), or the accession saved into `build/` and then
  renamed into place, as `stage_accession` does, with its manifests and metadata files.
  Retrying the move needs the same care as `stage_accession`'s marker.
- **The directory name:** `<project>.<subject>.<session>-<run_uid>` separates the run
  UID with `-`, where today's staged names use `.` (`staging_dirname`,
  `_labels_from_dirname`). Labels can contain `-`, so the name has to be split at the
  last `-`, and the run UID must never contain one; the parser and `staging_dirname`
  change to match.
- **The `label` stage and Phase 5:** with labelling in collate, does the `label` command
  stay for other sources (e.g. Orthanc), or is it retired? Phase 5 is replanned
  accordingly, and the store commands that read the staged directories (`store xnat`,
  `store folder`) must accept the new names.
- **The output directory parameter:** whether `output_dir` becomes the target
  directory, or a separate target parameter is added.

##### leftover files to an unprocessed directory

Status: **Done** (2026-11-25), with these decisions:

- `finish_claim(claimed, unprocessed_dir, failed=(), ignored=())` moves the whole run
  directory, with its plan, to `<unprocessed_dir>/<run_uid>/`, after writing
  `unprocessed.json` into it: for each leftover file, its path, its original path, and
  why it was left (`failed` with the accession and its error, `ignored` with its
  datatype, or `unrecognised`). With nothing left, the run directory is removed.
- A run that raises after the claim moves its claim to an **error directory** instead:
  the new `abandon_claim(claimed, error_dir, error)` moves the run directory to
  `<error_dir>/<run_uid>/`, with the error in `error.json`. The composite calls it in
  an `except` and re-raises.
- Both move with a rename on one file system, and across file systems with a copy to a
  hidden name, a rename into place and a delete, safe to retry.

The plan as it was written:

**Part of `finish_claim` (step 18) is to move any files that are left to an unprocessed
directory, which is given as a parameter.** Today it keeps the run directory, with its
plan, and reports the files left in it. They are files that no datatype recognised but
`--allow-unrecognised` let through, file-sets of an `--ignore-datatype`, and the files of
accessions that failed to stage, and they are the only copies, since the claim moved
them out of the input. Moving them to one known place, outside the processing area,
makes them easy to find and deal with, and lets the run directory always be removed.
This answers the open question about what happens to the run directories that
`finish_claim` leaves.

Changes:

- **A new `unprocessed_dir` parameter** for `finish_claim`, and for the collate API and
  the composites that call it. It becomes the "finish the run" step of
  the revised flow.
- **`finish_claim` moves each leftover file** into `unprocessed_dir` after deleting any
  `.claiming` temporary files and pruning the empty directories, then removes the run
  directory. It returns the files' new paths and logs one warning, giving their count
  and where they went.
- **The move is safe to retry** (principle 9): a file already moved is skipped, and the
  run directory is only removed once every leftover has been moved. Across file systems
  the move is a copy, a check and a delete, as in the claim.

To confirm:

- **The layout in `unprocessed_dir`:** e.g. `<unprocessed_dir>/<run_uid>/`, keeping each
  file's path relative to the source roots, so that files from different runs, and
  repeated names, don't collide and can be traced back.
- **Whether the plan (`claimed.json`) goes with them**, so that each file's original
  path is kept.
- **Whether the reason a file was left is recorded** (unrecognised, ignored, or failed
  to stage, with the error), e.g. in a manifest next to the files. `finish_claim` can
  only tell the first two apart from the third if the composite passes it the errors
  from staging.
- **A run that raises after the claim** (e.g. a `FormatMismatchError` for an
  unrecognised file) never reaches `finish_claim`. Should the composite call it in a
  `finally`, as it does `remove_build_dir`, so that its files are moved to
  `unprocessed_dir` too?
- **The CLI option** that supplies it (e.g. `--unprocessed-dir`), its default, and how it
  fits with `working_dir` in the revised flow.

#### Phase 1 composites

The composites of the collate steps, moved from `ROADMAP.md` when they were done
(2026-11-26), with the two Phase 1 test items they completed. The dated entries record
each step's changes.

Later the same day, C2's `collect_accessions` and C3's `deliver_accessions` were
restructured into four composites, one per stage of a run: `build_filesets`,
`apply_fileset_metadata`, `build_accessions` and `move_accessions` (see the dated
entries). The record below is as C1–C5 were built. As planned:

> Plain-Python sequences of the steps, which the CLI runs; the flows
> repository wraps the same steps in the same order (principle 10). Their signatures can
> change. They are built in five steps, each one PR that keeps the suite green and adds
> its own `CHANGELOG.md` entry. The folder `collate()` keeps its many callers (the CLI and
> about 20 tests, all with `input_paths=...`) until the CLI step, so the new composite is
> built alongside it, and the name `save_accessions_to_dir` stays with the old function in
> `api/collate_api.py` until the removals step.

##### C1. Collect the failures, not only their messages

Status: **Done** (2026-11-25).

- `for_each_accession(accessions, step, desc, raise_errors=False, name_of=...)`
  (`api/staging.py`) returns `list[tuple[T, str]]`, each failed item with its error
  message, instead of `list[str]`, because `finish_claim` needs the failed accessions.
  `log_stage_summary` is given the messages. Nothing but its tests calls it yet; they
  are updated in `api/tests/test_staging.py`.

##### C2. `collect_accessions`, steps 7–15

Status: **Done** (2026-11-26). In a new `accessionflow/api/collate/composites.py`.

```python
collect_accessions(
    claimed, datatypes, recursion, *, accession_uid_field, recursive=False,
    allow_unrecognised=(), dont_read_metadata=(), path_metadata_regex=(),
    metadata_tables=(), acquisition_id_field=(), resource_field=(),
    on_resource_clash="error", run_uid=None,
) -> CollectedAccessions
```

- Runs `expand_claimed_paths`, `classify_paths`, `disable_metadata_reading`,
  `drop_ignored_filesets`, `apply_path_metadata` (with `claimed`),
  `tag_fileset_types`, `inject_fileset_tables`, `group_into_accessions` and
  `inject_accession_tables`, in the order of the steps table.
- `CollectedAccessions` is a frozen attrs record that pickles: the `accessions`, and the
  `ignored` file-sets (the classified file-sets `drop_ignored_filesets` dropped), which
  `finish_claim` needs.
- A `FormatMismatchError` from classification names the claimed paths, so a note
  (`add_note`) lists the unrecognised files' original paths (`claimed.original_of`)
  and the run directory.
- Tests: `api/tests/collate/test_composites.py`, which took over the tests that
  chained steps 7–14 by hand from `test_group.py` and `test_metadata.py`.
- **Found:** with `--recursive`, a directory that matches an ignored directory format
  (e.g. `DirectoryOf[Csv]`) was skipped whole by `expand_claimed_paths`, so
  `finish_claim` recorded its files as `unrecognised` instead of `ignored`. Fixed in
  C4.

##### C3. `deliver_accessions`, steps 16–18

Status: **Done** (2026-11-26). In `composites.py`.

```python
deliver_accessions(
    accessions, build_dir, output_dir, claimed, label_fields, *,
    acquisition_field=None, constant_labels=None, store_type=None,
    copy_mode=hardlink_or_copy, collation_map=None, conversion_map=None,
    raise_errors=False,
) -> list[tuple[Accession, str]]
```

- `warn_if_hardlinks_unavailable`, then `for_each_accession` over `assign_labels`
  followed by `move_to_target`.
- Returns the accessions that failed, with their errors, including
  `LabelsNotAssignedError`, ready for `finish_claim`.
- Tests, in `api/tests/collate/test_composites.py`:
  - one accession delivered, one that can't be labelled and one whose save fails. This
    is `test_claim.py`'s end-to-end test, moved and run on `collect_accessions` and
    `deliver_accessions`.
  - all delivered
  - `raise_errors=True` raising the first failure
  - the hard-link warning given once, before anything is delivered

##### C4. The new folder composite, `collate_files`

Status: **Done** (2026-11-26). In `sources/folder/api/collate_api.py`, alongside
today's `collate()`.

```python
collate_files(
    input_files, output_dir, working_dir, unprocessed_dir, error_dir, label_fields, *,
    datatypes=(DicomSeries,), ignore_datatypes=(), source_roots=None, recursive=False,
    allow_unrecognised=(), dont_read_metadata=(),
    accession_uid_field=DEFAULT_ACCESSION_UID_FIELD,
    acquisition_id_field=DEFAULT_ACQUISITION_ID_FIELD,
    resource_field=DEFAULT_RESOURCE_FIELD, path_metadata=(), path_metadata_regex=(),
    metadata_tables=None, on_resource_clash="error", acquisition_field=None,
    constant_labels=None, store_type=None, copy_mode=hardlink_or_copy,
    collation_map=None, conversion_map=None, raise_errors=False,
) -> list[str]
```

- The ID-spec parameters take the steps' names (`accession_uid_field`, ...), not the
  old `collate()`'s (`accession_uid`, ...).
- Checks first, before anything is changed: `check_datatypes`, `plan_recursion`,
  `load_metadata_tables` and `merge_path_metadata`. Then `_create_run_directory(output_dir)`, the
  `make_run_uid` / `prepare_build_dir(exclusive=True)` loop, now shared with
  `collate()`.
- Then, in a `try`: `claim_input_files`, `collect_accessions`, `deliver_accessions` and
  `finish_claim(claimed, unprocessed_dir, failed, collected.ignored)`. Its
  `except Exception` calls `abandon_claim(claimed, error_dir, e)` and re-raises. A
  claim that raised partway is reloaded from its plan (`ClaimedFiles.load`) to be
  abandoned. Its `finally` calls `remove_build_dir(build_dir)`. An interrupt leaves the
  claim in the working directory.
- Returns the error messages. It doesn't log them: summarising is a CLI concern
  (`cli/runner.py`), so the CLI step calls `log_stage_summary` (see the CLI step in `ROADMAP.md`).
- Tests, in `sources/folder/tests/test_collate_files.py`, on small JSON trees:
  - a run that delivers, with a leftover moved to `unprocessed_dir`
  - an accession that can't be labelled, recorded as failed
  - a run that raises (an unrecognised file), whose claim goes to `error_dir`
  - `raise_errors=True`, which abandons the run
  - a claim that raises partway
  - the **race test** (see the race test below): files added to the input directory during
    a run stay there for the next run, which collates them
  - a clash of run UIDs, and every UID taken
  - `source_roots` set to the input directory, so its top-level entries are classified
    whole, as today
  - with `--recursive`, an ignored directory recorded as ignored
  - no input files, and a bad path-metadata pattern that changes nothing
- **Also fixed:** with `--recursive`, `expand_claimed_paths` now yields a directory that
  matches an ignored directory format, rather than skipping it. It is classified and
  dropped as ignored, so `finish_claim` records its files as `ignored` (found in C2).

##### C5. Port the `from_paths` tests

Status: **Done** (2026-11-26). The regression net, before anything is removed.

- **Both paths run the same tests.** `api/tests/collate/from_paths_port.py` holds
  `collect_like_from_paths`. It takes `from_paths`' arguments, plus a `working_dir`,
  then lists, claims and runs `collect_accessions`.
  - `model/tests/test_accession.py` and `api/tests/test_collate.py` each have a
    `collect` fixture parametrized over `from_paths` and `steps`.
  - The 16 tests that called `Accession.from_paths` call `collect` instead and keep
    their assertions, so each one checks that both paths agree. They all do.
  - The `patient_id` fixture uses the steps on a copy of the DICOM directory.
  - `test_recursive_collect_prunes_on_match` stays on `_recursive_collect` until it is
    removed. Its port is `test_expand_recursion_prunes_on_directory_datatypes`.
- **The DICOM tests of the folder `collate()` have `collate_files` counterparts**, in
  `sources/folder/tests/test_collate_files.py`. They check what changes: labelling and
  the delivered names.

  | Old `collate()` test | Counterpart |
  | --- | --- |
  | `test_collate_creates_pre_label_session_dir` | `test_dicom_delivered_labelled` |
  | `test_collate_output_reloadable_with_no_labelled_ids` | `test_dicom_delivered_reloads_with_labels` |
  | `test_collate_injects_session_metadata_from_table` | `test_dicom_accession_metadata_from_table` |
  | `test_collate_converts_directory_to_zip` | `test_dicom_directory_converted_to_zip` |
  | `test_collate_warns_when_hardlinks_unavailable` | `test_dicom_warns_when_hardlinks_unavailable` |
  | `test_collate_hashes_each_resource_once` | `test_dicom_hashes_each_resource_once` |
  | `test_collate_collects_errors_without_raising` | `test_no_input_files` |
  | `test_collate_unrecognised_file_raises_without_allow_unrecognised`, `..._allow_unrecognised_pattern_not_matching_still_raises` | `test_run_that_raises_is_moved_to_the_error_dir` |
  | `test_collate_allow_unrecognised_skips_matching_files` | `test_delivers_and_leaves_the_rest` |
  | `test_collate_ignore_datatypes_excludes_recognised_but_unwanted_files` | `test_recursive_ignored_directory_recorded_as_ignored`, `test_classify.py` |
  | `test_collate_without_ignore_datatypes_raises_on_recognised_extra_type` | `test_classify.py` (`classify_paths` raising) |
  | `test_collate_ignore_datatypes_contradicting_datatype_raises`, `test_collate_recursive_generic_directory_raises` | `test_classify.py` (`check_datatypes`, `plan_recursion`) |
  | `test_collate_makes_a_new_run_uid_on_a_clash` | `test_run_uid_clash_makes_another` |
  | `test_collate_creates_build_dir`, `test_collate_removes_build_dir_when_raising` | `test_delivers_and_leaves_the_rest`, `test_run_that_raises_is_moved_to_the_error_dir` |

##### Tests completed with the composites

- **The race test**: files are added to the input directory while a collation runs.
  Only the files listed at the start are collated, and the new ones stay for the next
  run. The claim's part is tested in `api/tests/collate/test_claim.py`; the end-to-end
  test, through `collate_files`, is
  `test_files_that_arrive_during_a_run_wait_for_the_next` in
  `sources/folder/tests/test_collate_files.py` (C4).
- **Ported tests**, keeping their assertions as the regression net (C5): the 15 calls
  to `Accession.from_paths` in `model/tests/test_accession.py` and the 2 in
  `api/tests/test_collate.py`, which now run on both `from_paths` and the steps.

#### Phase 1 combine

The accession combiner, moved from `ROADMAP.md` when it was done (2026-11-26). The dated
entries record its changes.

Status: **Done** (2026-11-26). The accession combiner, the second part of collate, in
`accessionflow/api/collate/combine.py` (steps) and `api/collate/composites.py` (the
composite). Wiring it into `collate folder`, with `--wait-period` as the quiet period,
is part of the CLI step (see `ROADMAP.md`).

**Run accessions** are what `collate_files` delivers: one accession per
project.subject.session per run, named `<labels>_<run_uid>`. The `output_dir` given to
`collate_files` is the run-accessions directory. Since every run's accessions have
their own names, collate never merges two runs' data. Only the combiner does.

**The quiet period.** A session's run accessions are combined once the newest of them
is older than the quiet period. The age comes from the time in the run UID
(`run_uid_time`, `helpers/run_uid.py`), not from file times, so a retried delivery
doesn't reset it.

**The combined accession** is named `<labels>_<primary_label>`. The caller gives
`primary_label` as a fixed string (e.g. `combined`): letters, digits and `-`, and not
in the form of a run UID. Its metadata records the run accessions it was combined from
(`__combined_from__`).

**Names.** A name such as `P.S.sess_combined` can't be told from a session label
`sess_combined` by the name alone, so the name is read with the labels every accession
saves in its metadata (`__labels__`):

- `split_name_suffix` (`helpers/run_uid.py`) splits off a run UID or a primary label.
- `Accession._labels_from_dirname` and `SessionListing.ids` (local and S3) use the
  saved labels. Names without them parse as before.
- `staging_dirname` joins a suffix that is a run UID or a valid primary label with `_`.
  Any other suffix is joined with `.`, as before.

**Merging.**

- **Resources:** every run accession's resources are added, oldest first, with
  `Accession.add_resource`. An identical resource (the same checksums) is kept once,
  and any other clash follows `on_resource_clash`.
- **Metadata:** the metadata each level holds of its own (e.g. from a metadata table)
  is carried over. Values collated from the level below are collated again. A key that
  two run accessions give different values is an error, as are different store types
  or fields.

**The steps:**

| # | Step | Kind |
| --- | --- | --- |
| – | `check_primary_label(primary_label)` | checks the arguments |
| 1 | `list_run_accessions(runs_dir) -> list[RunAccessionGroup]`: groups the run accessions by their labels, oldest first | batch |
| 2 | `select_quiet_groups(groups, quiet_period, now=None)` | batch |
| 3 | `create_run_directory(output_dir)` (`claim.py`, shared with `collate_files`) | batch |
| 4 | `combine_accessions(group, on_resource_clash="error") -> Accession` | **per group** |
| 5 | `deliver_combined(accession, group, build_dir, output_dir, primary_label, copy_mode=...) -> Path` | **per group** |
| 6 | `remove_run_accessions(group)` | **per group** |
| – | `abandon_group(group, error_dir, error, run_uid) -> Path`, for a group that fails | **per group** |
| 7 | `remove_build_dir` (`api/staging.py`) | batch |

- `RunAccessionGroup(name, run_dirs, newest)` is a frozen attrs record that pickles,
  and is the unit a flow maps over.
- **An existing combined accession is an error.** `deliver_combined` never changes an
  accession already in the output directory, so the group goes to the error directory.
  The exception is a retry: when the existing accession's `__combined_from__` names
  the same run accessions, an earlier attempt delivered it and crashed before
  `remove_run_accessions`. It is kept, and only the run accessions are removed.
- `abandon_group` moves the group's run accessions to `<error_dir>/<labels>_<run_uid>/`,
  where `run_uid` is the combine run's. It writes an `error.json` like `abandon_claim`
  (`write_error_record`).

**The composite** is `combine_run_accessions(runs_dir, output_dir, error_dir,
quiet_period, primary_label, *, on_resource_clash="error", copy_mode=...,
now=None, raise_errors=False) -> list[str]`.

- It checks the arguments, then lists and selects the groups. If none is quiet, it
  creates nothing.
- Otherwise it makes a build directory and runs steps 4–6 per group through
  `for_each_accession`, abandoning a group that fails. It removes the build directory
  in a `finally`.
- It returns the error messages for the caller to log.

**Races.** A run accession delivered while the combiner runs is either newer than the
quiet period, so its group isn't selected, or it arrived after the listing, so it is
left for the next combine.

**Tests:** `api/tests/collate/test_combine.py`, which makes run accessions with
`collate_files` on small JSON trees. The name handling is tested in
`helpers/tests/test_run_uid.py` and `model/tests/test_labels.py`.

#### Dated entries

- 2026-11-27, Phase 1, added in `accessionflow.api.collate`, so that the layout of a
  claim in the processing area is defined in one place (`claim.py`), which
  `ClaimInputFiles`, `ClaimedFiles` and the folder `collate`'s failure handler all
  use:
  - `claim_run_dir(working_dir, run_uid) -> Path`: the run's claim directory,
    absolute
  - `has_claim_plan(run_dir) -> bool`: whether the claim's plan was written, i.e.
    whether it may have moved files
  - `ClaimedFiles.find(working_dir, run_uid) -> ClaimedFiles | None`: the claim of a
    run, e.g. one that raised partway, or None if it wrote no plan

- 2026-11-27, Phase 1, step classes:
  - added: `accessionflow.api.step.Step`, the base class of a step:
    `check_configuration()`, the private hooks `_check_configuration()` and
    `_require_checked()`, and the abstract `act(...)`
  - added, in `accessionflow.api.collate`, the eight step classes, each replacing a
    function:
    - `ReserveRunUid(output_dir).act() -> (run_uid, build_dir)`, replacing
      `create_run_directory(output_dir)`
    - `ClaimInputFiles(working_dir).act(input_files, run_uid, source_roots=None) -> ClaimedFiles`
    - `BuildFilesets(datatypes, ignore_datatypes=(), recursive=False, allow_unrecognised=()).act(claimed) -> ClassifiedFilesets`.
      Its check runs `check_datatypes` and `plan_recursion`, so `act` no longer takes
      a `RecursionPlan`
    - `ApplyFilesetMetadata(dont_read_metadata=(), path_metadata=(), path_metadata_regex=(), metadata_tables=()).act(filesets, claimed) -> list[FileSet]`.
      Its check runs `merge_path_metadata` and `load_metadata_tables`
    - `BuildAccessions(accession_uid_field, acquisition_id_field=(), resource_field=(), on_resource_clash="error", metadata_tables=()).act(filesets, run_uid=None) -> list[Accession]`
    - `MoveAccessions(output_dir, label_fields, *, acquisition_field, constant_labels, store_type, copy_mode, collation_map, conversion_map, raise_errors).act(accessions, build_dir, claimed) -> list[tuple[Accession, str]]`
    - `FinishClaim(unprocessed_dir).act(claimed, failed=(), ignored=()) -> list[Path]`
    - `AbandonClaim(error_dir).act(claimed, error) -> Path`
  - removed: the functions `create_run_directory`, `claim_input_files`,
    `build_filesets`, `apply_fileset_metadata`, `build_accessions`,
    `move_accessions`, `finish_claim` and `abandon_claim`. `check_datatypes`,
    `plan_recursion`, `merge_path_metadata`, `load_metadata_tables` and the smaller
    steps stay functions

- 2026-11-26, Phase 1, removals:
  - renamed: `accessionflow.sources.folder.api.collate_api.collate_files` is
    `accessionflow.sources.folder.api.collate`, with the same signature
  - removed: `Accession.from_paths`, `Accession.last_modified`, the old folder
    `collate(input_paths, ...)` and `accessionflow.api.save_accessions_to_dir` (see
    Removed)
  - changed: `RUN_UID_RE`, `split_run_uid` and `run_uid_time`
    (`accessionflow.helpers.run_uid`) recognise only `make_run_uid`'s form,
    `YYYYMMDDHHMMSS_<6 hex>`

- 2026-11-26, Phase 1, CLI, added in `accessionflow.api.collate`:
  - `list_source_roots(input_paths, input_files) -> list[Path]`
  - `RUNS_NAME_DEFAULT` (`__runs__`), `UNPROCESSED_NAME_DEFAULT` (`__unprocessed__`)
    and `ERROR_NAME_DEFAULT` (`__error__`)

- 2026-11-26, Phase 1, option converters, added in `accessionflow.helpers.arg_types`:
  - `collation_map_from(specs) -> dict[type[FileSet], FileSet.CopyCollation]`
  - `conversion_map_from(converts) -> dict[type[FileSet] | UnionType, tuple[type[FileSet], dict[str, Any]]]`
- 2026-11-26, Phase 1, Combine, added in `accessionflow.api.collate`:
  - `check_primary_label(primary_label) -> None`
  - `list_run_accessions(runs_dir) -> list[RunAccessionGroup]`
  - `select_quiet_groups(groups, quiet_period, now=None) -> list[RunAccessionGroup]`
  - `combine_accessions(group, on_resource_clash="error") -> Accession`
  - `deliver_combined(accession, group, build_dir, output_dir, primary_label, copy_mode=hardlink_or_copy) -> Path`
  - `remove_run_accessions(group) -> None`
  - `abandon_group(group, error_dir, error, run_uid) -> Path`
  - `combine_run_accessions(runs_dir, output_dir, error_dir, quiet_period, primary_label, *, on_resource_clash="error", copy_mode=hardlink_or_copy, now=None, raise_errors=False) -> list[str]`
  - `RunAccessionGroup(name, run_dirs, newest)`, `COMBINED_FROM_KEY`
  - moved: `create_run_directory(output_dir) -> tuple[str, Path]`; added:
    `write_error_record(directory, error) -> Path`, `RUN_UID_ATTEMPTS`
- 2026-11-26, Phase 1, the composites restructured, in `accessionflow.api.collate`:
  - added: `build_filesets(claimed, datatypes, recursion, *, recursive=False, allow_unrecognised=()) -> ClassifiedFilesets`
  - added: `apply_fileset_metadata(filesets, claimed, *, dont_read_metadata=(), path_metadata_regex=(), metadata_tables=()) -> list[FileSet]`
  - added: `build_accessions(filesets, *, accession_uid_field, acquisition_id_field=(), resource_field=(), on_resource_clash="error", run_uid=None, metadata_tables=()) -> list[Accession]`
  - added: `ClassifiedFilesets(filesets, ignored)`, a frozen attrs record that pickles
  - renamed: `deliver_accessions` to `move_accessions`, with the same signature
  - removed: `collect_accessions`, `CollectedAccessions`
- 2026-11-26, Phase 1, moved:
  - `merge_path_metadata(path_metadata=(), path_metadata_regex=()) -> list[PathMetadataRegex]`,
    to `accessionflow.api.collate` (`metadata.py`)
  - `path_metadata_pattern_to_regex(pattern) -> str`, to
    `accessionflow.helpers.path_pattern`
- 2026-11-26, Phase 1, composites step C4:
  - added, in `accessionflow.sources.folder.api.collate_api`:
    `collate_files(input_files, output_dir, working_dir, unprocessed_dir, error_dir, label_fields, *, datatypes=(DicomSeries,), ignore_datatypes=(), source_roots=None, recursive=False, allow_unrecognised=(), dont_read_metadata=(), accession_uid_field=..., acquisition_id_field=..., resource_field=..., path_metadata=(), path_metadata_regex=(), metadata_tables=None, on_resource_clash="error", acquisition_field=None, constant_labels=None, store_type=None, copy_mode=hardlink_or_copy, collation_map=None, conversion_map=None, raise_errors=False) -> list[str]`
  - changed: `expand_claimed_paths` yields the ignored directories it used to skip
- 2026-11-26, Phase 1, composites step C3, added in `accessionflow.api.collate`:
  - `deliver_accessions(accessions, build_dir, output_dir, claimed, label_fields, *, acquisition_field=None, constant_labels=None, store_type=None, copy_mode=hardlink_or_copy, collation_map=None, conversion_map=None, raise_errors=False) -> list[tuple[Accession, str]]`
- 2026-11-26, Phase 1, composites step C2, added in `accessionflow.api.collate`:
  - `collect_accessions(claimed, datatypes, recursion, *, accession_uid_field, recursive=False, allow_unrecognised=(), dont_read_metadata=(), path_metadata_regex=(), metadata_tables=(), acquisition_id_field=(), resource_field=(), on_resource_clash="error", run_uid=None) -> CollectedAccessions`
  - `CollectedAccessions(accessions, ignored)`, a frozen attrs record that pickles
- 2026-11-25, Phase 1, composites step C1, changed in `accessionflow.api.staging`:
  - `for_each_accession(accessions, step, desc, raise_errors=False, name_of=...) -> list[tuple[T, str]]`
- 2026-11-25, Phase 1, steps 6, 17 and 18:
  - added: `assign_labels(accession, label_fields, acquisition_field=None, constant_labels=None, store_type=None) -> Accession`
  - added: `move_to_target(accession, build_dir, output_dir, claimed, copy_mode=..., collation_map=None, conversion_map=None) -> Path`
  - removed: `stage_accession`
  - changed: `claim_input_files(input_files, working_dir, run_uid, source_roots=None)`,
    with `working_dir` renamed from `processing_dir`
- 2026-11-25, Phase 1, step 18:
  - changed: `finish_claim(claimed, unprocessed_dir, failed=(), ignored=()) -> list[Path]`
  - added: `abandon_claim(claimed, error_dir, error) -> Path`, `UNPROCESSED_MANIFEST`
    and `ERROR_MANIFEST`
- 2026-11-25, Phase 1, steps 4 and 5, changed:
  - `make_run_uid(now=None, rng=None) -> str`, which no longer takes the input files
  - `prepare_build_dir(output_dir, run_uid, exclusive=False) -> Path`
- 2026-11-25, Phase 1, step 0, changed in `accessionflow.api.collate`:
  - `list_input_files(input_paths, exclude_paths=(), metadata_table_paths=()) -> list[Path]`
- 2026-11-24, Phase 1, step 18:
  - added in `accessionflow.api.collate`: `finish_claim(claimed) -> list[Path]`
  - added in `accessionflow.api.staging`: `prune_empty_dirs(root) -> None`
- 2026-11-24, Phase 1, step 17, added in `accessionflow.api.collate`:
  - `save_to_build_dir(accession, build_dir, copy_mode=..., collation_map=None, conversion_map=None) -> Path`
  - `remove_claimed_files(accession, claimed) -> list[Path]`
  - `stage_accession(accession, build_dir, output_dir, claimed, copy_mode=..., collation_map=None, conversion_map=None) -> Path`
  - `STAGED_MARKER_SUFFIX`
- 2026-11-24, Phase 1, step 16, moved to `accessionflow.api.collate`:
  - `warn_if_hardlinks_unavailable(accessions, build_dir, copy_mode, conversion_map=None) -> list[Path]`,
    which returned `None` before
- 2026-11-24, Phase 1, step 15:
  - added in `accessionflow.api.collate`:
    `inject_accession_tables(accessions, metadata_tables=None) -> list[Accession]`
  - changed: `classify_paths` returns the file-sets sorted by path
- 2026-11-24, Phase 1, step 14, added in `accessionflow.api.collate`:
  - `resource_label_for(fileset, resource_field=()) -> tuple[str, bool]`
  - `acquisition_id_for(fileset, acquisition_id_field, resource_label) -> tuple[str, bool]`
  - `clash_hint_for(acquisition_derived, resource_derived) -> str | None`
  - `group_into_accessions(filesets, accession_uid_field, acquisition_id_field=(), resource_field=(), on_resource_clash="error", run_uid=None) -> list[Accession]`
- 2026-11-24, Phase 1, steps 3 and 13, added in `accessionflow.api.collate`:
  - `load_metadata_tables(metadata_tables=None) -> list[MetadataTable]`
  - `inject_fileset_tables(filesets, metadata_tables=None) -> list[FileSet]`
- 2026-11-24, Phase 1, step 11, added in `accessionflow.api.collate`:
  - `tag_fileset_types(filesets) -> list[FileSet]`
- 2026-11-24, Phase 1, step 10, added in `accessionflow.api.collate`:
  - `apply_path_metadata(filesets, path_metadata_regex=(), claimed=None) -> list[FileSet]`
- 2026-11-24, Phase 1, step 9, added in `accessionflow.api.collate`:
  - `drop_ignored_filesets(filesets, datatypes, ignore_datatypes=()) -> list[FileSet]`
- 2026-11-24, Phase 1, step 8, added in `accessionflow.api.collate`:
  - `disable_metadata_reading(filesets, dont_read_metadata=()) -> list[FileSet]`
- 2026-11-24, Phase 1, step 7:
  - added in `accessionflow.api.collate`:
    `classify_paths(fspaths, datatypes, ignore_datatypes=(), allow_unrecognised=()) -> list[FileSet]`
  - changed: `check_datatypes` raises `ValueError` if `datatypes` is empty
- 2026-11-24, Phase 1, step 6:
  - added in `accessionflow.api.collate`:
    `expand_claimed_paths(claimed, datatypes, recursion, recursive=False) -> list[Path]`,
    `CLAIMED_FILES_DIRNAME` and `ClaimedFiles.files_dir`
  - changed: `ClaimedFiles.original_of` covers directories, and raises `ValueError`
    for a path outside `files_dir`
- 2026-11-24, Phase 1, step 5:
  - added in `accessionflow.api.collate`:
    `claim_input_files(input_files, processing_dir, run_uid, source_roots=None) -> ClaimedFiles`,
    `ClaimedFiles` (with `claimed_roots`, `original_of` and `load`),
    `PROCESSING_NAME_DEFAULT` and `CLAIMED_MANIFEST`
  - added in `accessionflow.api.staging`: `check_run_uid(run_uid, purpose) -> None`
- 2026-11-24, Phase 1, steps 3, 4 and 18:
  - added in `accessionflow.api.collate`: `make_run_uid(input_files, now=None) -> str`
  - changed in `accessionflow.api.staging`: `prepare_build_dir(output_dir) -> Path` is
    now `prepare_build_dir(output_dir, run_uid) -> Path`, and returns the run's own
    directory, `output_dir / BUILD_NAME_DEFAULT / run_uid`
  - added in `accessionflow.api.staging`: `remove_build_dir(build_dir) -> list[Path]`
- 2026-11-24, Phase 1, step 2, added in `accessionflow.api.collate`:
  - `plan_recursion(datatypes, ignore_datatypes=(), recursive=False) -> RecursionPlan`
  - `RecursionPlan`, a `NamedTuple` of `(recurse_into_dirs, ignore_datatypes)`
- 2026-11-24, Phase 1, step 1, added in `accessionflow.api.collate`:
  - `check_datatypes(datatypes, ignore_datatypes=()) -> None`
- 2026-11-24, Phase 1, step 0, added in `accessionflow.api.collate`:
  - `list_input_files(input_paths, exclude_paths=()) -> list[Path]`

- 2026-11-24, Phase 0, added in `accessionflow.api.staging`:
  - `prepare_build_dir(output_dir) -> Path`
  - `move_into_place(saved_dir, output_dir, relpath) -> Path`
  - `for_each_accession(accessions, step, desc, raise_errors=False, name_of=...) -> list[str]`
  - `BUILD_NAME_DEFAULT`, moved from `accessionflow.api.collate_api`

### Staging layout

- 2026-11-26, Phase 1, removals: `from_paths`' run-UID form, `<6 hex>YYYYMMDDHHMMSS`,
  is no longer recognised in a directory name. Unlabelled accessions staged by an
  earlier version (`_.<uid>`) are still labelled by `label`, and the names it gives
  them parse back from their saved labels. But a labelled accession named
  `<labels>_<6 hex>YYYYMMDDHHMMSS` by an earlier version, whose metadata doesn't record
  its labels, no longer loads correctly: the run UID is taken as part of its last
  label. Drain the labelled accessions staged by an earlier version before upgrading.
  PR: pending.
- 2026-11-26, Phase 1, CLI: `collate folder` uses the new layout. In OUTPUT_DIR (each
  directory can be moved with its option):
  - `__processing__/<run_uid>/`: a run's claimed files, under `files/`, with its plan,
    `claimed.json`. Removed at the end of the run, or moved to one of the next two.
  - `__unprocessed__/<run_uid>/`: the files a run didn't deliver, with
    `unprocessed.json`.
  - `__error__/<run_uid>/`: the files of a run that failed, and
    `__error__/<labels>_<run_uid>/`: the run accessions of an accession that couldn't be
    combined, each with `error.json`.
  - `__runs__/<labels>_<run_uid>/`: the run accessions, until they are combined.
  - `<labels>_combined/`: the combined accessions, which later stages read.
  Accessions staged by an earlier version (`_.<uid>`) are still read by `label`, so
  nothing needs draining. PR: pending.

- 2026-11-26, Phase 1, Combine: a combined accession is named
  `<labels>_<primary_label>` (e.g. `P.S.V1_combined`). Its `__METADATA__.json` records
  its run accessions under `__combined_from__`. The run accessions of a group that
  couldn't be combined go to `<error_dir>/<labels>_<run_uid>/` with an `error.json`.
  Not used until `collate folder` runs the combiner, so nothing needs draining. PR:
  pending.
- 2026-11-25, Phase 1: labelled accession directories are named `<labels>_<run_uid>`
  instead of `<labels>.<run_uid>`, by every stage that saves one. Directories named the
  old way still load (both run-UID forms and the legacy `-` delimiter), so nothing
  needs draining. PR: pending.
- 2026-11-25, Phase 1: a run directory with files left after staging is moved to
  `<unprocessed_dir>/<run_uid>/` (its `claimed.json`, an `unprocessed.json` giving why
  each file was left, and the files under `files/`), and the run directory of a run
  that raised after the claim to `<error_dir>/<run_uid>/`, with an `error.json`. Not
  used until the folder `collate()` claims its input, so nothing needs draining. PR:
  pending.
- 2026-11-25, Phase 1: the run directories in `__build__/` are named
  `YYYYMMDDHHMMSS_<6 random hex characters>` instead of a path hash followed by the
  time. Staged accession names still use `Accession.from_paths`' run UID until it is
  removed, and both forms parse, so nothing needs draining. PR: pending.
- 2026-11-24, Phase 1, step 17: `stage_accession` writes a transient
  `<accession dir>.staged` marker in the run's build directory between moving an
  accession into place and deleting its claimed files. It is removed straight after,
  with the build directory, so nothing needs draining. PR: pending.
- 2026-11-24, Phase 1, step 4: collate builds each run in its own
  `<output_dir>/__build__/<run_uid>/` instead of directly in `__build__/`, and removes
  it at the end of the run. A directory left there holds what a failed save left
  behind. The staged accession directories don't change, so nothing needs to be
  drained before upgrading. PR: pending.
