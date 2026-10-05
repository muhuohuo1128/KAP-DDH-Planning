# Input and output formats

## Matched input files

Use the same case identifier (filename stem) in every folder and in the scale table.

| Configuration key | File | Required content |
|---|---|---|
| `FOLDER_A` | `{case}.png` | Source image |
| `FOLDER_B` | `{case}_kjwy.png` | Candidate acetabular rim mask, curve 1 |
| `FOLDER_C4` | `{case}_bks.png` | Exclusion curve 2 mask |
| `FOLDER_C3` | `{case}_bkx.png` | Optional exclusion curve 3 mask; absence is reported by the wrapper |
| `FOLDER_C` | `{case}.txt` | Ordered landmark coordinates |
| `FILE_D` | `.xlsx` workbook | Case identifier and calibrated mm/pixel value |

Masks and source image must have identical dimensions and registration. Use binary grayscale masks (0 background, 255 foreground; the original reader also recognizes foreground value 1). Prepare the masks and landmarks before starting the planning workflow.

TXT format is UTF-8 without BOM, one `x,y` coordinate pair per line; coordinates are pixels with x rightward and y downward. Rows 1–2, 3–4, 5–6, 7–8 define the four reference lines consumed by the core. Preserve the landmark identities and ordering from the original annotation protocol; arbitrary reordering changes the geometry. Row 9 is the contralateral center used by the existing study-specific adapter. The synthetic fixture illustrates this file structure; use the study annotation protocol for anatomical inputs.

The scale workbook has a header row. `FILE_D_STEM_COL` and `FILE_D_SCALE_COL` are **1-based** column positions. In the default configuration these are 1 and 57; the demo workbook explicitly uses 1 and 2. A scale of 0.5 means one image pixel represents 0.5 mm. Each case must have exactly one positive, finite scale value. No scale of 1.0 is silently substituted by the wrapper.

Set `SAVE_FOLDER` to a dedicated GUI-output directory. The original interface can add missing line endpoints to saved-plan JSON files there when checking compatibility. Keep archival data elsewhere. CLI outputs use `outputs/cli` unless `--output` is supplied.

## Configuration

The four Crowe groups of fixed constraints retain the values supplied with this implementation. They define the planner's geometric ranges, ideals and scoring weights. Preserve the pixel units of geometric constraints; physical-unit outputs use the calibrated scale. `COVERAGE_THRESHOLD=80.0`, `MIN_SAFE_DIAMETER=40.0`, the curve-clearance parameters, scoring weights and search implementation are unchanged.

Use Python booleans (`True` or `False`) for `PERSONALIZED_CONSTRAINTS_ENABLE`. The default `False` selects fixed constraints. Setting it to `True` selects the existing study-specific adapter and requires a compatible constraint-source environment; see [integration](INTEGRATION.md). The launcher checks adapter initialization before starting the requested mode.

## CLI output

The CLI stores a batch payload with case, mode, scale information, constraint-application status and a `plans` list. This is **not** the GUI's single saved-plan JSON schema. Do not copy it into the GUI save directory or load it as a saved plan.

| Plan field | Interpretation |
|---|---|
| `outer_point`, `center_point` | Image coordinates, pixels |
| `circle_diameter` | Continuous geometric diameter in pixels |
| `actual_diameter` | Continuous geometric diameter in mm |
| `safe_even_diameter` | Nominal even cup diameter in mm |
| `distance_to_line1/2/3/4/8` | Geometric distances in pixels |
| `scale_factor` | mm/pixel |
| `line6_angle_rad`, `line7_angle_rad` | Radians; internal oriented image geometry |
| `line6_angle_deg`, `line7_angle_deg` | Degrees; do not automatically equate every internal angle with cup inclination |
| `coverage_rate_angle` | Angular coverage percentage from the original formula |
| `coverage_rate_horizontal` | Original unbounded horizontal index; can exceed 100 or be negative |
| `is_valid` | Original constraint validity flag |
| `is_special_fallback` | True for a fallback candidate |
| `final_score`, `scores` | Original ranking scores; not probabilities and not bounded to 0–1 |

A nonfinite value, if produced, is written as JSON `null`; its field path is listed under `nonfinite_values_serialized_as_null`. Finite results are not rounded or rescaled by the wrapper. A nonempty output does not itself mean every constraint was satisfied.
