# Synthetic fixed-constraint example

This example provides a small, runnable geometry fixture for demonstrating the preoperative planning module. Its inputs are synthetic, and its computed outputs serve as software verification references.

## Geometry and configuration

The 512×512 background grid is labeled as synthetic. Four pairs of reference-line endpoints, a ninth point, one candidate rim pixel and two remote exclusion lines form the input. Pixel spacing is 0.5 mm/pixel. The deliberately simple geometry is intended to exercise the planner rather than represent an anatomical reconstruction.

`demo_config.py` reuses the fixed numerical constraints from `config.py`, supplies local input/output paths, selects scale-table columns 1 and 2, and selects fixed-constraint mode. The supplied inputs can be regenerated with `scripts/generate_synthetic_inputs.py`.

## Run and inspect

Run these commands from the repository root:

```bash
python run_planning.py --config examples/demo_config.py --case SYNTHETIC_001 --level 1
python scripts/verify_demo.py
```

For interactive inspection:

```bash
python run_planning.py --config examples/demo_config.py --gui
```

Select `SYNTHETIC_001`, Crowe class I, and **Planning → Generate Preoperative Plans**.

## Computed reference

| Output | Expected value |
|---|---:|
| Returned regular plans | 1 |
| Returned fallback plans | 1 |
| First regular plan: `is_valid` | true |
| Continuous diameter `actual_diameter` (mm) | 51.29163345616005 |
| Nominal diameter `safe_even_diameter` (mm) | 52 |
| Angular coverage `coverage_rate_angle` (%) | 93.88888888888887 |
| Horizontal index `coverage_rate_horizontal` | 102.13488663742815 |
| Center x, y (pixels) | 348.4648541907107, 181.29163345616007 |

Diameter, coverage and center values refer to the first regular plan. The horizontal index follows the existing formula and can fall outside 0–100; it is distinct from angular coverage percentage.

`expected/result.json` stores the computed CLI payload. `expected/best_plan.png` was rendered by the core visualization function using nominal cup diameter, while the JSON preserves both continuous and nominal diameters. `expected/gui_preview.png` records the interface preview. These reference outputs belong to the synthetic software example, independently of the manuscript's study results.

To compute a new result and render its image:

```bash
python scripts/render_demo.py
```

This saves `outputs/cli/synthetic_best_plan.png` and the corresponding computed JSON.
