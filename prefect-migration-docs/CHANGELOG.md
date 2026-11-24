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

### Changed

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

- 2026-11-24, Phase 0: `accessionflow.api.collate_api.BUILD_NAME_DEFAULT`. Use
  `accessionflow.api.staging.BUILD_NAME_DEFAULT`, or `accessionflow.api.BUILD_NAME_DEFAULT`,
  which is still exported. PR: pending.
- 2026-11-24, Phase 0: `accessionflow.cli.collate_cli.check_loop_options`. Use
  `accessionflow.cli.runner.check_loop_options`. PR: pending.

### Step API

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

- 2026-11-24, Phase 1, step 4: collate builds each run in its own
  `<output_dir>/__build__/<run_uid>/` instead of directly in `__build__/`, and removes
  it at the end of the run. A directory left there holds what a failed save left
  behind. The staged accession directories don't change, so nothing needs to be
  drained before upgrading. PR: pending.
