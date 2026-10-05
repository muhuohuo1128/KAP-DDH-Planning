# GitHub and Zenodo release guide

This guide provides consistent project metadata and release text for version 1.0.0 of the KAP-DDH preoperative planning module.

## Project metadata

| Field | Text |
|---|---|
| Repository name | `KAP-DDH-Planning` |
| Project title | KAP-DDH: Preoperative Acetabular Reconstruction Planning |
| Short description | Source code and graphical user interface for the preoperative planning module of KAP-DDH. |
| Version | `1.0.0` |
| Release tag | `v1.0.0` |
| Release title | KAP-DDH Planning v1.0.0 |
| License | GPL-3.0-only |

Suggested topics: `preoperative-planning`, `acetabular-reconstruction`, `developmental-dysplasia-of-the-hip`, `orthopaedics`, `medical-imaging`.

## Release description

The following text can be used for the GitHub release and Zenodo description:

> This repository provides the source code and graphical user interface for the preoperative planning module of KAP-DDH. Version 1.0.0 provides a geometric planning engine, an English desktop interface, portable configuration, input/output documentation and a synthetic example with computed reference outputs.
>
> The released example runs in fixed-constraint mode. It demonstrates candidate generation, scoring and visualization within the planning module. The documentation also describes the existing interface for applying study-specific constraints.
>
> See README.md for release scope and availability, docs/VALIDATION.md for the software checks, and CHANGELOG.md for the version history. The source is released under GPL-3.0-only; third-party dependencies retain their own licenses.

## Repository and archive layout

Upload the contents of `KAP-DDH-Planning/` so that `README.md`, `LICENSE`, `VERSION` and the source files sit at the repository root, with `docs/`, `examples/` and `scripts/` alongside them. Preserve those relative paths when creating a Zenodo archive.

Keep the generated `SHA256SUMS.txt` with the released file set; it covers all repository files except itself.

Archive the exact commit selected for the release. If a release has already been archived, follow the archive's versioning process so that each deposited version remains identifiable. Use the DOI actually assigned to the published record. Enter the actual software authors and contributors in the archive metadata, and link the associated manuscript when its publication details are available.

## Citation and availability text

Use the repository URL, archived software version and assigned DOI consistently in citations and the manuscript's Code availability statement. Describe the software as the **preoperative planning module and graphical user interface**. The [README scope and availability section](../README.md#scope-and-availability) supplies the corresponding resource-management statement.
