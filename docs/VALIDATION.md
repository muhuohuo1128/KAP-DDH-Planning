# Software validation record

Version: 1.0.0. Preparation checks completed: 2026-10-05.

These checks cover the public planning module, its synthetic fixed-constraint workflow and its launch interfaces. They record software behavior in the tested environment; the release scope is described in the [README](../README.md#scope-and-availability).

## Checks performed during version 1.0.0 preparation

| Check | Result |
|---|---|
| All 57 top-level core function/class definitions compared with the supplied implementation by Python AST | Identical, including nested bodies |
| Fixed-constraint values and weights compared with the supplied configuration | Identical |
| Other configuration parameter values compared | Preserved, with `PERSONALIZED_CONSTRAINTS_ENABLE=False` selected as the release default |
| Supplied English UI compared with the packaged UI | English module imports and three display-only inclination corrections |
| Python syntax compilation | Passed |
| Supplied core and packaged CPU launcher run on the synthetic fixture | Both returned one regular plan and one fallback plan; numerical plan fields matched the computed reference |
| Repeated synthetic calculation | Identical numerical results in the tested environment |
| Core visualization | PNG generated successfully |
| PyQt5 interface construction and case loading | Passed under Qt offscreen |
| GUI Generate action, worker completion and displayed planning image | Passed under Qt offscreen; four angular/horizontal presentation entries for the two returned candidates |
| Zero scale, duplicate scale rows and BOM-prefixed landmarks | Each tested invalid input was rejected by the launcher |
| Requested adapter mode with unavailable initialization dependencies | Startup was rejected as configured |
| Installation in a new Python environment without system-site packages | Completed; `pip check` reported no broken requirements |

During version 1.0.0 preparation, three inclination display paths were corrected to show the acute angle between the cup axis and reference line. In the synthetic check, a configuration previously labeled 140° displayed 40°. Stored oriented angles and planning result dictionaries were preserved.

The two raw candidates can appear in both the GUI's angular and horizontal presentation groups. Displayed entry counts therefore describe the interface's organization of plans.

## Tested environment

Python 3.12 on Linux x86_64, using the CPU: NumPy 2.3.5, OpenCV package 5.0.0.93, pandas 2.2.3, matplotlib 3.10.8, Pillow 12.3.0, openpyxl 3.1.5 and PyQt5 5.15.11. Direct dependencies are pinned in [requirements.txt](../requirements.txt).

These versions describe the software preparation environment. Dependency installation took 43.915 seconds with the normal pip cache enabled. Installation time depends on the network and hardware.

The recorded GUI checks used Qt offscreen. Interactive Windows/macOS use, GPU execution and the study-specific adapter require their own environment-specific checks. The synthetic checks assess software execution, not clinical performance or manuscript-level results.

## Supported use and diagnostics

Use `run_planning.py` for CPU planning or to launch the graphical interface. The direct core-script entry point and its legacy export helper are retained as source history; the supported launcher provides the documented input checks and output handling.

The launcher restores global traceback printing after importing the original modules. Internal worker exception handling remains as implemented. Review the input geometry and available logs if a run returns no candidates. Interpret returned plans using the validity and fallback flags described in [the output reference](INPUTS.md#cli-output).
