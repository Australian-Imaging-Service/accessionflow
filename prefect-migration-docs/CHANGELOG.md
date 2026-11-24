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
  for writing accessions into a staging directory, `prepare_build_dir`,
  `move_into_place` and `for_each_accession`, with `BUILD_NAME_DEFAULT` moved here.
  Tests in `accessionflow/api/tests/test_staging.py`. No stage uses the new helpers
  yet; each starts in its own phase. CLI unchanged. PR: pending.
- 2026-11-24, Phase 0, `accessionflow/cli/runner.py`: the helpers the CLI commands
  repeat, `run_on_interval` and `log_stage_summary`, with `check_loop_options` moved
  here. Tests in `accessionflow/cli/tests/test_runner.py`. No command uses
  `run_on_interval` or `log_stage_summary` yet; collate starts in Phase 1. CLI
  unchanged. PR: pending.

### Changed

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

- 2026-11-24, Phase 0, added in `accessionflow.api.staging`:
  - `prepare_build_dir(output_dir) -> Path`
  - `move_into_place(saved_dir, output_dir, relpath) -> Path`
  - `for_each_accession(accessions, step, desc, raise_errors=False, name_of=...) -> list[str]`
  - `BUILD_NAME_DEFAULT`, moved from `accessionflow.api.collate_api`

### Staging layout

- No changes yet.
