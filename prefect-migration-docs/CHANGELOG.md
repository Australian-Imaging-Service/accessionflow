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

### Changed

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

- 2026-11-24, Phase 1, step 0, added in `accessionflow.api.collate`:
  - `list_input_files(input_paths, exclude_paths=()) -> list[Path]`

- 2026-11-24, Phase 0, added in `accessionflow.api.staging`:
  - `prepare_build_dir(output_dir) -> Path`
  - `move_into_place(saved_dir, output_dir, relpath) -> Path`
  - `for_each_accession(accessions, step, desc, raise_errors=False, name_of=...) -> list[str]`
  - `BUILD_NAME_DEFAULT`, moved from `accessionflow.api.collate_api`

### Staging layout

- No changes yet.
