# Integration with study-specific constraints

The planning engine uses the same constraint structure for its fixed-constraint workflow and its existing adapter for study-specific constraints. This guide describes how those constraints are passed into planning and how the resulting mode is recorded.

## Constraint structure

For each Crowe group, `FIXED_CONSTRAINT_IDEALS[level]` in `config.py` defines six fields:

- `circle_diameter`
- `distance_to_line1`
- `distance_to_line2`
- `distance_to_line3`
- `distance_to_line4`
- `distance_to_line8`

Each field contains `min`, `max`, `ideal` and `weight`. These values populate the engine's active `CONSTRAINT_IDEALS` mapping. Preserve the implementation's pixel-coordinate convention when preparing constraints; physical-unit output conversion uses the case's calibrated mm/pixel value. See [inputs and outputs](INPUTS.md).

With `PERSONALIZED_CONSTRAINTS_ENABLE=False`, the engine uses the configured fixed constraints. This is the mode selected by the released synthetic example.

## Existing adapter contract

With `PERSONALIZED_CONSTRAINTS_ENABLE=True`, the planning-side adapter obtains ranked case identifiers from a compatible constraint-source environment and reads the corresponding parameter values from a workbook. Enabling this mode requires that environment to be configured and available at runtime.

The existing configuration names are retained for compatibility:

| Setting or interface | Role |
|---|---|
| `KB_GNN_DIR` | Module directory providing `search_vis`; optional `kb_config` supplies compatible column settings |
| `search_vis.BucketIndex(...)` | Initializes the adapter's search object using the configured input and cache options |
| `BucketIndex.search(query_txt_path, top_k=..., with_gradient=False, with_occlusion=False)` | Returns ordered `results` entries with `stem` identifiers; dynamic selection may also return `topk.return_k` |
| `KB_XLSX_PATH` | Parameter workbook used to look up values for the returned identifiers |
| `KB_STEM_COL`, `KB_CROWE_COL`, `KB_CONSTRAINT_COLS` | Case, Crowe and constraint-column mapping; workbook column positions are 1-based |
| Other `KB_*` path and search settings in `config.py` | Connection and search options for the configured constraint source |

This interface is a Python adapter and workbook lookup, rather than a standalone constraints-file import command. Query landmark ordering must follow the same input protocol; the configured adapter expects nine points by default.

## Applying the constraints

For each of the six fields, the adapter:

1. Collects parameter values from the configured workbook columns for the selected identifiers.
2. Uses their minimum and maximum as the candidate range.
3. Uses the top-ranked identifier's value as the ideal.
4. Retains the field's configured fixed weight.

A field is updated when its range satisfies `min < max` and its top-ranked value is available. Otherwise, the field retains its complete fixed-constraint entry. If retrieval fails for a case, planning continues with that case's fixed constraints.

## Execution status

The launcher checks adapter initialization before starting a requested study-specific run and reports a configuration failure if initialization cannot complete. A later per-case retrieval failure follows the fixed-constraint fallback described above.

CLI output records `kb_constraint_application.requested` and `kb_constraint_application.application_succeeded`. A successful application reports completion of the bridge; individual fields may still retain their fixed entries. The GUI uses the same underlying fallback behavior and reports through its existing logs; the CLI status payload belongs to the CLI output schema.

The fixed-constraint example can be run directly with [the documented example commands](../examples/README.md), without configuring this adapter.
