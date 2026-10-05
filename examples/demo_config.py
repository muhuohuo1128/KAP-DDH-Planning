"""Synthetic geometry only; not patient data or a KB-enabled experiment."""
from pathlib import Path
import runpy
ROOT = Path(__file__).resolve().parents[1]
original = runpy.run_path(str(ROOT / 'config.py'))
EXTRA_SYS_PATHS = []
PARAMS = dict(original['PARAMS'])
PARAMS.update(PERSONALIZED_CONSTRAINTS_ENABLE=False, FILE_D_STEM_COL=1, FILE_D_SCALE_COL=2)
FIXED_CONSTRAINT_IDEALS = original['FIXED_CONSTRAINT_IDEALS']
INPUT_STATUS = 'SYNTHETIC GEOMETRY ONLY; NOT PATIENT DATA OR STUDY RESULTS'
DATA = ROOT / 'examples' / 'synthetic'
PATHS = {
    'FOLDER_A': str(DATA / 'images'), 'FOLDER_B': str(DATA / 'rim'),
    'FOLDER_C': str(DATA / 'landmarks'), 'FOLDER_C4': str(DATA / 'upper'),
    'FOLDER_C3': str(DATA / 'lower'), 'FILE_D': str(DATA / 'scale.xlsx'),
    'SAVE_FOLDER': str(ROOT / 'outputs' / 'synthetic_gui'),
    'KB_GNN_DIR': '', 'KB_XLSX_PATH': '', 'KB_WEIGHTS_PATH': '',
    'KB_TXT_ROOT': '', 'KB_VECTOR_CACHE_PATH': '',
    'PERSONALIZED_EXPORT_XLSX_PATH': '',
}
