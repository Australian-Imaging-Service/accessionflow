# Testing notes

Notes on running the test suite during the Prefect migration, gathered while
implementing Phase 0 (2026-11-24). They record the state of one development machine
(WSL2, the repository's `.venv` on Python 3.14), so check them against your own set-up.

## Running the tests

- The environment is managed with uv. After pulling changes to `pyproject.toml`, run
  `uv sync --extra test` so that `.venv` matches it (see
  [A stale environment](#a-stale-environment)). `uv sync` created a `uv.lock`, which
  isn't committed yet.
- There is no `python` on the PATH, and the system `python3` doesn't have
  `accessionflow` installed. Use the virtual environment: `.venv/bin/python -m pytest ...`.
- `pre-commit` isn't on the PATH. Run the hooks with
  `uvx pre-commit run --files <files>`. The hooks are trailing-whitespace,
  end-of-file-fixer, check-yaml, check-added-large-files, ruff check (with `--fix`), ruff
  format and codespell.
- mypy isn't installed in `.venv`: `pyproject.toml` configures it under `[tool.mypy]`,
  but no extra installs it.
- `-p no:cacheprovider` keeps `.pytest_cache` out of the working tree.

## Baseline

The whole suite passes after Phase 0 (2026-11-24), with `.venv` synced:

| Tests | Result | Time |
| --- | --- | --- |
| `accessionflow`, without `accessionflow/stores/xnat` | 619 passed | 14 min 6 s |
| `accessionflow/stores/xnat` | 297 passed | 3.7 s |
| Total | 916 passed, no failures, no reruns | about 14 min |

## What takes the time

- **A live XNAT server.** A session-scoped fixture (`conftest.py:97-99`) starts XNAT in
  Docker with `xnat4tests.start_xnat()`, in a container named `xnat4tests` (Tomcat and
  Postgres). The first run pays the start-up time. Later runs reuse the container while
  it is up, so leave it running between runs and stop it with
  `docker stop xnat4tests` when you're done.
- **`test_stage_and_upload`** (`cli/tests/test_cli.py:297`): 157 s. A full end-to-end
  run that generates 2 sessions of 4 Siemens series (about 1 GB of data), then collates,
  labels, deidentifies and uploads them to the XNAT container, and checks the upload.
  It is marked `flaky(reruns=3)`, because the test XNAT sometimes answers with HTTP 500,
  so a bad run can take up to four times as long.
- **Tests that generate DICOM images**:

  | Test | Time |
  | --- | --- |
  | `cli/tests/test_cli.py::test_deidentify_cli_dicom` | 72 s |
  | `api/tests/test_dicom_churn_probe.py`, 2 tests | 41 s each |
  | `model/tests/test_accession.py::test_session_save_roundtrip` | 33 s |
  | `cli/tests/test_cli.py::test_deidentify_cli_dicom_encrypted_reid` | 23 s |
  | `api/tests/test_label.py`, the end-to-end tests | 12–23 s each |
  | other deidentify, label and accession tests, including fixture set-up | 10–18 s each |

- The XNAT store tests (`accessionflow/stores/xnat`) are mocked and don't use the live
  server, so they take seconds.

For a quick check while working, skip the slowest tests and run the full suite at the
end of each phase:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider \
    -k "not stage_and_upload and not deidentify_cli_dicom and not churn_probe" accessionflow
```

`--durations=20` lists the slowest tests of a run. The full suite takes longer than a
10-minute command timeout, so run it in the background (e.g. with `run_in_background` in
an agent session), with `-v` output to a log to see its progress.

## `/tmp` fills up

`/tmp` is a 3.7 GB tmpfs. pytest keeps the temporary directories of recent runs in
`/tmp/pytest-of-<user>`, and the DICOM fixtures are large: a full run writes about 1 GB
(`test_stage_and_upload` alone writes 990 MB). On 2026-11-24, `/tmp` filled up
completely, and tests that write files failed with
`OSError: [Errno 28] No space left on device`, often from inside pydicom, which looks
like a real failure at first sight. After old runs were cleared, `/tmp` was 53 % full.

Either clear `/tmp/pytest-of-<user>`, or put pytest's and Python's temporary files on
the main disk:

```bash
T=$PWD/.tmp-tests
mkdir -p $T/tmp
TMPDIR=$T/tmp .venv/bin/python -m pytest -q -p no:cacheprovider --basetemp=$T/pt <tests>
rm -rf $T
```

`--basetemp` moves pytest's `tmp_path` directories, and `TMPDIR` moves the
`tempfile` directories that the code under test creates.

## A stale environment

Before `uv sync`, `.venv` held the project under its old name (`xnat-ingest` 0.16.1,
installed 2026-10-06), `fileformats` 0.19.4, `fileformats-extras` 0.18.3 and
`fileformats-medimage` 0.15.2, and no `fileformats-vendor-xnat`. `pyproject.toml`
requires `fileformats >=0.22.8`, `fileformats-extras >=0.22.1`,
`fileformats-medimage >=0.15.5` and `fileformats-vendor-xnat >=0.3.1`. That gave 23
failures and 2 test modules that couldn't be collected, all of which looked unrelated
to the change being tested:

- `ModuleNotFoundError: No module named 'fileformats.vendor.xnat'`: the `label xnat` and
  `store xnat` cases of `cli/tests/test_loop_interval.py`, and collection of
  `cli/tests/test_cli.py` and `cli/tests/test_require_manifest_default.py`
- `TypeError: Arguments differ between the signature of the extras hook method
  FileSet.load and the implementing function load_text_file`: `api/tests/test_package.py`
  and `cli/tests/test_store_commands.py`
- `FormatRecognitionError` raised where `FormatMismatchError` is expected: 3 tests in
  `api/tests/test_collate.py`

If you see these, compare the installed versions with `pyproject.toml`:

```bash
uv pip list --python .venv/bin/python | grep -E "^(accessionflow|xnat-ingest|fileformats)"
```

Then run `uv sync --extra test`. After that, every one of these tests passed.

To check whether a failure is caused by your change, stash it (`git stash -u`), run the
same tests, and `git stash pop`.

## Tests that guard the migration

- **Collate**: `api/tests/test_collate.py`, `model/tests/test_accession.py` (its
  `Accession.from_paths` tests become the regression net for Phase 1),
  `sources/folder/tests/test_collate_api.py`, `sources/orthanc/tests/`.
- **CLI contract**: `cli/tests/test_collate_commands.py`, `cli/tests/test_cli.py`, and
  `cli/tests/test_loop_interval.py`, which runs each looping command with the API, `time`,
  `datetime` and `logger` of the command's module patched. When a command moves to
  `accessionflow.cli.runner.run_on_interval`, the clock and sleep are looked up there
  instead, so the test's patching needs to follow. `run_on_interval` keeps the timings
  as the first arguments of its log message, as the test checks.
- **Internal paths patched by tests**: `cli/tests/test_cli.py:746` patches
  `accessionflow.api.collate_api.time`, and `sources/orthanc/tests/test_orthanc_cli.py`
  patches `accessionflow.sources.orthanc.api.collate_api.stage_studies`. Both need
  updating when that code moves (Phases 1 and 3).
- **Shared helpers (Phase 0)**: `api/tests/test_staging.py` and
  `cli/tests/test_runner.py`.
- **Collate steps (Phase 1)**: `api/tests/collate/`, one test module per step module,
  using small trees of plain files in `tmp_path`, so they run in about a second.
- `real-tests/` scripts drive collate through the CLI, so Python API changes don't
  affect them.

## Linting Markdown

The editor's markdownlint reports MD022, MD031 and MD032 (blank lines around headings,
fences and lists), MD036 (bold text used as a heading), MD040 (a code fence without a
language) and MD060 (table pipe style; use `| --- |` delimiter rows). It doesn't check
line length. Running `markdownlint-cli2` through `npx` was blocked in the agent session,
because it downloads a package, so check the editor's Problems panel instead.
