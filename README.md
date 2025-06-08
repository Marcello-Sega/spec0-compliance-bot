# SPEC-0 Compliance Bot

This GitHub Action automatically checks your Python project’s dependencies for compliance with the [SPEC 0 — Minimum Supported Dependencies](https://scientific-python.org/specs/spec-0000/) specification. If any dependencies are out of date, it opens a pull request suggesting a patch that upgrades them to the **oldest supported version within the 2-year support window**.

## What It Does

- Scans your `requirements.txt`, `pyproject.toml`, and `setup.py`
- Identifies outdated dependencies
- Updates them to the **minimum version required by SPEC-0**
- Commits the changes in a new branch
- Opens a pull request back to the triggering branch

## How to Use It

To enable SPEC-0 compliance checks in your repository, create a new workflow file in `.github/workflows/spec-0.yml` with the following content:

```yaml
name: SPEC-0 Compliance Check

on:
  push:
    paths:
      - '**/requirements.txt'
      - '**/setup.py'
      - '**/pyproject.toml'
  pull_request:

jobs:
  spec0:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: Marcello-Sega/spec0-compliance-bot@v0.2
        with:
          path: .
          github_token: "${{ secrets.GITHUB_TOKEN }}"
          trigger_branch: "${{ github.head_ref || github.ref_name }}"
```

## Badge

You can add a badge to your repository’s README.md to show the live status of the SPEC-0 check:

`![SPEC-0](https://img.shields.io/github/actions/workflow/status/<User>/<repository>/spec-0.yml?label=SPEC-0&logo=github)`

## ⚠️ Warning: Experimental Code

This action is **experimental and untested** on projects with non-standard or complex dependency file formats.

It may fail or behave unexpectedly when:
 - Dependency entries deviate from standard `pip` formats- Files are highly customized (e.g., dynamic generation of `install_requires`)
 - The `pyproject.toml` or `setup.py` contain syntax or
 -  structure not anticipated by the parser

Use with care, and review pull requests before merging.
