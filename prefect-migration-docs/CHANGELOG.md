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

### Step API

- No changes yet.

### Staging layout

- No changes yet.
