# Migrating from xnat-ingest to AccessionFlow

This guide covers moving a deployment of **xnat-ingest** (up to v0.17.1) to
**AccessionFlow** v0.20.0. The tool was renamed in v0.18.0, and the commands were
reorganised in v0.19.0 and v0.20.0 so that where data comes from (*sources*) and where it
goes (*data stores*) are both plugins. The pipeline works the same way, but almost every
name an operator touches has changed: the package, the command, the Docker image, the
subcommands and the environment variables.

The changes you have to make are:

1. use the new package or image, and the `accessionflow` command (`acflow` is an alias)
2. rename the subcommands (see [Commands](#commands))
3. rename every `XINGEST_*` environment variable to `ACFLOW_*` (see
   [Environment variables](#environment-variables)). **The old ones are silently
   ignored**, so this is the step most likely to break a deployment without an error
4. check the two [behaviour changes](#behaviour-changes-to-check) that can affect a
   working pipeline

**Note** Data already staged by xnat-ingest can be read by AccessionFlow (see
[Data that is already staged](#data-that-is-already-staged)), so you don't need to drain
the pipeline first.


## Package, command and image

| | xnat-ingest | AccessionFlow |
|---|---|---|
| PyPI package | `xnat-ingest` | `accessionflow` |
| Command | `xnat-ingest` | `accessionflow` (or its alias, `acflow`) |
| Docker image | `ghcr.io/australian-imaging-service/xnat-ingest` | `ghcr.io/australian-imaging-service/accessionflow` |
| Image entrypoint | `xnat-ingest` | `accessionflow` |
| Python package | `xnat_ingest` | `accessionflow` |

Python 3.11 or later is still required. To deposit in a folder store on S3 or over SFTP,
install the `s3` or `ssh` extra, e.g. `pip install accessionflow[s3]`.


## Commands

Each stage that depends on where the data comes from or goes to now takes a subcommand
naming the source or data store, e.g. `collate folder` or `store xnat`.

| xnat-ingest | AccessionFlow | What changed |
|---|---|---|
| `group` | `collate folder` | renamed; `--session`/`--scan` renamed (see [Options](#options-that-changed)) |
| `group-orthanc` | `collate orthanc` | renamed; same arguments and options |
| `assign` | `label xnat` | renamed; same arguments and options |
| `associate` | `attach` | renamed; same arguments and options |
| `deidentify` | `deidentify` | `SPEC_DIR` renamed `RECIPE_DIR`; new options |
| `package` | `package` | unchanged |
| `upload` | `store xnat` | renamed; same arguments and options, plus `--no-uid-check` |
| `check-upload` | `check-store xnat` | renamed; same arguments and options, plus `--no-uid-check` |

There are no aliases for the old names: `accessionflow upload ...` fails with
`No such command 'upload'`.

AccessionFlow also has commands xnat-ingest didn't:

- `select-fields` — copies metadata into an accession's fields, which `store xnat` sets
  as custom variables on the XNAT session
- `label folder`, `store folder` and `check-store folder` — deposit accessions in a
  folder hierarchy on a local path, a mount, S3 or SFTP instead of XNAT

The terms have changed too: what xnat-ingest called a *session* is an **accession**,
and a *scan* is an **acquisition**. XNAT's own terms are unchanged, so `label xnat`
still has `--project`, `--subject`, `--session` and `--scan` options.


## Options that changed

Apart from the environment variables, only these options changed. Everything else
keeps its name and meaning.

### `group` → `collate folder`

| xnat-ingest | AccessionFlow | Environment variable |
|---|---|---|
| `--session <spec> <datatype>` | `--accession-uid <spec> <datatype>` | `XINGEST_SESSION` → `ACFLOW_ACCESSION_UID` |
| `--scan <spec> <datatype>` | `--acquisition-id <spec> <datatype>` | `XINGEST_SCAN` → `ACFLOW_ACQUISITION_ID` |

The defaults are unchanged (`StudyInstanceUID` and `SeriesNumber` for DICOM).
`--accession-uid` is the value files are grouped into accessions by; it isn't DICOM's
`AccessionNumber`, although that can be used for it.

The row frequencies of `--metadata-table` were renamed in the same way: `session` is now
`accession` and `scan` is now `acquisition`; `resource`, `fileset` and
`fileset[<mime-type>]` are unchanged. For example:

```diff
- --metadata-table table.csv session PatientID=PatientID
+ --metadata-table table.csv accession PatientID=PatientID
```

### `deidentify`

The third argument, the directory of de-identification recipes, was renamed from
`SPEC_DIR` to `RECIPE_DIR`. Its environment variable is now `ACFLOW_RECIPE_DIR`, but
`ACFLOW_SPEC_DIR` is still accepted. The layout of the directory is unchanged.

New options: `--metadata-allowlist` and `--hash-uid-key` (see
[Behaviour changes](#behaviour-changes-to-check)).


## Environment variables

Every environment variable's prefix changed from `XINGEST_` to `ACFLOW_`. AccessionFlow
doesn't read the old names at all, so a deployment that still sets `XINGEST_USER` runs
without credentials, and one that sets `XINGEST_PROJECT` labels from the default field,
with no warning in either case. Check every manifest, Compose file, Helm values file,
`ConfigMap` and `Secret`.

For almost every variable, replacing the prefix is all that is needed, e.g.
`XINGEST_HOST` → `ACFLOW_HOST`, `XINGEST_USER` → `ACFLOW_USER`, `XINGEST_PASS` →
`ACFLOW_PASS`, `XINGEST_PROJECT` → `ACFLOW_PROJECT`, `XINGEST_LOOP` → `ACFLOW_LOOP`,
`XINGEST_ORTHANC_URL` → `ACFLOW_ORTHANC_URL`.

**The exceptions are `XINGEST_SESSION` and `XINGEST_SCAN`, which depend on the
command.** xnat-ingest used the same names for two different things:

| Set for | xnat-ingest | AccessionFlow |
|---|---|---|
| `group` → `collate folder` | `XINGEST_SESSION` | `ACFLOW_ACCESSION_UID` |
| `group` → `collate folder` | `XINGEST_SCAN` | `ACFLOW_ACQUISITION_ID` |
| `assign` → `label xnat` | `XINGEST_SESSION` | `ACFLOW_SESSION` |
| `assign` → `label xnat` | `XINGEST_SCAN` | `ACFLOW_SCAN` |

A blanket `XINGEST_` → `ACFLOW_` replacement gets the `assign`/`label xnat` ones right
and the `group`/`collate folder` ones wrong. Rename those two by hand in whatever
configures the collate stage. If several stages share one environment (e.g. a single
`env_file`), the old names meant `group` and `assign` read each other's settings;
AccessionFlow's names no longer collide, so give each stage the variables it needs.

New variables that xnat-ingest didn't have: `ACFLOW_S3_MAX_WORKERS` (for `store xnat`
and `check-store xnat`), `ACFLOW_NO_UID_CHECK`, `ACFLOW_HASH_UID_KEY` and
`ACFLOW_METADATA_ALLOWLIST`. The documentation lists every variable and the option it
sets under *Reference → Environment variables*.

`AIS_LOG_FORMAT=json` still selects JSON logs, but the logger is now named
`accessionflow` rather than `xnat-ingest`, so update log routing or filters that select
it by name.


## Behaviour changes to check

Two changes since xnat-ingest can affect a pipeline that otherwise migrates cleanly.

### `deidentify` keeps only the accession's UID in its metadata

The metadata side-cars that `deidentify` writes now keep only `__uid__` (and the keys
identifying the accession's labels and data store). Every other field is dropped; the
input's metadata is unchanged. **A later stage that reads a metadata field from the
de-identified copy fails**: most commonly `store xnat --date StudyDate`, which reports
that it couldn't set the session's date. Keep the fields later stages need with
`--metadata-allowlist`:

```console
$ accessionflow deidentify /staging/labelled /staging/deidentified /etc/deid-recipes \
    --metadata-allowlist StudyDate
```

The values kept are the de-identified ones, e.g. a `StudyDate` that the recipe has
shifted.

### `store xnat` checks a session's identity before reusing it

When an XNAT session with the incoming label already exists, `store xnat` (and
`check-store xnat`) now checks that it belongs to the expected subject, and that its
`xnat_ingest_uid` custom field matches the accession's UID, before adding to it. A
mismatch refuses the upload and keeps the staged copy. New sessions get the field when
they are created. A session created by xnat-ingest has no field: after its subject
matches, it is adopted (the field is written, with a warning) rather than refused.

If you start hashing UIDs with `deidentify --hash-uid-key`, sessions already on XNAT
hold the unhashed UID and will be refused. Pass `--no-uid-check` to `store xnat` and
`check-store xnat` while moving over. The documentation's XNAT page describes this under
*Session identity on reuse*.


## Data that is already staged

AccessionFlow reads directories written by xnat-ingest, so accessions already partway
through the pipeline carry on after the upgrade:

- grouped (collated) accessions are still in `_.<uid>` directories
- assigned (labelled) accessions in `<project>.<subject>.<session>` directories, which
  don't record the names of their label levels, are read as XNAT's project, subject and
  session
- resources with the older `MANIFEST.json` manifest name are still read

Upgrade all the stages of a pipeline at the same time, rather than running xnat-ingest
and AccessionFlow stages on the same directories.


## Example: a Docker Compose deployment

```diff
 services:
   collate:
-    image: ghcr.io/australian-imaging-service/xnat-ingest
-    command: group /input /staging/grouped --loop 300
+    image: ghcr.io/australian-imaging-service/accessionflow
+    command: collate folder /input /staging/grouped --loop 300
     environment:
-      XINGEST_SESSION: "StudyInstanceUID medimage/dicom-collection"
+      ACFLOW_ACCESSION_UID: "StudyInstanceUID medimage/dicom-collection"
     volumes:
       - /data/incoming:/input
       - staging:/staging
     restart: unless-stopped

   label:
-    image: ghcr.io/australian-imaging-service/xnat-ingest
-    command: assign /staging/grouped /staging/assigned --loop 300
+    image: ghcr.io/australian-imaging-service/accessionflow
+    command: label xnat /staging/grouped /staging/assigned --loop 300
     environment:
-      XINGEST_PROJECT: StudyComments
-      XINGEST_SESSION: AccessionNumber
+      ACFLOW_PROJECT: StudyComments
+      ACFLOW_SESSION: AccessionNumber
     volumes:
       - staging:/staging
     restart: unless-stopped

   upload:
-    image: ghcr.io/australian-imaging-service/xnat-ingest
-    command: upload /staging/assigned xnat.example.org --loop 300
+    image: ghcr.io/australian-imaging-service/accessionflow
+    command: store xnat /staging/assigned xnat.example.org --loop 300
     environment:
-      XINGEST_USER: my-upload-user
-      XINGEST_PASS: my-upload-password
+      ACFLOW_USER: my-upload-user
+      ACFLOW_PASS: my-upload-password
     volumes:
       - staging:/staging
     restart: unless-stopped
```

The staging directories can keep their names (`grouped`, `assigned`); only the commands
and variables need to change. A Kubernetes deployment changes the same way: the image,
each container's `args`, and the `ACFLOW_*` keys in its `ConfigMap`s and `Secret`s.
`check-upload` CronJobs become `check-store xnat`.


## Python API

Scripts that import xnat-ingest need these changes.

| xnat-ingest | AccessionFlow |
|---|---|
| `xnat_ingest.api.group(..., session=, scan=)` | `accessionflow.sources.folder.api.collate(..., accession_uid=, acquisition_id=)` |
| `xnat_ingest.api.group_orthanc(...)` | `accessionflow.sources.orthanc.api.collate(...)` |
| `xnat_ingest.api.assign(...)` | `accessionflow.api.label(...)`, with different parameters (see below) |
| `xnat_ingest.api.associate(...)` | `accessionflow.api.attach(...)` |
| `xnat_ingest.api.deidentify(..., spec_dir=)` | `accessionflow.api.deidentify(..., recipe_dir=)` |
| `xnat_ingest.api.package(...)` | `accessionflow.api.package(...)` |
| `xnat_ingest.api.upload(...)` | `accessionflow.stores.xnat.api.store(...)` |
| `xnat_ingest.api.check_upload(...)` | `accessionflow.stores.xnat.api.check_store(...)` |

`assign`'s parameters for each XNAT level became a mapping, since a data store can have
any levels:

```diff
- assign(input_dir, output_dir,
-        project_field="StudyComments", subject_field="PatientID",
-        session_field="AccessionNumber", scan_field="SeriesDescription",
-        project_id="MYPROJECT")
+ label(input_dir, output_dir,
+       label_fields={"project": "StudyComments", "subject": "PatientID",
+                     "session": "AccessionNumber"},
+       acquisition_field="SeriesDescription",
+       constant_labels={"project": "MYPROJECT"},
+       store_type="xnat")
```

The model classes and their attributes were renamed:

| xnat-ingest | AccessionFlow |
|---|---|
| `xnat_ingest.model.session.ImagingSession` | `accessionflow.model.accession.Accession` |
| `xnat_ingest.model.scan.ImagingScan` | `accessionflow.model.acquisition.Acquisition` |
| `xnat_ingest.model.resource.ImagingResource` | `accessionflow.model.resource.Resource` |
| `ImagingSession.project_id` / `.subject_id` / `.session_id` | `Accession.labels`, a dict, e.g. `labels["project"]` |
| `ImagingSession.scans` | `Accession.acquisitions` |
| `ImagingScan.session` | `Acquisition.accession` |
| `ImagingResource.scan` | `Resource.acquisition` |
| `ImagingSession.from_paths(..., session_field=, scan_field=)` | `Accession.from_paths(..., accession_uid_field=, acquisition_id_field=)` |

`Accession.load` takes a `pathlib.Path`, not a string.


## Checklist

- [ ] Image changed to `ghcr.io/australian-imaging-service/accessionflow`, or
      `accessionflow` installed in place of `xnat-ingest`
- [ ] Every command updated: `group` → `collate folder`, `group-orthanc` →
      `collate orthanc`, `assign` → `label xnat`, `associate` → `attach`, `upload` →
      `store xnat`, `check-upload` → `check-store xnat`
- [ ] `collate folder`'s `--session`/`--scan` changed to `--accession-uid`/`--acquisition-id`,
      and any `--metadata-table` row frequency of `session`/`scan` changed to
      `accession`/`acquisition`
- [ ] No `XINGEST_` variables left anywhere: Compose files, Helm values, `ConfigMap`s,
      `Secret`s, `.env` files, scripts
- [ ] The collate stage's `XINGEST_SESSION`/`XINGEST_SCAN` renamed to
      `ACFLOW_ACCESSION_UID`/`ACFLOW_ACQUISITION_ID`, not `ACFLOW_SESSION`/`ACFLOW_SCAN`
- [ ] If `store xnat --date` (or any later stage) reads a metadata field after
      `deidentify`, that field listed in `deidentify --metadata-allowlist`
- [ ] If adopting `deidentify --hash-uid-key`, `--no-uid-check` set on `store xnat` and
      `check-store xnat` for the changeover
- [ ] Alerting and log queries that match command names (e.g. `upload`, `group`) or the
      `xnat-ingest` logger updated for the new names (the logger is now `accessionflow`)
- [ ] Python scripts updated to the new modules, functions and attribute names
