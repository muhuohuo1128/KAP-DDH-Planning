"""Portable configuration for the KAP-DDH preoperative planning module.
The released example uses fixed-constraint mode. Numerical constraints retain
the supplied implementation values. Read docs/INPUTS.md for prepared inputs
and docs/INTEGRATION.md for study-specific constraint integration.
Paths are resolved from this file, independently of the working directory.
"""
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
EXTRA_SYS_PATHS = []
PATHS = {
    'FOLDER_A': str(BASE_DIR / 'data' / 'images'),
    'FOLDER_B': str(BASE_DIR / 'data' / 'curve1'),
    'FOLDER_C': str(BASE_DIR / 'data' / 'landmarks'),
    'FOLDER_C4': str(BASE_DIR / 'data' / 'curve2'),
    'FOLDER_C3': str(BASE_DIR / 'data' / 'curve3'),
    'FILE_D': str(BASE_DIR / 'data' / 'scales.xlsx'),
    'SAVE_FOLDER': str(BASE_DIR / 'outputs' / 'gui'),
    'KB_GNN_DIR': '',
    'KB_XLSX_PATH': '',
    'KB_WEIGHTS_PATH': '',
    'KB_TXT_ROOT': '',
    'KB_VECTOR_CACHE_PATH': '',
    'PERSONALIZED_EXPORT_XLSX_PATH': '',
}
# Scale column and all other numerical settings retain the supplied values.
# The synthetic demo overrides its own file paths and scale-column mapping.
PARAMS = {'COVERAGE_THRESHOLD': 80.0,
 'MIN_SAFE_DIAMETER': 40.0,
 'MIN_CURVE2_DISTANCE': 2,
 'MIN_CURVE3_DISTANCE': 2,
 'ZOOM_MIN': 0.1,
 'ZOOM_MAX': 10.0,
 'FILE_D_STEM_COL': 1,
 'FILE_D_SCALE_COL': 57,
 'PERSONALIZED_CONSTRAINTS_ENABLE': False,
 'KB_EXPECT_N_POINTS': 9,
 'KB_DYNAMIC_TOPK_ENABLE': True,
 'KB_RETURN_K_BY_CROWE': {1: 100, 2: 50, 3: 30, 4: 30},
 'KB_TOPK_FIXED': 10,
 'KB_VECTOR_CACHE_ENABLE': True,
 'KB_FORCE_REBUILD_CACHE': False,
 'KB_STEM_COL': 1,
 'KB_CROWE_COL': 10,
 'KB_CONSTRAINT_COLS': {'circle_diameter': 22,
                        'distance_to_line1': 26,
                        'distance_to_line4': 28,
                        'distance_to_line2': 25,
                        'distance_to_line3': 27,
                        'distance_to_line8': 29}}

FIXED_CONSTRAINT_IDEALS = {1: {'circle_diameter': {'min': 76.026, 'max': 134.466, 'weight': 0.25, 'ideal': 102.5802},
     'distance_to_line1': {'min': 14.4892, 'max': 81.5357, 'weight': 0.15, 'ideal': 42.1895},
     'distance_to_line4': {'min': 21.1939, 'max': 77.7665, 'weight': 0.15, 'ideal': 50.0235},
     'distance_to_line2': {'min': 204.3568, 'max': 364.1266, 'weight': 0.15, 'ideal': 270.7587},
     'distance_to_line3': {'min': 71.4224, 'max': 200.7667, 'weight': 0.15, 'ideal': 129.2622},
     'distance_to_line8': {'min': 128.395, 'max': 227.287, 'weight': 0.15, 'ideal': 173.9077}},
 2: {'circle_diameter': {'min': 83.629, 'max': 127.722, 'weight': 0.25, 'ideal': 101.873},
     'distance_to_line1': {'min': 16.9454, 'max': 99.0464, 'weight': 0.15, 'ideal': 50.6589},
     'distance_to_line4': {'min': 32.3463, 'max': 79.189, 'weight': 0.15, 'ideal': 50.3104},
     'distance_to_line2': {'min': 201.3865, 'max': 331.36, 'weight': 0.15, 'ideal': 262.1348},
     'distance_to_line3': {'min': 75.8492, 'max': 188.2086, 'weight': 0.15, 'ideal': 133.7728},
     'distance_to_line8': {'min': 130.449, 'max': 217.695, 'weight': 0.15, 'ideal': 175.2478}},
 3: {'circle_diameter': {'min': 77.936, 'max': 115.966, 'weight': 0.25, 'ideal': 94.8846},
     'distance_to_line1': {'min': 7.1642, 'max': 87.83, 'weight': 0.15, 'ideal': 46.1086},
     'distance_to_line4': {'min': 26.3051, 'max': 72.144, 'weight': 0.15, 'ideal': 43.1301},
     'distance_to_line2': {'min': 201.2605, 'max': 344.6253, 'weight': 0.15, 'ideal': 267.9214},
     'distance_to_line3': {'min': 69.8591, 'max': 181.9472, 'weight': 0.15, 'ideal': 119.7932},
     'distance_to_line8': {'min': 125.82, 'max': 221.694, 'weight': 0.15, 'ideal': 170.0625}},
 4: {'circle_diameter': {'min': 75.444, 'max': 111.501, 'weight': 0.25, 'ideal': 88.4746},
     'distance_to_line1': {'min': 0.0204, 'max': 74.5543, 'weight': 0.15, 'ideal': 30.5686},
     'distance_to_line4': {'min': 17.0285, 'max': 57.7657, 'weight': 0.15, 'ideal': 34.0174},
     'distance_to_line2': {'min': 223.1698, 'max': 365.3042, 'weight': 0.15, 'ideal': 278.7535},
     'distance_to_line3': {'min': 51.8595, 'max': 159.3623, 'weight': 0.15, 'ideal': 97.544},
     'distance_to_line8': {'min': 116.183, 'max': 201.569, 'weight': 0.15, 'ideal': 156.6358}}}
