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

The steps fall into eight groups. In the table, `#` is the step's number in the run
order; the steps in a group marked `–` are helpers that the numbered step uses,
or the record a step returns. Each group's table gives each step's signature, its
module in `accessionflow/api/collate/` (unless another path is shown), where it was
taken from, and what it does.

| Group | Steps |
| --- | --- |
| List input files | 0 `list_input_files` |
| Check parameters | 1 `check_datatypes`, 2 `plan_recursion`, 3 `load_metadata_tables` |
| Set up the run directory | 4 `make_run_uid`, 5 `prepare_build_dir`, 6 `claim_input_files` |
| Determine the file-sets | 7 `expand_claimed_paths`, 8 `classify_paths`, 10 `drop_ignored_filesets` |
| Apply metadata | 9 `disable_metadata_reading`, 11 `apply_path_metadata`, 12 `tag_fileset_types`, 13 `inject_fileset_tables` |
| Form accessions | 14 `group_into_accessions`, 15 `inject_accession_tables` |
| Stage accessions | 16 `warn_if_hardlinks_unavailable`, 17 `stage_accession` |
| Clean up | 18 `finish_claim`, 19 `remove_build_dir` |

Steps 1–16, 18 and 19 run once per collation; step 17 runs once per accession. Within
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
| 10 | `drop_ignored_filesets(filesets, datatypes, ignore_datatypes=()) -> list[FileSet]` | `classify.py` | L1009-1019 | Returns a new list without the file-sets of the ignored datatypes (`RecursionPlan.ignore_datatypes`), matched with `isinstance`. A wanted datatype wins, so a wanted `DirectoryOf[Json]` isn't dropped because `Directory` is ignored. The dropped file-sets' files stay in the processing area, for `finish_claim` to report |

##### Apply metadata

Add metadata to the file-sets from their paths, their types and the metadata tables.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 9 | `disable_metadata_reading(filesets, dont_read_metadata=()) -> list[FileSet]` | `classify.py` | L1000-1007 | Sets the public `fileset.metadata.read_disabled` (in `fileformats` 0.22.8, the minimum version) on each file-set that is an instance of one of the datatypes, so a subclass matches too. Changes the file-sets in place and returns the same ones. `from_paths` now uses the public setter too, which resolves its TODO |
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

##### Stage accessions

Save each accession and move it into the output directory. `stage_accession` is the per-accession unit.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 16 | `warn_if_hardlinks_unavailable(accessions, build_dir, copy_mode, conversion_map=None) -> list[Path]` | `save.py` | L118-169 | Moved here from `api/collate_api.py`, which imports it. Same checks and warning, now also returning one file of each resource that can't be hard-linked. The output directory it names is worked out from the build directory (`<output_dir>/__build__/<run_uid>`), or is the build directory itself if it isn't in a `__build__` directory. Once collate claims its input, it compares the processing area, not the source, with the build directory, so it only warns if the processing area is put elsewhere |
| 17 | `stage_accession(accession, build_dir, output_dir, claimed, copy_mode=hardlink_or_copy, collation_map=None, conversion_map=None) -> Path` | `save.py` | L83-106 | **The per-accession unit**: `save_to_build_dir`, then `move_into_place`, then `remove_claimed_files`. Raises on failure; a failure before the move leaves the output untouched and the files in the processing area. Once the move succeeds it writes a marker, `build_dir/<staging_dirname>.staged` (`STAGED_MARKER_SUFFIX`), so a retry after a failed delete skips the save and the move (which would clash with the acquisitions already in place) and only deletes; a crash in the instant between the move and the marker still makes the retry fail on the move, without losing data |
| – | `save_to_build_dir(accession, build_dir, copy_mode=hardlink_or_copy, collation_map=None, conversion_map=None) -> Path` | `save.py` | L87-97 | Removes the accession's scratch directory (`build_dir/<staging_dirname>`) left by an earlier attempt, then `Accession.save`s it there (principle 9). Doesn't touch the run's shared `build_dir/__build__` |
| – | `remove_claimed_files(accession, claimed) -> list[Path]` | `save.py` | L100-106 | Deletes the accession's files from the processing area (a directory datatype's directory with `rmtree`), skipping any already gone, so it can be retried. Refuses, before deleting anything, if any file isn't in `claimed.files_dir`, so it never deletes from a live input. Always run, replacing the optional `unlink_source`. Empty directories are left for `finish_claim` |

The wait-period check (L71-81) is removed, with `Accession.last_modified`
(`model/accession.py:2026`), which nothing else uses.

##### Clean up

Remove what the run leaves in the processing area and the build directory.

| # | Step | Module | From | Notes |
| --- | --- | --- | --- | --- |
| 18 | `finish_claim(claimed) -> list[Path]` | `claim.py` | new | After staging: deletes any hidden `.<name>.claiming` file left by a copy across file systems that was stopped part way (its source is still in the input), prunes the empty directories (`prune_empty_dirs`, shared with `remove_build_dir`), and removes the whole run directory, plan included, if no files are left. Otherwise it keeps the run directory with its plan, so `ClaimedFiles.load` still works, and returns, and logs once, the files left: ones `--allow-unrecognised` let through, file-sets of an `--ignore-datatype`, and the files of accessions that failed to stage. Returns `[]` if the run directory doesn't exist |
| 19 | `remove_build_dir(build_dir) -> list[Path]` | `api/staging.py` | new | Removes empty subdirectories first (`prune_empty_dirs`), including the empty `__build__` that `Accession.save` leaves, then the run's build directory if no files are left. Otherwise keeps it, logs a warning and returns what is left. `__build__` itself stays, as other runs share it. |

#### Dated entries

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
