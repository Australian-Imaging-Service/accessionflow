
<p>
  <br>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Australian-Imaging-Service/accessionflow/main/docs/logo_dev/accessionflow-logo-dark.png">
    <img src="https://raw.githubusercontent.com/Australian-Imaging-Service/accessionflow/main/docs/logo_dev/accessionflow-logo.png" alt="AccessionFlow" width="520">
  </picture>
  <br>
  <br>
</p>

[![CI/CD](https://github.com/Australian-Imaging-Service/accessionflow/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Australian-Imaging-Service/accessionflow/actions/workflows/ci-cd.yml)
[![codecov](https://codecov.io/gh/Australian-Imaging-Service/accessionflow/graph/badge.svg?token=V860ZYIKQ3)](https://codecov.io/gh/Australian-Imaging-Service/accessionflow)
[![PyPI](https://img.shields.io/pypi/v/accessionflow.svg)](https://pypi.python.org/pypi/accessionflow/)
[![Documentation Status](https://img.shields.io/badge/docs-latest-brightgreen.svg?style=flat)](https://australian-imaging-service.github.io/accessionflow/)


Accessioning is the process of formally receiving material from a source and registering
it in a managed collection. AccessionFlow is a
collection of tools to accession data: collate, label, de-identify and store them
in a data store. Support for various file types is provided through
the [FileFormats](https://python-fileformats.github.io/fileformats/) package and its extensions
(e.g. [FileFormats MedImage](https://python-fileformats.github.io/fileformats-medimage/), [FileFormats Siemens](https://python-fileformats.github.io/fileformats-vendor-siemens/),...).

```mermaid
flowchart LR
    Folder(["folder"]) --> Collate["collate (source)"]
    Orthanc(["Orthanc"]) --> Collate
    Collate --> Label["label (store)"]
    Label --> Deidentify["deidentify (optional)"]
    Deidentify --> Store["store (store)"]
    Store --> XNAT[("XNAT")]
    Store --> FolderStore[("folder store\n(local, S3, SFTP)")]
    Store -.-> CheckStore["check-store (store)"]

    Extra(["files without\nsorting metadata"]) -.-> Attach["attach (optional)"]
    Collate -.-> Attach
    Attach -.-> Label
```

Where the files come from and where they go are both plugins: sources provide the
`collate` subcommands (`collate folder`, `collate orthanc`), and data stores provide the
`label`, `store` and `check-store` subcommands (e.g. `label xnat`, `store folder`).


## Installation

A Docker image containing the toolkit can be pulled from the GitHub Container Registry
and entrypoint of the image is the accessionflow CLI so commands can be run by the form

```
docker run ghcr.io/australian-imaging-service/accessionflow:latest <command-name> <arg1> <arg2> ... --opt1 <opt1> ...
```

Alternatively, AccessionFlow can be installed as a Python package from PyPI with `pip`:

```
$ python3 -m pip install accessionflow
```


## Running

AccessionFlow has a public API and a command-line interface (CLI), with subcommands to collate,
attach, label, de-identify and store accessions in a data store — either as a one-off run or
as a continuously-running service (e.g. via Docker Compose or Kubernetes). For example:

```
$ accessionflow collate folder /data/incoming /data/staging/collated
$ accessionflow label folder /data/staging/collated /data/staging/labelled --level subject PatientID
$ accessionflow store folder /data/staging/labelled s3://my-bucket/archive
```

See the [full documentation](https://australian-imaging-service.github.io/accessionflow/) for a hands-on
quick start, a guide to each source, stage and data store, and the complete CLI/API reference.
