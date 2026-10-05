import os
import numpy as np
import cv2
import math
import sys
try:
    import config as _config
except Exception:
    _config = None

if _config:
    for _p in (getattr(_config, 'EXTRA_SYS_PATHS', None) or []):
        if _p and _p not in sys.path:
            sys.path.insert(0, _p)

_CONFIG_PATHS = getattr(_config, 'PATHS', {}) if _config else {}
_CONFIG_PARAMS = getattr(_config, 'PARAMS', {}) if _config else {}


def _cfg_path(key, default=""):
    v = _CONFIG_PATHS.get(key)
    return v if isinstance(v, str) and v else default


def _cfg_float(key, default):
    try:
        return float(_CONFIG_PARAMS.get(key, default))
    except Exception:
        return float(default)


COVERAGE_THRESHOLD = _cfg_float('COVERAGE_THRESHOLD', 80.0)
MIN_SAFE_DIAMETER = _cfg_float('MIN_SAFE_DIAMETER', 40.0)
import pandas as pd
from matplotlib import pyplot as plt
from PIL import Image, ImageDraw, ImageFont
from collections import Counter
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import builtins as _builtins
import traceback as _traceback

_ORIG_PRINT = _builtins.print
_now_ms = lambda: time.perf_counter() * 1000.0
_CURRENT_LOG_CASE = None


def _log(msg):
    try:
        _ORIG_PRINT(msg)
    except Exception:
        pass


def _log_case(file_name, msg):
    s = str(file_name or "").strip()
    global _CURRENT_LOG_CASE
    if not s:
        _log(str(msg))
        return
    if s != _CURRENT_LOG_CASE:
        _CURRENT_LOG_CASE = s
        _log(f"------------{s}-----------")
    _log(str(msg))


def print(*args, **kwargs):
    return


try:
    _traceback.print_exc = lambda *args, **kwargs: None
except Exception:
    pass

# 全局诊断汇总（不影响算法，仅用于打印统计）
GLOBAL_DIAG_SUMMARY = {
    'outer_points_processed': 0,
    'attempts': 0,
    'elim_intersects': 0,
    'elim_safe_even_invalid': 0,
    'elim_safe_even_lt40': 0,
    'need_cover_count': 0,
    'curve2_dist_lt1px_count': 0,
    # 预候选阶段汇总计数（仅诊断，不参与筛选）
    'pre_angle_trials_total': 0,
    'pre_angle_relation_failures_total': 0,
    'pre_angle_relation_pass_no_centers_total': 0,
    'constraint_failures': {
        'circle_diameter': 0,
        'distance_to_line1': 0,
        'distance_to_line4': 0,
        'distance_to_line2': 0,
        'distance_to_line3': 0,
        'distance_to_line8': 0
    }
}
GLOBAL_DIAG_LOCK = threading.Lock()
GLOBAL_PRE_DIAG = {}

# GPU加速相关导入
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("警告: PyTorch未安装，GPU加速功能将不可用")

# 默认文件夹路径
DEFAULT_FOLDER_A = _cfg_path('FOLDER_A', "")
DEFAULT_FOLDER_B = _cfg_path('FOLDER_B', "")
DEFAULT_FOLDER_C = _cfg_path('FOLDER_C', "")
DEFAULT_FOLDER_C4 = _cfg_path('FOLDER_C4', "")
DEFAULT_FOLDER_C3 = _cfg_path('FOLDER_C3', "")
DEFAULT_FILE_D = _cfg_path('FILE_D', "")

# 全局变量，将在main函数中根据命令行参数或使用默认值设置
FOLDER_A = None
FOLDER_B = None
FOLDER_C = None
FOLDER_C4 = None
FOLDER_C3 = None  # 新增
FILE_D = None


def read_scale_from_excel(file_name):
    """从Excel文件中读取比例尺"""
    try:
        # 读取Excel文件
        df = pd.read_excel(FILE_D)

        # 获取文件名（不含扩展名）
        base_name = os.path.splitext(file_name)[0]

        # 查找对应的行
        stem_col = max(1, _cfg_int('FILE_D_STEM_COL', 1)) - 1
        scale_col = max(1, _cfg_int('FILE_D_SCALE_COL', 10)) - 1
        if stem_col >= df.shape[1] or scale_col >= df.shape[1]:
            return 1.0
        row = df[df.iloc[:, stem_col].astype(str).str.strip() == str(base_name).strip()]

        if not row.empty:
            v = row.iloc[0, scale_col]
            scale = float(v)
            return scale
        else:
            print(f"警告：在Excel文件中未找到 {base_name} 对应的比例尺")
            return 1.0  # 如果找不到，返回默认值1.0
    except Exception as e:
        print(f"读取Excel文件时出错: {str(e)}")
        return 1.0  # 发生错误时返回默认值1.0


CONSTRAINT_IDEALS = None
CURRENT_LEVEL = 1
CURRENT_NORM_DENOM = 1.0


def _cfg_bool(key, default=False):
    try:
        return bool(_CONFIG_PARAMS.get(key, default))
    except Exception:
        return bool(default)


def _cfg_int(key, default):
    try:
        return int(_CONFIG_PARAMS.get(key, default))
    except Exception:
        return int(default)


def calculate_midpoint_distance(point1, point2, point3, point4):
    midpoint1 = (np.array(point1, dtype=float) + np.array(point2, dtype=float)) / 2.0
    midpoint2 = (np.array(point3, dtype=float) + np.array(point4, dtype=float)) / 2.0
    distance = float(np.linalg.norm(midpoint1 - midpoint2))
    return round(distance, 3)


def _calc_norm_denom(points):
    try:
        if not points or len(points) < 6:
            return 1.0
        d = calculate_midpoint_distance(points[2], points[3], points[4], points[5])
        if d and d > 1e-9:
            return float(d)
    except Exception:
        pass
    return 1.0


def update_constraint_ideals(level):
    global CONSTRAINT_IDEALS, CURRENT_LEVEL
    CURRENT_LEVEL = int(level)
    CONSTRAINT_IDEALS = None


_KB_INDEX = None
_KB_SEARCH_MOD = None
_KB_LOCK = threading.Lock()
_KB_INDEX_LOAD_MS = None
_KB_INDEX_LOAD_LOGGED = False
_PERSONALIZED_EXPORT_LOCK = threading.Lock()


def _export_personalized_row(file_name, search_ms, ideals):
    out_path = _cfg_path('PERSONALIZED_EXPORT_XLSX_PATH', '')
    out_path = str(out_path or '').strip()
    if not out_path:
        return
    if not ideals or not isinstance(ideals, dict):
        return

    keys = [
        'circle_diameter',
        'distance_to_line1',
        'distance_to_line4',
        'distance_to_line2',
        'distance_to_line3',
        'distance_to_line8',
    ]

    try:
        from openpyxl import Workbook, load_workbook
    except Exception:
        return

    def _num(v):
        try:
            return float(v)
        except Exception:
            return None

    row = [str(file_name or ''), _num(search_ms)]
    for k in keys:
        cfg = ideals.get(k) if isinstance(ideals.get(k), dict) else {}
        row.extend([_num(cfg.get('min')), _num(cfg.get('max')), _num(cfg.get('ideal'))])

    header = ['file_name', 'search_ms']
    for k in keys:
        header.extend([f'{k}_min', f'{k}_max', f'{k}_ideal'])

    with _PERSONALIZED_EXPORT_LOCK:
        try:
            if os.path.exists(out_path):
                wb = load_workbook(out_path)
                ws = wb.active
            else:
                d = os.path.dirname(os.path.abspath(out_path))
                if d:
                    os.makedirs(d, exist_ok=True)
                wb = Workbook()
                ws = wb.active
                ws.append(header)
            ws.append(row)
            wb.save(out_path)
            try:
                wb.close()
            except Exception:
                pass
        except Exception as e:
            _log_case(file_name, f"写入个性化约束xlsx失败: {e}")


def _get_fixed_constraint_ideals(level):
    fixed = getattr(_config, 'FIXED_CONSTRAINT_IDEALS', None) if _config else None
    fixed = fixed or {}
    src = fixed.get(int(level)) or {}
    return {k: dict(v) for k, v in src.items()} if src else {}


def _normalize_constraint_ideals(ideals, denom):
    try:
        d = float(denom)
    except Exception:
        d = 1.0
    if d <= 1e-9:
        d = 1.0
    out = {}
    ideals = ideals or {}
    for k, cfg in ideals.items():
        if not isinstance(cfg, dict):
            continue
        new_cfg = dict(cfg)
        for f in ('min', 'max', 'ideal'):
            if f in new_cfg and new_cfg[f] is not None:
                try:
                    new_cfg[f] = float(new_cfg[f]) / d
                except Exception:
                    pass
        out[k] = new_cfg
    return out


def _read_xlsx_cols(xlsx_path, stems, cols):
    from openpyxl import load_workbook
    stem_col = max(1, _cfg_int('KB_STEM_COL', 1)) - 1
    stems_set = {str(s).strip() for s in stems if s is not None}
    cols = [int(c) for c in cols]
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    out = {}
    for row in ws.iter_rows(values_only=True):
        if not row:
            continue
        stem = row[stem_col] if stem_col < len(row) else None
        if stem is None:
            continue
        stem = str(stem).strip()
        if stem not in stems_set:
            continue
        m = {}
        for c in cols:
            i = int(c) - 1
            m[int(c)] = row[i] if i < len(row) else None
        out[stem] = m
    wb.close()
    return out


def _get_kb_index():
    global _KB_INDEX, _KB_SEARCH_MOD
    if _KB_INDEX is not None and _KB_SEARCH_MOD is not None:
        return _KB_INDEX, _KB_SEARCH_MOD

    with _KB_LOCK:
        if _KB_INDEX is not None and _KB_SEARCH_MOD is not None:
            return _KB_INDEX, _KB_SEARCH_MOD

        try:
            t0 = _now_ms()
            base_dir = os.path.dirname(os.path.abspath(__file__))
            kb_dir = _cfg_path('KB_GNN_DIR', '') or os.path.join(base_dir, '知识库检索-gnn')
            if kb_dir and kb_dir not in sys.path:
                sys.path.insert(0, kb_dir)

            import search_vis as kb_search_vis
            try:
                import kb_config as kb_cfg
                kb_stem_col = _cfg_int('KB_STEM_COL', getattr(kb_cfg, 'STEM_COL', 1))
                kb_crowe_col = _cfg_int('KB_CROWE_COL', getattr(kb_cfg, 'CROWE_COL', 7))
                kb_cfg.STEM_COL = int(kb_stem_col)
                kb_cfg.CROWE_COL = int(kb_crowe_col)
            except Exception:
                pass

            kb_weights = _cfg_path('KB_WEIGHTS_PATH', '')
            if kb_weights:
                kb_search_vis.WEIGHTS_PATH = kb_weights

            kwargs = {}
            kb_txt_root = _cfg_path('KB_TXT_ROOT', '')
            kb_xlsx = _cfg_path('KB_XLSX_PATH', '')
            if kb_txt_root:
                kwargs['txt_root'] = kb_txt_root
            if kb_xlsx:
                kwargs['xlsx_path'] = kb_xlsx
            kwargs['cache_enable'] = _cfg_bool('KB_VECTOR_CACHE_ENABLE', True)
            kwargs['force_rebuild_cache'] = _cfg_bool('KB_FORCE_REBUILD_CACHE', False)
            kb_cache_path = _cfg_path('KB_VECTOR_CACHE_PATH', '')
            if kb_cache_path:
                kwargs['cache_path'] = kb_cache_path

            idx = kb_search_vis.BucketIndex(**kwargs)
            _KB_INDEX = idx
            _KB_SEARCH_MOD = kb_search_vis
            try:
                global _KB_INDEX_LOAD_MS
                if _KB_INDEX_LOAD_MS is None:
                    _KB_INDEX_LOAD_MS = float(_now_ms() - t0)
            except Exception:
                pass
            return _KB_INDEX, _KB_SEARCH_MOD
        except Exception:
            _KB_INDEX = None
            _KB_SEARCH_MOD = None
            return None, None


def _apply_personalized_constraint_ideals(file_name, level, fixed_raw=None):
    global CONSTRAINT_IDEALS

    fixed = fixed_raw or _get_fixed_constraint_ideals(level)
    if not fixed:
        _log_case(file_name, "个性化约束检索失败：固定约束为空")
        return False

    idx, kb_search_vis = _get_kb_index()
    if idx is None or kb_search_vis is None:
        _log_case(file_name, "个性化约束检索失败：索引未就绪")
        return False
    try:
        global _KB_INDEX_LOAD_LOGGED, _KB_INDEX_LOAD_MS
        if (not _KB_INDEX_LOAD_LOGGED) and (_KB_INDEX_LOAD_MS is not None):
            _log_case(file_name, f"索引加载耗时: {float(_KB_INDEX_LOAD_MS):.2f}ms")
            _KB_INDEX_LOAD_LOGGED = True
    except Exception:
        pass

    try:
        t_search0 = _now_ms()
        use_dynamic_k = _cfg_bool('KB_DYNAMIC_TOPK_ENABLE', True)
        if use_dynamic_k:
            topk_request = 1
        else:
            topk_request = max(1, _cfg_int('KB_TOPK_FIXED', 10))
        query_txt_path = os.path.join(FOLDER_C or '', f'{file_name}.txt')
        expected_n = _cfg_int('KB_EXPECT_N_POINTS', 0)
        if expected_n > 0:
            try:
                with open(query_txt_path, 'r', encoding='utf-8') as f:
                    n_lines = sum(1 for line in f if line.strip())
                if n_lines != int(expected_n):
                    _log_case(file_name, f"个性化约束检索失败：txt点数不一致 expected={int(expected_n)} actual={int(n_lines)}")
                    return False
            except Exception:
                pass
        try:
            if hasattr(kb_search_vis, 'DYNAMIC_TOPK'):
                kb_search_vis.DYNAMIC_TOPK = use_dynamic_k
            if hasattr(kb_search_vis, 'RETURN_K_BY_CROWE'):
                m = _CONFIG_PARAMS.get('KB_RETURN_K_BY_CROWE', {}) if _CONFIG_PARAMS else {}
                if isinstance(m, dict) and m:
                    kb_search_vis.RETURN_K_BY_CROWE = {int(k): int(v) for k, v in m.items()}
        except Exception:
            pass

        card = idx.search(query_txt_path, top_k=topk_request, with_gradient=False, with_occlusion=False)
        if not card:
            try:
                stem = os.path.splitext(os.path.basename(query_txt_path))[0]
                crowe = None
                try:
                    crowe = getattr(idx, "crowe_map", {}).get(stem)
                except Exception:
                    crowe = None
                if crowe not in (1, 2, 3, 4):
                    _log_case(file_name, f"个性化约束检索失败：search返回空（xlsx未找到该病例Crowe分型）stem={stem}")
                else:
                    n_same = None
                    try:
                        b = getattr(idx, "buckets", {}).get(int(crowe))
                        n_same = int(getattr(b, "shape", [0])[0]) if b is not None else 0
                    except Exception:
                        n_same = None
                    if n_same == 0:
                        _log_case(file_name, f"个性化约束检索失败：search返回空（该Crowe桶为空）crowe={int(crowe)}")
                    else:
                        _log_case(file_name, "个性化约束检索失败：search返回空")
            except Exception:
                _log_case(file_name, "个性化约束检索失败：search返回空")
            return False
        results_all = (card.get('results') or [])
        topk_effective = None
        if use_dynamic_k:
            try:
                topk_effective = int((card.get('topk') or {}).get('return_k') or 0)
            except Exception:
                topk_effective = None
        if not topk_effective:
            topk_effective = len(results_all) if results_all else topk_request
        results = results_all[: max(1, int(topk_effective))]
        if not results:
            _log_case(file_name, "个性化约束检索失败：无有效相似病例")
            return False

        stems = [r.get('stem') for r in results if r and r.get('stem')]
        if not stems:
            _log_case(file_name, "个性化约束检索失败：相似病例stem为空")
            return False
        top1_stem = str(stems[0]).strip()

        cols_map = _CONFIG_PARAMS.get('KB_CONSTRAINT_COLS', {}) if _CONFIG_PARAMS else {}
        cols_map = cols_map if isinstance(cols_map, dict) else {}
        needed_cols = [int(cols_map.get(k, 1)) for k in fixed.keys()]

        xlsx_path = _cfg_path('KB_XLSX_PATH', '') or getattr(idx, 'xlsx_path', '')
        if not xlsx_path:
            _log_case(file_name, "个性化约束检索失败：KB_XLSX_PATH为空")
            return False

        xlsx = _read_xlsx_cols(xlsx_path, stems, needed_cols)

        new_ideals = {}
        for k, base_cfg in fixed.items():
            col = int(cols_map.get(k, 1))
            vals = []
            top1_val = None
            for s in stems:
                v = xlsx.get(str(s).strip(), {}).get(col)
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                try:
                    fv = float(v)
                except Exception:
                    continue
                vals.append(fv)
                if top1_val is None and str(s).strip() == top1_stem:
                    top1_val = fv

            if vals:
                vmin = float(min(vals))
                vmax = float(max(vals))
                if top1_val is None:
                    try:
                        v = xlsx.get(top1_stem, {}).get(col)
                        top1_val = float(v) if v is not None else None
                    except Exception:
                        top1_val = None

                if vmin < vmax and top1_val is not None:
                    new_ideals[k] = {
                        'min': vmin,
                        'max': vmax,
                        'ideal': float(top1_val),
                        'weight': float(base_cfg.get('weight', 0.0)),
                    }
                    continue

            new_ideals[k] = dict(base_cfg)

        CONSTRAINT_IDEALS = new_ideals
        try:
            _export_personalized_row(file_name, float(_now_ms() - t_search0), new_ideals)
        except Exception:
            pass
        try:
            _log_case(file_name, f"检索耗时: {float(_now_ms() - t_search0):.2f}ms")
        except Exception:
            pass
        for k, cfg in new_ideals.items():
            if not isinstance(cfg, dict):
                continue
            try:
                _log_case(file_name, f"个性化约束 {k}: min={float(cfg.get('min')):.6f} max={float(cfg.get('max')):.6f} ideal={float(cfg.get('ideal')):.6f}")
            except Exception:
                _log_case(file_name, f"个性化约束 {k}: {cfg}")
        return True
    except Exception:
        _log_case(file_name, "个性化约束检索失败：异常")
        return False


def calculate_line_angle(point1, point2):
    """计算直线的角度（弧度）"""
    delta_x = point2[0] - point1[0]
    delta_y = point2[1] - point1[1]
    return math.atan2(delta_y, delta_x)


def calculate_distance_point_to_line(point, line_eq):
    """计算点到直线的距离"""
    a, b, c = line_eq
    return abs(a * point[0] + b * point[1] + c) / math.sqrt(a ** 2 + b ** 2)

def normalize_line6_angle(center_point, outer_point, line6_angle_rad):
    """
    统一线6角度方向：确保线6的+90°法线指向半圆开口侧（外沿点所在侧）。

    参数:
        center_point: 圆心坐标 (x, y)
        outer_point: 外沿点坐标 (x, y)
        line6_angle_rad: 当前线6角度（弧度）

    返回:
        归一化后的线6角度（弧度）。
    """
    try:
        if center_point is None or outer_point is None or line6_angle_rad is None:
            return line6_angle_rad
        # 线6的方向向量
        dx = math.cos(line6_angle_rad)
        dy = math.sin(line6_angle_rad)
        # +90°法线（顺时针）与 is_point_on_arc_side 中的定义保持一致
        perp_dx = dy
        perp_dy = -dx
        # 从中心到外沿点的向量
        vx = outer_point[0] - center_point[0]
        vy = outer_point[1] - center_point[1]
        # 点积判断半圆侧
        dot = vx * perp_dx + vy * perp_dy
        if dot < 0:
            # 翻转线6方向 180°
            return (line6_angle_rad + math.pi) % (2 * math.pi)
        return line6_angle_rad % (2 * math.pi)
    except Exception:
        return line6_angle_rad


def adjust_negative_angle(angle_rad):
    """
    将任意“水平角度”统一到[-π, π]，并将正角转换为对应的负角：
    - 先归一化到[-π, π]
    - 若结果为正值，则减去π，使其成为对应的负角（例如 +30° -> -150°）

    说明：这是对角度计算值的统一处理，确保线6、线7的角度落在-180°~180°，且不为正。
    """
    try:
        if angle_rad is None:
            return None
        # 归一化到[-π, π]
        ang = (angle_rad + math.pi) % (2 * math.pi) - math.pi
        # 将正角转换为对应的负角
        if ang > 0:
            ang = ang - math.pi
        return ang
    except Exception:
        return angle_rad


def read_image_with_pil(image_path):
    """
    使用PIL读取图像，然后转换为OpenCV格式
    支持中文路径
    """
    try:
        # 使用PIL读取图像
        pil_img = Image.open(image_path)
        # 转换为灰度图
        if pil_img.mode != 'L':
            pil_img = pil_img.convert('L')
        # 转换为numpy数组
        img_array = np.array(pil_img)
        return img_array
    except Exception as e:
        raise Exception(f"无法读取图像 {image_path}: {str(e)}")


def read_image_with_cache(image_path, image_cache, cache_lock=None):
    """
    线程安全的图像读取函数，带缓存机制
    
    Args:
        image_path: 图像文件路径
        image_cache: 图像缓存字典
        cache_lock: 线程锁，用于线程安全
    
    Returns:
        numpy.ndarray: 图像数组
    """
    # 首先尝试从缓存中获取
    cached_image = thread_safe_cache_access(image_cache, image_path, cache_lock)
    if cached_image is not None:
        return cached_image
    
    # 缓存中没有，读取图像
    try:
        # 使用PIL读取图像
        pil_img = Image.open(image_path)
        # 转换为灰度图
        if pil_img.mode != 'L':
            pil_img = pil_img.convert('L')
        # 转换为numpy数组
        img_array = np.array(pil_img)
        
        # 将结果存入缓存
        thread_safe_cache_update(image_cache, image_path, img_array, cache_lock)
        
        return img_array
    except Exception as e:
        raise Exception(f"无法读取图像 {image_path}: {str(e)}")


def find_lowest_point(curve_img_path):
    """找到曲线图像中的最低点（y坐标最大的点）"""
    # 使用PIL读取图像（支持中文路径）
    try:
        img = read_image_with_pil(curve_img_path)
    except Exception as e:
        raise FileNotFoundError(f"无法读取图像 {curve_img_path}: {str(e)}")

    # 找到所有值为1的像素点
    y_indices, x_indices = np.where(img == 1)

    if len(y_indices) == 0:
        # 如果没有找到值为1的像素点，尝试二值化图像
        _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
        y_indices, x_indices = np.where(img > 0)

    if len(y_indices) == 0:
        raise ValueError(f"在图像中没有找到曲线像素")

    # 找到y坐标最大的点（图像坐标系中y向下增长）
    max_y_index = np.argmax(y_indices)
    lowest_x = x_indices[max_y_index]
    lowest_y = y_indices[max_y_index]

    return (lowest_x, lowest_y)


def find_highest_point(curve_img_path):
    """找到曲线图像中的最高点（y坐标最小的点）"""
    # 使用PIL读取图像（支持中文路径）
    try:
        img = read_image_with_pil(curve_img_path)
    except Exception as e:
        raise FileNotFoundError(f"无法读取图像 {curve_img_path}: {str(e)}")

    # 找到所有值为1的像素点
    y_indices, x_indices = np.where(img == 1)

    if len(y_indices) == 0:
        # 如果没有找到值为1的像素点，尝试二值化图像
        _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
        y_indices, x_indices = np.where(img > 0)

    if len(y_indices) == 0:
        raise ValueError(f"在图像中没有找到曲线像素")

    # 找到y坐标最小的点（图像坐标系中y向下增长，因此最小y值是最高点）
    min_y_index = np.argmin(y_indices)
    highest_x = x_indices[min_y_index]
    highest_y = y_indices[min_y_index]

    return (highest_x, highest_y)


def find_curve_points(curve_img_path):
    """找到曲线图像中的所有点"""
    # 使用PIL读取图像（支持中文路径）
    try:
        img = read_image_with_pil(curve_img_path)
    except Exception as e:
        raise FileNotFoundError(f"无法读取图像 {curve_img_path}: {str(e)}")

    # 找到所有值为1的像素点
    y_indices, x_indices = np.where(img == 1)

    if len(y_indices) == 0:
        # 如果没有找到值为1的像素点，尝试二值化图像
        _, img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
        y_indices, x_indices = np.where(img > 0)

    if len(y_indices) == 0:
        raise ValueError(f"在图像中没有找到曲线像素")

    # 返回所有曲线点的坐标
    curve_points = list(zip(x_indices, y_indices))

    # 按y坐标排序（从上到下）
    curve_points.sort(key=lambda p: p[1])

    return curve_points


def visualize_results(original_img_path, line1_points, outer_point, center_point, line2_angle, line3_angle, line1_eq,
                      line4_eq, use_line4_circle=False, circle_diameter=None, scale=None, ui_mode=False,
                      visibility_flags=None, override_center_point=None, override_outer_point=None,
                      show_highest_point=False, show_lowest_point=False, is_special_fallback=False,
                      center_color_override=None, semicircle_color_override=None, saved_curve_data=None,
                      fixed_semicircle_range=None):
    """可视化结果"""
    # 使用提供的 saved_curve_data 或从文件读取曲线数据，移除诊断打印
    
    # === 初始化可能未赋值的变量 ===
    line5_point1, line5_point2 = None, None
    line6_start_x, line6_start_y, line6_end_x, line6_end_y = None, None, None, None
    line8_point1, line8_point2 = None, None
    line9_eq = None
    line9_closest_point = None
    # === 结束初始化 ===

    # Default visibility if not provided
    if visibility_flags is None:
        visibility_flags = {
            'line1': True, 'line2': True, 'line3': True, 'line4': True, 'line5': True,
            'line6': True, 'line7': True, 'line8': True, 'line9': True, 'line9_closest_point': True,  # Add line9 flags
            'outer_point': True, 'center_point': True, 'half_circle': True,
            'curve1': True, 'curve2': True, 'curve3': True,  # Add curve3 flag
            'highest_point': True, 'lowest_point': True  # Add highest/lowest
        }

    # 读取原始图像
    img = read_image_with_pil(original_img_path)
    if img is None:
        raise ValueError(f"无法读取图像: {original_img_path}")

    # 将灰度图转换为彩色图
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # 读取并绘制曲线1
    curve1_img_path = None
    if visibility_flags.get('curve1', True):
        # 优先使用保存的曲线数据
        if saved_curve_data and 'curve1_points' in saved_curve_data:
            try:
                curve1_points_list = saved_curve_data['curve1_points']
                print(f"使用保存的曲线1数据: {len(curve1_points_list)} 个点")
                # 在原图上绘制曲线1点
                for point in curve1_points_list:
                    x, y = int(point[0]), int(point[1])
                    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
                        img[y, x] = (255, 255, 0)  # 用黄色绘制曲线1
            except Exception as e:
                print(f"使用保存的曲线1数据失败: {str(e)}")
        else:
            # 回退到从文件读取
            base_filename = os.path.basename(original_img_path)
            curve1_filename = base_filename.replace('.png', '_kjwy.png')
            curve1_img_path = os.path.join(FOLDER_B, curve1_filename)

            try:
                curve1_img = read_image_with_pil(curve1_img_path)
                if curve1_img is not None:
                    # 找到曲线上的所有点（像素值为1的点）
                    curve1_points = np.where(curve1_img == 1)
                    if len(curve1_points[0]) == 0:  # 如果没有找到值为1的点，尝试找白色点
                        curve1_points = np.where(curve1_img > 0)

                    # 在原图上绘制曲线1点
                    for y, x in zip(curve1_points[0], curve1_points[1]):
                        img[y, x] = (255, 255, 0)  # 用黄色绘制曲线1
            except Exception as e:
                print(f"警告：无法加载或绘制曲线1: {str(e)}")

    # 读取并绘制曲线2
    if visibility_flags.get('curve2', True):
        # 优先使用保存的曲线数据
        if saved_curve_data and 'curve2_points' in saved_curve_data:
            try:
                curve2_points_list = saved_curve_data['curve2_points']
                print(f"使用保存的曲线2数据: {len(curve2_points_list)} 个点")
                # 在原图上绘制曲线2点
                for point in curve2_points_list:
                    x, y = int(point[0]), int(point[1])
                    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
                        img[y, x] = (0, 255, 255)  # 用青色绘制曲线2
            except Exception as e:
                print(f"使用保存的曲线2数据失败: {str(e)}")
        else:
            # 回退到从文件读取
            base_filename = os.path.basename(original_img_path)
            curve2_filename = base_filename.replace('.png', '_bks.png')
            curve2_img_path = os.path.join(FOLDER_C4, curve2_filename)

            try:
                curve2_img = read_image_with_pil(curve2_img_path)
                if curve2_img is not None:
                    # 找到曲线上的所有点（像素值为1的点）
                    curve2_points = np.where(curve2_img == 1)
                    if len(curve2_points[0]) == 0:  # 如果没有找到值为1的点，尝试找白色点
                        curve2_points = np.where(curve2_img > 0)

                    # 在原图上绘制曲线2点
                    for y, x in zip(curve2_points[0], curve2_points[1]):
                        img[y, x] = (0, 255, 255)  # 用青色绘制曲线2
            except Exception as e:
                print(f"警告：无法加载或绘制曲线2: {str(e)}")

    # 读取并绘制曲线3 (新增)
    if visibility_flags.get('curve3', True):
        # 优先使用保存的曲线数据
        if saved_curve_data and 'curve3_points' in saved_curve_data:
            try:
                curve3_points_list = saved_curve_data['curve3_points']
                print(f"使用保存的曲线3数据: {len(curve3_points_list)} 个点")
                # 在原图上绘制曲线3点
                for point in curve3_points_list:
                    x, y = int(point[0]), int(point[1])
                    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
                        img[y, x] = (128, 0, 255)  # 洋红色 BGR: (128, 0, 255)
            except Exception as e:
                print(f"使用保存的曲线3数据失败: {str(e)}")
        else:
            # 回退到从文件读取
            if FOLDER_C3:
                base_filename = os.path.basename(original_img_path)
                curve3_filename = base_filename.replace('.png', '_bkx.png')  # 修改后缀为 _bkx.png
                curve3_img_path = os.path.join(FOLDER_C3, curve3_filename)

                try:
                    curve3_img = read_image_with_pil(curve3_img_path)
                    if curve3_img is not None:
                        curve3_points = np.where(curve3_img == 1)
                        if len(curve3_points[0]) == 0:
                            curve3_points = np.where(curve3_img > 0)

                        # 绘制曲线3 (使用洋红色)
                        for y, x in zip(curve3_points[0], curve3_points[1]):
                            img[y, x] = (128, 0, 255)  # 洋红色 BGR: (128, 0, 255)
                except Exception as e:
                    print(f"警告：无法加载或绘制曲线3: {str(e)}")

    # 获取图像尺寸
    height, width = img.shape[:2]

    # 计算线1的角度（相对于水平线）
    line1_angle = calculate_line_angle(line1_points[0], line1_points[1])
    line1_angle_deg = math.degrees(line1_angle)

    # 计算线6和线7的角度（相对于水平线）
    line6_angle_deg = math.degrees(line2_angle)
    line7_angle_deg = math.degrees(line3_angle)

    # 计算线6与线7的夹角
    angle67 = math.degrees((line3_angle - line2_angle + math.pi) % (2 * math.pi) - math.pi)

    # 从txt文件读取线4坐标
    txt_filename = os.path.basename(original_img_path).replace('.png', '.txt')
    txt_path = os.path.join(FOLDER_C, txt_filename)
    points = read_points_from_txt(txt_path)

    # 计算原始圆的直径
    original_diameter = 0
    if use_line4_circle and points:
        # 使用与线4相切的圆，使用TXT文件中的点重新计算线4方程
        line4_points = points[6:8]  # 第7、8行的点为线4的端点

        # 计算线4的方程参数 ax + by + c = 0
        a4 = line4_points[1][1] - line4_points[0][1]
        b4 = line4_points[0][0] - line4_points[1][0]
        c4 = line4_points[1][0] * line4_points[0][1] - line4_points[0][0] * line4_points[1][1]

        # 计算中心点到线4的距离作为半径
        radius = abs(a4 * center_point[0] + b4 * center_point[1] + c4) / math.sqrt(a4 * a4 + b4 * b4)
        original_diameter = radius * 2
    else:
        # 使用与线5相切的圆
        a1, b1, c1 = line1_eq
        # 计算过外沿点的平行于线1的直线方程（线5）
        c5 = -a1 * outer_point[0] - b1 * outer_point[1]
        # 计算中心点到线5的距离作为半径
        radius = abs(a1 * center_point[0] + b1 * center_point[1] + c5) / math.sqrt(a1 * a1 + b1 * b1)
        original_diameter = radius * 2

    # 计算标准化直径和半径（如果提供了circle_diameter和scale）
    standard_diameter = original_diameter
    standard_radius = standard_diameter / 2

    # --- Use override center point if provided for display ---
    display_center_point = override_center_point if override_center_point is not None else center_point
    # --- End Use override center point ---

    # 对于普通方案，如果提供了circle_diameter，使用它来计算标准直径
    if circle_diameter is not None and scale is not None:
        actual_diameter = circle_diameter * scale
        safe_even_diameter = None

        # 计算安全的标准偶数直径
        curve2_filename = os.path.basename(original_img_path).replace('.png', '') + '_bks.png'
        curve2_img_path = os.path.join(FOLDER_C4, curve2_filename)
        curve3_img_path = None
        if FOLDER_C3:
            curve3_filename = os.path.basename(original_img_path).replace('.png', '') + '_bkx.png'
            curve3_img_path = os.path.join(FOLDER_C3, curve3_filename)
        # Use the original center_point for safety calculation, display_center for distance print
        safe_even_diameter = round_to_safe_even_diameter(center_point, actual_diameter, curve2_img_path, scale, curve3_img_path=curve3_img_path)

        if safe_even_diameter:
            # 将标准偶数直径转换回像素尺度
            standard_diameter = safe_even_diameter / scale
            standard_radius = standard_diameter / 2

            min_distance = calculate_min_distance_circle_to_curve_thread_safe(display_center_point, standard_radius,
                                                                              curve2_img_path, {}, None, None)
            if min_distance is not None:
                print(f"圆到曲线2的最小距离: {min_distance:.2f}像素, {min_distance * scale:.2f}mm")

    # 定义颜色（BGR格式）
    RED = (0, 0, 255)  # 线1颜色
    BLUE = (255, 0, 0)  # 外沿点颜色
    GREEN = (0, 255, 0)  # 中心点和圆的颜色
    ORANGE = (0, 165, 255)  # 线6颜色
    PURPLE = (255, 0, 255)  # 线7颜色
    YELLOW = (0, 255, 255)  # 线2颜色
    CYAN = (255, 255, 0)  # 线3颜色
    BROWN = (42, 42, 165)  # 线4颜色
    WHITE = (255, 255, 255)  # 线5颜色
    PINK = (147, 20, 255)  # 线8颜色
    SKY_BLUE = (235, 206, 135)  # 最高点颜色
    GOLD = (0, 215, 255)  # 最低点颜色
    MAGENTA = (255, 0, 128)  # 洋红色 (BGR格式)
    # GRAY = (128, 128, 128) # 灰色，用于线9
    # DARK_RED = (0, 0, 139) # 暗红色，用于线9交点

    # 绘制线1
    if visibility_flags.get('line1', True):
        cv2.line(img, (int(line1_points[0][0]), int(line1_points[0][1])),
                 (int(line1_points[1][0]), int(line1_points[1][1])), RED, 2)

    # 绘制外沿点
    if visibility_flags.get('outer_point', True):
        if override_outer_point is not None:
            cv2.circle(img, (int(override_outer_point[0]), int(override_outer_point[1])), 5, BLUE, -1)
        else:
            cv2.circle(img, (int(outer_point[0]), int(outer_point[1])), 5, BLUE, -1)

    # 绘制中心点 (Use display_center_point)
    # Use center_color_override if provided, otherwise default GREEN
    effective_center_color = (
        center_color_override
        if center_color_override is not None
        else GREEN
    )

    if visibility_flags.get('center_point', True):
        cx = int(display_center_point[0])
        cy = int(display_center_point[1])

        # Dark outer ring for contrast
        cv2.circle(
            img,
            (cx, cy),
            7,
            (0, 0, 0),
            3,
            cv2.LINE_AA
        )

        # Green inner ring
        cv2.circle(
            img,
            (cx, cy),
            5,
            effective_center_color,
            2,
            cv2.LINE_AA
        )

        # Small centre dot
        cv2.circle(
            img,
            (cx, cy),
            2,
            effective_center_color,
            -1,
            cv2.LINE_AA
        )

    # 绘制线6和线7
    # Use display_center_point for line start
    x1 = display_center_point[0]
    y1 = display_center_point[1]

    # 对于普通方案，线6作为半圆的直径
    line6_length = standard_diameter
    line6_half_length = line6_length / 2
    line6_start_x = x1 - line6_half_length * math.cos(line2_angle)
    line6_start_y = y1 - line6_half_length * math.sin(line2_angle)
    line6_end_x = x1 + line6_half_length * math.cos(line2_angle)
    line6_end_y = y1 + line6_half_length * math.sin(line2_angle)
    if visibility_flags.get('line6', True):
        cv2.line(img, (int(line6_start_x), int(line6_start_y)),
                 (int(line6_end_x), int(line6_end_y)), ORANGE, 2)

    # 线7 (Starts from display_center_point)
    if visibility_flags.get('line7', True):
        x3 = x1 + 200 * math.cos(line3_angle)
        y3 = y1 + 200 * math.sin(line3_angle)
        cv2.line(img, (int(x1), int(y1)), (int(x3), int(y3)), PURPLE, 2)

    # 绘制以线6为直径的上半圆 (Centered at display_center_point)
    if visibility_flags.get('half_circle', True):
        # 普通方案的半圆绘制逻辑
        line6_vector_x = line6_end_x - line6_start_x
        line6_vector_y = line6_end_y - line6_start_y

        # --- 确定半圆开口方向 ---
        # 计算线6的方向角 (弧度)
        line6_rad = math.atan2(line6_vector_y, line6_vector_x)
        
        # 确定绘制角度范围
        line6_angle_unit_circle = math.degrees(line6_rad)
        
        # 如果提供了固定的半圆绘制范围，则使用固定范围，否则使用点积判断
        if fixed_semicircle_range is not None:
            start_angle_rad, end_angle_rad = fixed_semicircle_range
            # 将弧度转换为度数
            start_angle = math.degrees(start_angle_rad)
            end_angle = math.degrees(end_angle_rad)
        else:
            # 计算线6法向量（指向其中一个半圆），旋转+90度: (dx, dy) -> (-dy, dx)
            perp_dx = -line6_vector_y
            perp_dy = line6_vector_x
            # 计算中心点到外沿点的向量
            outer_vec_x = outer_point[0] - display_center_point[0]
            outer_vec_y = outer_point[1] - display_center_point[1]
            # 计算点积，判断外沿点在法向量的哪一侧
            dot_product = outer_vec_x * perp_dx + outer_vec_y * perp_dy

            if dot_product >= 0:  # 外沿点在法向量指向的一侧，绘制0-180度
                start_angle = 0
                end_angle = 180
            else:  # 外沿点在法向量的反方向一侧，绘制180-360度（或-180到0）
                start_angle = 180
                end_angle = 360

        # Use semicircle_color_override if provided, otherwise default GREEN
        effective_semicircle_color = (
            semicircle_color_override
            if semicircle_color_override is not None
            else GREEN
        )

        cup_center = (
            int(display_center_point[0]),
            int(display_center_point[1])
        )

        cup_radius = (
            int(standard_radius),
            int(standard_radius)
        )

        # ============================================================
        # 1. Semi-transparent fill for the planned acetabular cup
        # ============================================================

        overlay = img.copy()

        cv2.ellipse(
            overlay,
            cup_center,
            cup_radius,
            line6_angle_unit_circle,
            start_angle,
            end_angle,
            effective_semicircle_color,
            -1,  # -1 means filled
            cv2.LINE_AA
        )

        # Transparency of the cup fill
        # 0.20 = 20% colour + 80% original radiograph
        fill_alpha = 0.20

        img = cv2.addWeighted(
            overlay,
            fill_alpha,
            img,
            1.0 - fill_alpha,
            0
        )

        # ============================================================
        # 2. Dark outer halo to improve contrast
        # ============================================================

        cv2.ellipse(
            img,
            cup_center,
            cup_radius,
            line6_angle_unit_circle,
            start_angle,
            end_angle,
            (0, 0, 0),
            9,
            cv2.LINE_AA
        )

        # ============================================================
        # 3. Bright planned-cup contour
        # ============================================================

        cv2.ellipse(
            img,
            cup_center,
            cup_radius,
            line6_angle_unit_circle,
            start_angle,
            end_angle,
            effective_semicircle_color,
            5,
            cv2.LINE_AA
        )

        # 2. Bright planned-cup contour
        cv2.ellipse(
            img,
            cup_center,
            cup_radius,
            line6_angle_unit_circle,
            start_angle,
            end_angle,
            effective_semicircle_color,
            5,  # green/red inner width
            cv2.LINE_AA
        )

    # 标记曲线的最高点和最低点
    if (show_highest_point or show_lowest_point) and curve1_img_path:
        try:
            # 获取曲线最高点
            if show_highest_point:
                highest_point = find_highest_point(curve1_img_path)
                if highest_point:
                    cv2.circle(img, (int(highest_point[0]), int(highest_point[1])), 7, SKY_BLUE, -1)
                    if not ui_mode:
                        # 将图像转换为PIL格式添加标签
                        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                        draw = ImageDraw.Draw(img_pil)
                        try:
                            font = ImageFont.truetype("simhei.ttf", 16)
                        except:
                            try:
                                font = ImageFont.truetype("simsun.ttc", 16)
                            except:
                                font = ImageFont.load_default()
                        draw.text((int(highest_point[0]) + 10, int(highest_point[1]) - 10),
                                  "最高点", font=font, fill=(135, 206, 235))
                        img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

            # 获取曲线最低点
            if show_lowest_point:
                lowest_point = find_lowest_point(curve1_img_path)
                if lowest_point:
                    cv2.circle(img, (int(lowest_point[0]), int(lowest_point[1])), 7, GOLD, -1)
                    if not ui_mode:
                        # 将图像转换为PIL格式添加标签
                        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                        draw = ImageDraw.Draw(img_pil)
                        try:
                            font = ImageFont.truetype("simhei.ttf", 16)
                        except:
                            try:
                                font = ImageFont.truetype("simsun.ttc", 16)
                            except:
                                font = ImageFont.load_default()
                        draw.text((int(lowest_point[0]) + 10, int(lowest_point[1]) - 10),
                                  "最低点", font=font, fill=(255, 215, 0))
                        img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"标记最高/最低点时出错: {str(e)}")

    # # --- 绘制线9 ---
    # lowest_point_for_line9 = None # Variable to store the calculated lowest point
    # if visibility_flags.get('line9', True) or visibility_flags.get('line9_closest_point', True):
    #     if curve1_img_path and os.path.exists(curve1_img_path):
    #         try:
    #             lowest_point_for_line9 = find_lowest_point(curve1_img_path)
    #         except Exception as e:
    #             print(f"查找最低点以计算线9时出错: {str(e)}")
    #
    #     if lowest_point_for_line9 and line1_eq and scale is not None and scale > 0:
    #         lx, ly = lowest_point_for_line9
    #         a1, b1, c1 = line1_eq
    #         norm_sq = a1**2 + b1**2
    #
    #         if norm_sq > 1e-10: # Avoid division by zero if line1 points are coincident
    #             norm = math.sqrt(norm_sq)
    #             pixel_distance = 20 / scale
    #             # Ensure minimum visual distance
    #             pixel_distance = max(5, pixel_distance)
    #
    #             # Calculate candidate c9 values
    #             val_lowest = a1 * lx + b1 * ly
    #             offset = pixel_distance * norm
    #             c9_candidate1 = -val_lowest - offset
    #             c9_candidate2 = -val_lowest + offset
    #
    #             # Determine which line is below (larger y in image coordinates)
    #             line9_eq = None
    #             if abs(b1) > 1e-10: # Check if line1 is not vertical
    #                 y_line1 = (-a1 * lx - c9_candidate1) / b1
    #                 y_line2 = (-a1 * lx - c9_candidate2) / b1
    #                 if y_line1 > ly:
    #                     line9_eq = (a1, b1, c9_candidate1)
    #                 elif y_line2 > ly:
    #                     line9_eq = (a1, b1, c9_candidate2)
    #                 else:
    #                      # If neither is strictly below, pick the one further away in the expected direction
    #                      # This might happen if lowest point is right on the line, use the offset sign logic
    #                      normal_points_down = b1 > 0 # Heuristic: if b1 > 0, normal points down
    #                      if normal_points_down:
    #                          line9_eq = (a1, b1, c9_candidate1) # Should correspond to -offset
    #                      else:
    #                          line9_eq = (a1, b1, c9_candidate2) # Should correspond to +offset
    #             elif abs(a1) > 1e-10: # Handle vertical line1
    #                 x_line1 = -c9_candidate1 / a1
    #                 x_line2 = -c9_candidate2 / a1
    #                 # Determine which line is "below" for a vertical line (arbitrarily choose one side, e.g., larger x)
    #                 if x_line1 > lx:
    #                      line9_eq = (a1, b1, c9_candidate1)
    #                 else:
    #                      line9_eq = (a1, b1, c9_candidate2)
    #
    #             # Draw line9 if equation found
    #             if line9_eq and visibility_flags.get('line9', True):
    #                 # Calculate endpoints for drawing (extend across image width)
    #                 if abs(b1) > 1e-10:
    #                     y_start = (-a1 * 0 - line9_eq[2]) / b1
    #                     y_end = (-a1 * (width - 1) - line9_eq[2]) / b1
    #                     cv2.line(img, (0, int(y_start)), (width - 1, int(y_end)), GRAY, 2)
    #                 elif abs(a1) > 1e-10: # Vertical line
    #                     x_line = int(-line9_eq[2] / a1)
    #                     cv2.line(img, (x_line, 0), (x_line, height - 1), GRAY, 2)
    #
    #             # Calculate and draw closest point on line9 to lowest_point
    #             if line9_eq and visibility_flags.get('line9_closest_point', True):
    #                 a9, b9, c9 = line9_eq
    #                 # Closest point calculation using formula derived earlier
    #                 denom = a9**2 + b9**2
    #                 closest_x = (-a9*c9 + b9**2*lx - a9*b9*ly) / denom
    #                 closest_y = (-b9*c9 - a9*b9*lx + a9**2*ly) / denom
    #                 closest_point_on_line9 = (int(closest_x), int(closest_y))
    #                 cv2.circle(img, closest_point_on_line9, 5, DARK_RED, -1)
    #
    #                 # 添加线9最近点标签 (如果不在UI模式下)
    #                 if not ui_mode:
    #                     img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    #                     draw = ImageDraw.Draw(img_pil)
    #                     try:
    #                         font = ImageFont.truetype("simhei.ttf", 16)
    #                     except:
    #                         try:
    #                             font = ImageFont.truetype("simsun.ttc", 16)
    #                         except:
    #                             font = ImageFont.load_default()
    #                     draw.text((closest_point_on_line9[0] + 10, closest_point_on_line9[1] - 10),
    #                               "最近点", font=font, fill=(139, 0, 0))
    #                     img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    # # --- End 绘制线9 ---

    # 确定绘制角度范围
    if visibility_flags.get('half_circle', True):
        line6_angle_unit_circle = math.degrees(line6_rad)

    # 从txt文件中读取的点坐标绘制线2、线3、线4、线8
    if points:
        # 线2
        if visibility_flags.get('line2', True):
            cv2.line(img, (int(points[2][0]), int(points[2][1])),
                     (int(points[3][0]), int(points[3][1])), YELLOW, 2)
        # 线3
        if visibility_flags.get('line3', True):
            cv2.line(img, (int(points[4][0]), int(points[4][1])),
                     (int(points[5][0]), int(points[5][1])), CYAN, 2)
        # 线4
        if visibility_flags.get('line4', True):
            cv2.line(img, (int(points[6][0]), int(points[6][1])),
                     (int(points[7][0]), int(points[7][1])), BROWN, 2)

        # 计算线8的端点
        line8_point1 = ((points[2][0] + points[3][0]) / 2, (points[2][1] + points[3][1]) / 2)
        line8_point2 = ((points[4][0] + points[5][0]) / 2, (points[4][1] + points[5][1]) / 2)
        # 绘制线8
        if visibility_flags.get('line8', True):
            cv2.line(img, (int(line8_point1[0]), int(line8_point1[1])),
                     (int(line8_point2[0]), int(line8_point2[1])), PINK, 2)

    # 绘制线5
    if visibility_flags.get('line5', True):
        line1_vector = (line1_points[1][0] - line1_points[0][0], line1_points[1][1] - line1_points[0][1])
        line1_length = math.sqrt(line1_vector[0] ** 2 + line1_vector[1] ** 2)
        if line1_length > 0:  # Avoid division by zero
            line1_unit_vector = (line1_vector[0] / line1_length, line1_vector[1] / line1_length)
            line5_length = 300
            line5_point1 = (outer_point[0] - line5_length * line1_unit_vector[0],
                            outer_point[1] - line5_length * line1_unit_vector[1])
            line5_point2 = (outer_point[0] + line5_length * line1_unit_vector[0],
                            outer_point[1] + line5_length * line1_unit_vector[1])
            cv2.line(img, (int(line5_point1[0]), int(line5_point1[1])),
                     (int(line5_point2[0]), int(line5_point2[1])), WHITE, 2)

        # === Conditional Text Drawing Start ===
        if not ui_mode:
            img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)
            try:
                font = ImageFont.truetype("simhei.ttf", 16)
            except IOError:
                try:
                    font = ImageFont.truetype("simsun.ttc", 16)
                except IOError:
                    font = ImageFont.load_default()

            # --- All text drawing moved inside this block ---

            # 添加线5的标签
            if visibility_flags.get('line5', True) and line5_point1 and line5_point2:
                line5_mid_x = (line5_point1[0] + line5_point2[0]) // 2
                line5_mid_y = (line5_point1[1] + line5_point2[1]) // 2
                draw.text((line5_mid_x, line5_mid_y - 20), "线5", font=font, fill=(255, 255, 255))

            # 添加点的标签
            if visibility_flags.get('outer_point', True):
                effective_outer_point = override_outer_point if override_outer_point is not None else outer_point
                if effective_outer_point:
                    draw.text((int(effective_outer_point[0]) + 10, int(effective_outer_point[1]) - 10),
                              "外沿点", font=font, fill=(255, 0, 0))

            if visibility_flags.get('center_point', True):
                if display_center_point:  # Use the potentially overridden center point for label
                    draw.text((int(display_center_point[0]) + 10, int(display_center_point[1]) - 10),
                              "中心点", font=font, fill=(0, 255, 0))

            # Convert back to OpenCV format (still inside if not ui_mode)
            img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    # === Conditional Text Drawing End ===

    return img


def read_points_from_txt(txt_path):
    """从txt文件中读取所有点的坐标"""
    try:
        # 尝试以UTF-8编码读取文件
        with open(txt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            # 如果UTF-8失败，尝试以GBK编码读取
            with open(txt_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"无法读取文件 {txt_path}: {str(e)}")
            return None
    except FileNotFoundError:
        print(f"找不到文件: {txt_path}")
        return None
    except Exception as e:
        print(f"读取文件时出错 {txt_path}: {str(e)}")
        return None

    try:
        # 处理文件内容
        points = []
        for line in lines:
            # 去除空白字符并分割坐标
            coords = line.strip().split(',')
            if len(coords) >= 2:  # 确保有足够的坐标值
                try:
                    x = float(coords[0])
                    y = float(coords[1])
                    points.append((x, y))
                except ValueError as e:
                    print(f"无法转换坐标值: {line.strip()}")
                    continue

        if len(points) < 8:  # 确保至少有8个点
            print(f"文件中点的数量不足（需要至少8个点）: {txt_path}")
            return None

        # 规范化各线段端点顺序（线1、线2、线3、线4）：保证左点在前；若x相等则y小的在前
        try:
            for i in (0, 2, 4, 6):
                p1, p2 = points[i], points[i + 1]
                if (p1[0] > p2[0]) or (p1[0] == p2[0] and p1[1] > p2[1]):
                    points[i], points[i + 1] = p2, p1
        except Exception:
            # 若出现异常（如索引问题），保持原有顺序，不影响后续流程
            pass

        return points

    except Exception as e:
        print(f"处理文件内容时出错 {txt_path}: {str(e)}")
        return None


def calculate_distance_to_line(point1, point2, point3):
    """
    计算点1到点2和点3形成的直线的垂直距离
    :param point1: 点1的坐标，格式为 (x, y)
    :param point2: 点2的坐标，格式为 (x, y)
    :param point3: 点3的坐标，格式为 (x, y)
    :return: 点1到线的垂直距离
    """
    try:
        # 检查输入点是否有效
        if any(p is None for p in [point1, point2, point3]):
            print(f"警告: 输入点包含空值: point1={point1}, point2={point2}, point3={point3}")
            return 0

        # 转换为 numpy 数组
        p1 = np.array(point1)
        p2 = np.array(point2)
        p3 = np.array(point3)

        # 计算点到线的距离公式
        # 距离 = |(p3 - p2) x (p2 - p1)| / |p3 - p2|
        line_vector = p3 - p2  # 线的方向向量
        point_vector = p1 - p2  # 点到线起点的向量
        cross_product = np.linalg.norm(np.cross(line_vector, point_vector))  # 向量叉乘的模
        line_length = np.linalg.norm(line_vector)  # 线段的长度

        # 添加除零保护
        if line_length < 1e-10:  # 如果线段长度接近零
            print(f"警告: 线段长度接近零，可能导致除零错误。点坐标: {point2}, {point3}")
            return 0  # 返回零或一个默认值

        distance = cross_product / line_length
        return float(distance)  # 确保返回Python float类型

    except Exception as e:
        print(f"计算距离时出错: {str(e)}")
        print(f"输入点坐标: point1={point1}, point2={point2}, point3={point3}")
        return 0  # 发生错误时返回0


# 从原文件导入所有必要的函数
# GPU内存池优化
_gpu_tensor_cache = {
    'pi': None,
    'two_pi': None,
    'device': None
}

def _get_cached_constants(device):
    """获取缓存的GPU常量张量"""
    global _gpu_tensor_cache
    
    if _gpu_tensor_cache['device'] != device or _gpu_tensor_cache['pi'] is None:
        _gpu_tensor_cache['pi'] = torch.tensor(math.pi, dtype=torch.float32, device=device)
        _gpu_tensor_cache['two_pi'] = 2 * _gpu_tensor_cache['pi']
        _gpu_tensor_cache['device'] = device
    
    return _gpu_tensor_cache['pi'], _gpu_tensor_cache['two_pi']

def find_center_point_gpu(line1_points, outer_point, angle1_deg=40, angle2_deg=36, device=None):
    """
    高度优化的GPU版本中心点计算函数
    使用内存池、常量缓存和向量化操作提高性能
    """
    if device is None or not TORCH_AVAILABLE:
        # 回退到CPU版本
        return find_center_point_cpu(line1_points, outer_point, angle1_deg, angle2_deg)
    
    try:
        # 使用no_grad上下文减少内存开销
        with torch.no_grad():
            # 转换输入数据为PyTorch张量（复用内存）
            line1_tensor = torch.tensor(line1_points, dtype=torch.float32, device=device)
            outer_tensor = torch.tensor(outer_point, dtype=torch.float32, device=device)
            
            # 获取缓存的常量
            pi, two_pi = _get_cached_constants(device)
            
            # 预计算角度（避免重复计算）
            angle1_rad = torch.tensor(math.radians(angle1_deg), dtype=torch.float32, device=device)
            angle2_rad = torch.tensor(math.radians(angle2_deg), dtype=torch.float32, device=device)
        
        # 计算线1的角度和中点
        delta = line1_tensor[1] - line1_tensor[0]
        line1_angle = torch.atan2(delta[1], delta[0])
        line1_midpoint = torch.mean(line1_tensor, dim=0)
        
        # 判断外沿点在图像的哪一侧
        is_outer_point_left = outer_tensor[0] < line1_midpoint[0]
        
        # 计算线2和线3的角度
        line2_angle = line1_angle + angle1_rad
        if is_outer_point_left:
            line3_angle = line2_angle + angle2_rad
        else:
            line3_angle = line2_angle - angle2_rad
        
        # 标准化角度到[-π, π]范围内
        line2_angle_norm = torch.remainder(line2_angle + pi, two_pi) - pi
        line3_angle_norm = torch.remainder(line3_angle + pi, two_pi) - pi
        
        # 验证角度条件（在GPU上进行）
        if is_outer_point_left:
            condition1 = line2_angle_norm < line3_angle_norm
            if not condition1.item():
                return [], None, None, None, None
        else:
            condition1 = line2_angle_norm > line3_angle_norm
            if not condition1.item():
                return [], None, None, None, None
        
        # 计算线1的直线方程: ax + by + c = 0
        a1 = line1_tensor[1, 1] - line1_tensor[0, 1]
        b1 = line1_tensor[0, 0] - line1_tensor[1, 0]
        c1 = line1_tensor[1, 0] * line1_tensor[0, 1] - line1_tensor[0, 0] * line1_tensor[1, 1]
        
        # 计算过外延点的平行于线1的直线方程
        c4 = -a1 * outer_tensor[0] - b1 * outer_tensor[1]
        
        # 计算反向角度和线1长度
        reverse_angle = torch.remainder(line3_angle + pi, two_pi)
        line1_length = torch.norm(delta)
        
        # 批量计算所有候选点（向量化操作）
        # 双方向 + 提升采样密度/范围，增强“在线1与线4之间”命中概率
        max_tries = 200
        i_range = torch.arange(1, max_tries + 1, dtype=torch.float32, device=device)
        dist_multipliers = i_range / max_tries * 3.0
        distances_pos = line1_length * dist_multipliers
        distances_neg = -distances_pos
        distances_all = torch.cat([distances_pos, distances_neg])
        
        # 批量计算所有候选中心点
        cos_angle = torch.cos(reverse_angle)
        sin_angle = torch.sin(reverse_angle)
        
        center_x_batch = outer_tensor[0] + distances_all * cos_angle
        center_y_batch = outer_tensor[1] + distances_all * sin_angle
        
        # 批量检查点是否在线1和线4之间
        val1_batch = a1 * center_x_batch + b1 * center_y_batch + c1
        val4_batch = a1 * center_x_batch + b1 * center_y_batch + c4
        
        # 找到符号相反的点（在线1和线4之间）
        valid_mask = torch.sign(val1_batch) != torch.sign(val4_batch)
        
        # 提取有效的中心点
        if valid_mask.any():
            valid_x = center_x_batch[valid_mask]
            valid_y = center_y_batch[valid_mask]
            
            # 一次性转换所有有效点到CPU
            center_points = list(zip(valid_x.cpu().numpy(), valid_y.cpu().numpy()))
            
            # 转换其他结果到CPU
            line2_angle_cpu = float(line2_angle.item())
            line3_angle_cpu = float(line3_angle.item())
            line1_eq_cpu = (float(a1.item()), float(b1.item()), float(c1.item()))
            line4_eq_cpu = (float(a1.item()), float(b1.item()), float(c4.item()))
            
            return center_points, line2_angle_cpu, line3_angle_cpu, line1_eq_cpu, line4_eq_cpu
        else:
            return [], None, None, None, None
            
    except Exception as e:
        # 如果GPU计算出错，回退到CPU版本
        print(f"GPU计算出错，回退到CPU: {e}")
        return find_center_point_cpu(line1_points, outer_point, angle1_deg, angle2_deg)

def find_center_point_gpu_batch(line1_points, outer_point, angle1_deg=40, angle2_deg_list=None, device=None):
    """
    GPU批量角度版本的中心点计算：对多个angle2一次性计算候选中心点集合。

    Returns:
        (centers_by_angle, line2_angle_cpu, line3_angles_cpu, line1_eq_cpu, line4_eq_cpu)
        - centers_by_angle: list[list[tuple]]，每个angle2的中心点列表
        - line2_angle_cpu: float（弧度）
        - line3_angles_cpu: list[float]（每个angle2对应的弧度）
        - line1_eq_cpu: (a1,b1,c1)
        - line4_eq_cpu: (a1,b1,c4)
    """
    if device is None or not TORCH_AVAILABLE or angle2_deg_list is None or len(angle2_deg_list) == 0:
        # 回退：逐角度CPU
        centers_by_angle = []
        l2 = None
        l1eq = None
        l4eq = None
        for a2 in angle2_deg_list or []:
            cps, l2, l3, l1eq, l4eq = find_center_point_cpu(line1_points, outer_point, angle1_deg, a2)
            centers_by_angle.append(cps)
        # CPU模式下，line3角度列表逐一计算
        line3_angles_cpu = []
        for a2 in angle2_deg_list or []:
            _, _, l3, _, _ = find_center_point_cpu(line1_points, outer_point, angle1_deg, a2)
            line3_angles_cpu.append(l3)
        return centers_by_angle, l2, line3_angles_cpu, l1eq, l4eq

    try:
        with torch.no_grad():
            line1_tensor = torch.tensor(line1_points, dtype=torch.float32, device=device)
            outer_tensor = torch.tensor(outer_point, dtype=torch.float32, device=device)
            pi, two_pi = _get_cached_constants(device)
            angle1_rad = torch.tensor(math.radians(angle1_deg), dtype=torch.float32, device=device)
            angle2_rad_vec = torch.tensor([math.radians(v) for v in angle2_deg_list], dtype=torch.float32, device=device)  # [K]

        delta = line1_tensor[1] - line1_tensor[0]
        line1_angle = torch.atan2(delta[1], delta[0])
        line1_midpoint = torch.mean(line1_tensor, dim=0)
        is_outer_point_left = outer_tensor[0] < line1_midpoint[0]

        line2_angle = line1_angle + angle1_rad  # 常量
        if is_outer_point_left:
            line3_angle_vec = line2_angle + angle2_rad_vec
        else:
            line3_angle_vec = line2_angle - angle2_rad_vec

        line2_angle_norm = torch.remainder(line2_angle + pi, two_pi) - pi  # 标量
        line3_angle_norm_vec = torch.remainder(line3_angle_vec + pi, two_pi) - pi  # [K]

        if is_outer_point_left:
            cond1 = line2_angle_norm < line3_angle_norm_vec
            cond2 = torch.abs(line2_angle_norm) > torch.abs(line3_angle_norm_vec)
            angle_ok_vec = cond1 & cond2
        else:
            cond1 = line2_angle_norm > line3_angle_norm_vec
            cond2 = torch.abs(line2_angle_norm) < torch.abs(line3_angle_norm_vec)
            angle_ok_vec = cond1 & cond2

        a1 = line1_tensor[1, 1] - line1_tensor[0, 1]
        b1 = line1_tensor[0, 0] - line1_tensor[1, 0]
        c1 = line1_tensor[1, 0] * line1_tensor[0, 1] - line1_tensor[0, 0] * line1_tensor[1, 1]
        c4 = -a1 * outer_tensor[0] - b1 * outer_tensor[1]
        line1_length = torch.norm(delta)

        max_tries = 100
        i_range = torch.arange(1, max_tries + 1, dtype=torch.float32, device=device)  # [M]
        dist_multipliers = i_range / max_tries * 2
        distances = line1_length * dist_multipliers

        # 注意：寻找中心点需要沿线7的反向方向从外沿点回溯
        reverse_angle_vec = torch.remainder(line3_angle_vec + pi, two_pi)  # [K]
        cos_vec = torch.cos(reverse_angle_vec)  # [K]
        sin_vec = torch.sin(reverse_angle_vec)  # [K]

        center_x = outer_tensor[0] + distances.unsqueeze(0) * cos_vec.unsqueeze(1)
        center_y = outer_tensor[1] + distances.unsqueeze(0) * sin_vec.unsqueeze(1)

        val1 = a1 * center_x + b1 * center_y + c1
        val4 = a1 * center_x + b1 * center_y + c4
        between_mask = torch.sign(val1) != torch.sign(val4)  # [K,M]

        centers_by_angle = []
        line3_angles_cpu = []
        for k in range(len(angle2_deg_list)):
            line3_angles_cpu.append(float(line3_angle_vec[k].item()))
            if not angle_ok_vec[k].item():
                centers_by_angle.append([])
                continue
            mk = between_mask[k]
            if mk.any():
                vx = center_x[k][mk].cpu().numpy()
                vy = center_y[k][mk].cpu().numpy()
                centers_by_angle.append(list(zip(vx, vy)))
            else:
                centers_by_angle.append([])

        line2_angle_cpu = float(line2_angle.item())
        line1_eq_cpu = (float(a1.item()), float(b1.item()), float(c1.item()))
        line4_eq_cpu = (float(a1.item()), float(b1.item()), float(c4.item()))

        return centers_by_angle, line2_angle_cpu, line3_angles_cpu, line1_eq_cpu, line4_eq_cpu
    except Exception as e:
        print(f"GPU批量计算出错，回退到CPU: {e}")
        centers_by_angle = []
        l2 = None
        l1eq = None
        l4eq = None
        line3_angles_cpu = []
        for a2 in angle2_deg_list or []:
            cps, l2, l3, l1eq, l4eq = find_center_point_cpu(line1_points, outer_point, angle1_deg, a2)
            centers_by_angle.append(cps)
            line3_angles_cpu.append(l3)
        return centers_by_angle, l2, line3_angles_cpu, l1eq, l4eq


def verify_gpu_cpu_consistency(line1_points, outer_point, angle1_deg=40, angle2_deg=36, tolerance=1e-3):
    """
    验证GPU和CPU计算结果的一致性
    
    Args:
        line1_points: 线1的两个端点
        outer_point: 外沿点
        angle1_deg: 角度1（度）
        angle2_deg: 角度2（度）
        tolerance: 数值容差
    
    Returns:
        bool: 结果是否一致
        dict: 详细的比较信息
    """
    if not (TORCH_AVAILABLE and torch.cuda.is_available()):
        return False, {"error": "GPU不可用，无法进行一致性验证"}
    
    try:
        # CPU计算
        cpu_result = find_center_point_cpu(line1_points, outer_point, angle1_deg, angle2_deg)
        
        # GPU计算
        device = torch.device('cuda')
        gpu_result = find_center_point_gpu(line1_points, outer_point, angle1_deg, angle2_deg, device)
        
        if cpu_result is None or gpu_result is None:
            return False, {"error": "其中一个计算返回None"}
        
        if len(cpu_result) != len(gpu_result):
            return False, {"error": "返回结果长度不一致"}
        
        # 比较中心点列表
        cpu_centers, cpu_line2_angle, cpu_line3_angle, cpu_line1_eq, cpu_line4_eq = cpu_result
        gpu_centers, gpu_line2_angle, gpu_line3_angle, gpu_line1_eq, gpu_line4_eq = gpu_result
        
        comparison = {
            "centers_match": len(cpu_centers) == len(gpu_centers),
            "line2_angle_diff": abs(cpu_line2_angle - gpu_line2_angle) if cpu_line2_angle is not None and gpu_line2_angle is not None else None,
            "line3_angle_diff": abs(cpu_line3_angle - gpu_line3_angle) if cpu_line3_angle is not None and gpu_line3_angle is not None else None,
            "line1_eq_diff": [abs(cpu_line1_eq[i] - gpu_line1_eq[i]) for i in range(len(cpu_line1_eq))] if cpu_line1_eq and gpu_line1_eq else None,
            "line4_eq_diff": [abs(cpu_line4_eq[i] - gpu_line4_eq[i]) for i in range(len(cpu_line4_eq))] if cpu_line4_eq and gpu_line4_eq else None
        }
        
        # 检查中心点坐标差异
        if comparison["centers_match"]:
            center_diffs = []
            for i in range(len(cpu_centers)):
                diff_x = abs(cpu_centers[i][0] - gpu_centers[i][0])
                diff_y = abs(cpu_centers[i][1] - gpu_centers[i][1])
                center_diffs.append((diff_x, diff_y))
            comparison["center_diffs"] = center_diffs
        
        # 判断是否一致
        is_consistent = True
        if comparison["line2_angle_diff"] and comparison["line2_angle_diff"] > tolerance:
            is_consistent = False
        if comparison["line3_angle_diff"] and comparison["line3_angle_diff"] > tolerance:
            is_consistent = False
        if comparison["center_diffs"]:
            for diff_x, diff_y in comparison["center_diffs"]:
                if diff_x > tolerance or diff_y > tolerance:
                    is_consistent = False
                    break
        
        return is_consistent, comparison
        
    except Exception as e:
        return False, {"error": f"验证过程中出现异常: {str(e)}"}


# GPU性能优化：减少设备初始化开销
_gpu_device_cache = None
_gpu_warmup_done = False
_GPU_SELFTEST_DONE = False

def _initialize_gpu_device():
    """初始化并预热GPU设备"""
    global _gpu_device_cache, _gpu_warmup_done
    
    if _gpu_device_cache is None and TORCH_AVAILABLE and torch.cuda.is_available():
        _gpu_device_cache = torch.device('cuda')
        
        # GPU预热：执行一次小计算来初始化CUDA上下文
        if not _gpu_warmup_done:
            try:
                dummy_tensor = torch.tensor([1.0, 2.0], dtype=torch.float32, device=_gpu_device_cache)
                _ = torch.sin(dummy_tensor)  # 简单计算触发CUDA初始化
                _gpu_warmup_done = True
            except Exception as e:
                print(f"GPU预热失败: {e}")
                _gpu_device_cache = None
    
    return _gpu_device_cache

def find_center_point(line1_points, outer_point, angle1_deg=40, angle2_deg=36, use_gpu=False):
    """
    优化的中心点计算主函数，支持GPU/CPU切换
    减少GPU初始化开销，提高计算效率
    """
    if use_gpu and TORCH_AVAILABLE and torch.cuda.is_available():
        device = _initialize_gpu_device()
        if device is not None:
            return find_center_point_gpu(line1_points, outer_point, angle1_deg, angle2_deg, device)
        else:
            # GPU初始化失败，回退到CPU
            return find_center_point_cpu(line1_points, outer_point, angle1_deg, angle2_deg)
    else:
        return find_center_point_cpu(line1_points, outer_point, angle1_deg, angle2_deg)


def find_center_point_cpu(line1_points, outer_point, angle1_deg=40, angle2_deg=36):
    """
    CPU版本的中心点计算函数
    找到中心点，使得：
    1. 过该点的线2与线1夹角为angle1_deg
    2. 连接中心点和外沿点的线3与线2夹角为angle2_deg
    3. 当外沿点在左侧时：
       - 线2的角度小于线3的角度
       - 线2角度的绝对值大于线3角度的绝对值
    4. 当外沿点在右侧时：
       - 线2的角度大于线3的角度
       - 线2角度的绝对值小于线3角度的绝对值
    5. 中心点位于线1与过外延点的线1平行线之间
    """
    # 计算线1的角度
    line1_angle = calculate_line_angle(line1_points[0], line1_points[1])

    # 计算线1的中点
    line1_midpoint = ((line1_points[0][0] + line1_points[1][0]) / 2,
                      (line1_points[0][1] + line1_points[1][1]) / 2)

    # 判断外沿点在图像的哪一侧
    is_outer_point_left = outer_point[0] < line1_midpoint[0]

    # 计算线2的角度（与线1夹角为angle1_deg）
    line2_angle = line1_angle + math.radians(angle1_deg)

    # 根据外沿点位置计算线3的角度
    if is_outer_point_left:
        # 外沿点在左侧：线3角度大于线2角度
        line3_angle = line2_angle + math.radians(angle2_deg)
    else:
        # 外沿点在右侧：线3角度小于线2角度
        line3_angle = line2_angle - math.radians(angle2_deg)

    # 标准化角度到[-π, π]范围内
    def normalize_angle(angle):
        return (angle + math.pi) % (2 * math.pi) - math.pi

    # 标准化所有角度
    line2_angle_norm = normalize_angle(line2_angle)
    line3_angle_norm = normalize_angle(line3_angle)

    # 验证角度条件
    if is_outer_point_left:
        # 外沿点在左侧：
        # 1. 线2角度应小于线3角度
        if not (line2_angle_norm < line3_angle_norm):
            return [], None, None, None, None
    else:
        # 外沿点在右侧：
        # 1. 线2角度应大于线3角度
        if not (line2_angle_norm > line3_angle_norm):
            return [], None, None, None, None

    # 计算线1的直线方程: ax + by + c = 0
    a1 = line1_points[1][1] - line1_points[0][1]
    b1 = line1_points[0][0] - line1_points[1][0]
    c1 = line1_points[1][0] * line1_points[0][1] - line1_points[0][0] * line1_points[1][1]

    # 计算过外延点的平行于线1的直线方程
    c4 = -a1 * outer_point[0] - b1 * outer_point[1]

    # 从外延点沿着线3相反方向寻找中心点
    reverse_angle = (line3_angle + math.pi) % (2 * math.pi)

    # 计算线1长度作为参考距离
    line1_length = math.sqrt((line1_points[1][0] - line1_points[0][0]) ** 2 +
                             (line1_points[1][1] - line1_points[0][1]) ** 2)

    # 尝试不同距离找到在线1和线4之间的中心点
    center_points = []
    max_tries = 200  # 提升采样密度

    # 测试一系列距离（双方向，增加范围到 3 倍 line1_length）
    for i in range(1, max_tries + 1):
        dist_multiplier = i / max_tries * 3.0
        dist = line1_length * dist_multiplier

        # 方向1：reverse_angle
        center_x = outer_point[0] + dist * math.cos(reverse_angle)
        center_y = outer_point[1] + dist * math.sin(reverse_angle)

        # 检查点是否在线1和线4之间
        val1 = a1 * center_x + b1 * center_y + c1
        val4 = a1 * center_x + b1 * center_y + c4

        # 如果val1和val4符号相反，则点在线1和线4之间
        if math.copysign(1, val1) != math.copysign(1, val4):
            center_points.append((center_x, center_y))

        # 方向2：reverse_angle + π（等价于反向）
        center_x2 = outer_point[0] + dist * math.cos((reverse_angle + math.pi) % (2 * math.pi))
        center_y2 = outer_point[1] + dist * math.sin((reverse_angle + math.pi) % (2 * math.pi))

        val1_2 = a1 * center_x2 + b1 * center_y2 + c1
        val4_2 = a1 * center_x2 + b1 * center_y2 + c4
        if math.copysign(1, val1_2) != math.copysign(1, val4_2):
            center_points.append((center_x2, center_y2))

    return center_points, line2_angle, line3_angle, (a1, b1, c1), (a1, b1, c4)


def check_point_constraints(center_point, outer_point, points):
    """
    检查中心点是否满足所有约束条件

    Args:
        center_point: 中心点坐标
        outer_point: 外沿点坐标
        points: txt文件中读取的所有点坐标

    Returns:
        bool: 是否满足所有约束条件
        dict: 如果满足约束条件，返回包含所有距离值的字典；否则返回计算的距离字典或None
    """
    # 获取各条线的端点
    line1_points = points[:2]  # 第1、2行的点为线1的端点
    line2_points = points[2:4]  # 第3、4行的点为线2的端点
    line3_points = points[4:6]  # 第5、6行的点为线3的端点
    line4_points = points[6:8]  # 第7、8行的点为线4的端点

    # 计算线8的端点（点3、4的中点和点5、6的中点）
    line8_point1 = ((line2_points[0][0] + line2_points[1][0]) / 2,
                    (line2_points[0][1] + line2_points[1][1]) / 2)
    line8_point2 = ((line3_points[0][0] + line3_points[1][0]) / 2,
                    (line3_points[0][1] + line3_points[1][1]) / 2)

    try:
        # 计算线1的方程参数 ax + by + c = 0
        a1 = line1_points[1][1] - line1_points[0][1]
        b1 = line1_points[0][0] - line1_points[1][0]
        c1 = line1_points[1][0] * line1_points[0][1] - line1_points[0][0] * line1_points[1][1]

        # 计算过外延点的平行于线1的直线方程（线5）
        # 平行线的a和b系数相同，只需要计算新的c值
        c5 = -a1 * outer_point[0] - b1 * outer_point[1]

        # 计算中心点到线5的距离作为圆的半径
        circle_radius = abs(a1 * center_point[0] + b1 * center_point[1] + c5) / math.sqrt(a1 * a1 + b1 * b1)
        circle_diameter = circle_radius * 2

        # 计算其他线的方程参数
        # 线2
        a2 = line2_points[1][1] - line2_points[0][1]
        b2 = line2_points[0][0] - line2_points[1][0]
        c2 = line2_points[1][0] * line2_points[0][1] - line2_points[0][0] * line2_points[1][1]

        # 线3
        a3 = line3_points[1][1] - line3_points[0][1]
        b3 = line3_points[0][0] - line3_points[1][0]
        c3 = line3_points[1][0] * line3_points[0][1] - line3_points[0][0] * line3_points[1][1]

        # 线4
        a4 = line4_points[1][1] - line4_points[0][1]
        b4 = line4_points[0][0] - line4_points[1][0]
        c4 = line4_points[1][0] * line4_points[0][1] - line4_points[0][0] * line4_points[1][1]

        # 线8
        a8 = line8_point2[1] - line8_point1[1]
        b8 = line8_point1[0] - line8_point2[0]
        c8 = line8_point2[0] * line8_point1[1] - line8_point1[0] * line8_point2[1]

        # 计算到各条线的距离
        distance_to_line1 = calculate_distance_point_to_line(center_point, (a1, b1, c1))
        distance_to_line2 = calculate_distance_point_to_line(center_point, (a2, b2, c2))
        distance_to_line3 = calculate_distance_point_to_line(center_point, (a3, b3, c3))
        distance_to_line4 = calculate_distance_point_to_line(center_point, (a4, b4, c4))
        distance_to_line8 = calculate_distance_point_to_line(center_point, (a8, b8, c8))

        # 创建距离字典
        distances = {
            'circle_diameter': circle_diameter,
            'distance_to_line1': distance_to_line1,
            'distance_to_line2': distance_to_line2,
            'distance_to_line3': distance_to_line3,
            'distance_to_line4': distance_to_line4,
            'distance_to_line8': distance_to_line8
        }

        # 确保 CONSTRAINT_IDEALS 已被设置 (应该在调用此函数前由 update_constraint_ideals 设置)
        if CONSTRAINT_IDEALS is None:
            print("错误：CONSTRAINT_IDEALS 未设置！请确保已调用 update_constraint_ideals。")
            return False, distances

        is_valid = True
        if not (CONSTRAINT_IDEALS['circle_diameter']['min'] <= circle_diameter <= CONSTRAINT_IDEALS['circle_diameter']['max']):
            is_valid = False
        if not (CONSTRAINT_IDEALS['distance_to_line1']['min'] <= distance_to_line1 <=
                CONSTRAINT_IDEALS['distance_to_line1']['max']):
            is_valid = False
        if not (CONSTRAINT_IDEALS['distance_to_line4']['min'] <= distance_to_line4 <=
                CONSTRAINT_IDEALS['distance_to_line4']['max']):
            is_valid = False
        if not (CONSTRAINT_IDEALS['distance_to_line2']['min'] <= distance_to_line2 <=
                CONSTRAINT_IDEALS['distance_to_line2']['max']):
            is_valid = False
        if not (CONSTRAINT_IDEALS['distance_to_line3']['min'] <= distance_to_line3 <=
                CONSTRAINT_IDEALS['distance_to_line3']['max']):
            is_valid = False
        if not (CONSTRAINT_IDEALS['distance_to_line8']['min'] <= distance_to_line8 <=
                CONSTRAINT_IDEALS['distance_to_line8']['max']):
            is_valid = False

        if not is_valid:
            return False, distances

        return True, distances

    except Exception as e:
        print(f"计算距离时出错: {e}")
        # 创建一个默认距离字典，用于收集无效点
        default_distances = {
            'circle_diameter': 0,
            'distance_to_line1': 0,
            'distance_to_line2': 0,
            'distance_to_line3': 0,
            'distance_to_line4': 0,
            'distance_to_line8': 0
        }
        return False, default_distances

def check_points_constraints_batch(center_points, outer_point, points, line_coeffs=None):
    """
    批量向量化检查中心点是否满足所有约束条件，返回布尔掩码和距离数组。

    Args:
        center_points: list[tuple] 或 numpy.ndarray 形状 (N,2)
        outer_point: 外沿点坐标
        points: txt文件中读取的所有点坐标

    Returns:
        (is_valid_mask, distances_dict)
        - is_valid_mask: numpy.ndarray[bool] 长度N
        - distances_dict: dict 包含每个距离项目的numpy.ndarray长度N
    """
    # 转换为numpy数组
    if isinstance(center_points, list):
        if len(center_points) == 0:
            return np.array([], dtype=bool), {
                'circle_diameter': np.array([]),
                'distance_to_line1': np.array([]),
                'distance_to_line2': np.array([]),
                'distance_to_line3': np.array([]),
                'distance_to_line4': np.array([]),
                'distance_to_line8': np.array([]),
            }
        centers = np.array(center_points, dtype=np.float64)
    else:
        centers = center_points.astype(np.float64)

    if line_coeffs is None:
        line1_points = points[:2]
        line2_points = points[2:4]
        line3_points = points[4:6]
        line4_points = points[6:8]

        # 线8的两个点
        line8_point1 = ((line2_points[0][0] + line2_points[1][0]) / 2,
                        (line2_points[0][1] + line2_points[1][1]) / 2)
        line8_point2 = ((line3_points[0][0] + line3_points[1][0]) / 2,
                        (line3_points[0][1] + line3_points[1][1]) / 2)

        # 计算各线的参数
        a1 = line1_points[1][1] - line1_points[0][1]
        b1 = line1_points[0][0] - line1_points[1][0]
        c1 = line1_points[1][0] * line1_points[0][1] - line1_points[0][0] * line1_points[1][1]
        c5 = -a1 * outer_point[0] - b1 * outer_point[1]

        a2 = line2_points[1][1] - line2_points[0][1]
        b2 = line2_points[0][0] - line2_points[1][0]
        c2 = line2_points[1][0] * line2_points[0][1] - line2_points[0][0] * line2_points[1][1]

        a3 = line3_points[1][1] - line3_points[0][1]
        b3 = line3_points[0][0] - line3_points[1][0]
        c3 = line3_points[1][0] * line3_points[0][1] - line3_points[0][0] * line3_points[1][1]

        a4 = line4_points[1][1] - line4_points[0][1]
        b4 = line4_points[0][0] - line4_points[1][0]
        c4 = line4_points[1][0] * line4_points[0][1] - line4_points[0][0] * line4_points[1][1]

        a8 = line8_point2[1] - line8_point1[1]
        b8 = line8_point1[0] - line8_point2[0]
        c8 = line8_point2[0] * line8_point1[1] - line8_point1[0] * line8_point2[1]

        # 预计算分母
        den1 = math.sqrt(a1 * a1 + b1 * b1) if (a1 * a1 + b1 * b1) > 1e-12 else 1.0
        den2 = math.sqrt(a2 * a2 + b2 * b2) if (a2 * a2 + b2 * b2) > 1e-12 else 1.0
        den3 = math.sqrt(a3 * a3 + b3 * b3) if (a3 * a3 + b3 * b3) > 1e-12 else 1.0
        den4 = math.sqrt(a4 * a4 + b4 * b4) if (a4 * a4 + b4 * b4) > 1e-12 else 1.0
        den8 = math.sqrt(a8 * a8 + b8 * b8) if (a8 * a8 + b8 * b8) > 1e-12 else 1.0
    else:
        a1 = line_coeffs['a1']; b1 = line_coeffs['b1']; c1 = line_coeffs['c1']; c5 = line_coeffs['c5']
        a2 = line_coeffs['a2']; b2 = line_coeffs['b2']; c2 = line_coeffs['c2']
        a3 = line_coeffs['a3']; b3 = line_coeffs['b3']; c3 = line_coeffs['c3']
        a4 = line_coeffs['a4']; b4 = line_coeffs['b4']; c4 = line_coeffs['c4']
        a8 = line_coeffs['a8']; b8 = line_coeffs['b8']; c8 = line_coeffs['c8']
        den1 = line_coeffs['den1']; den2 = line_coeffs['den2']; den3 = line_coeffs['den3']; den4 = line_coeffs['den4']; den8 = line_coeffs['den8']

    xs = centers[:, 0]
    ys = centers[:, 1]

    # 向量化距离计算
    distance_to_line1 = np.abs(a1 * xs + b1 * ys + c1) / den1
    distance_to_line2 = np.abs(a2 * xs + b2 * ys + c2) / den2
    distance_to_line3 = np.abs(a3 * xs + b3 * ys + c3) / den3
    distance_to_line4 = np.abs(a4 * xs + b4 * ys + c4) / den4
    distance_to_line8 = np.abs(a8 * xs + b8 * ys + c8) / den8
    circle_diameter = 2.0 * (np.abs(a1 * xs + b1 * ys + c5) / den1)

    distances = {
        'circle_diameter': circle_diameter,
        'distance_to_line1': distance_to_line1,
        'distance_to_line2': distance_to_line2,
        'distance_to_line3': distance_to_line3,
        'distance_to_line4': distance_to_line4,
        'distance_to_line8': distance_to_line8,
    }

    if CONSTRAINT_IDEALS is None:
        # 如果未设置，全部标记为无效
        return np.zeros(len(centers), dtype=bool), distances

    # 逐项范围判定（向量化）
    mask = (
        (CONSTRAINT_IDEALS['circle_diameter']['min'] <= circle_diameter) & (circle_diameter <= CONSTRAINT_IDEALS['circle_diameter']['max']) &
        (CONSTRAINT_IDEALS['distance_to_line1']['min'] <= distance_to_line1) & (distance_to_line1 <= CONSTRAINT_IDEALS['distance_to_line1']['max']) &
        (CONSTRAINT_IDEALS['distance_to_line4']['min'] <= distance_to_line4) & (distance_to_line4 <= CONSTRAINT_IDEALS['distance_to_line4']['max']) &
        (CONSTRAINT_IDEALS['distance_to_line2']['min'] <= distance_to_line2) & (distance_to_line2 <= CONSTRAINT_IDEALS['distance_to_line2']['max']) &
        (CONSTRAINT_IDEALS['distance_to_line3']['min'] <= distance_to_line3) & (distance_to_line3 <= CONSTRAINT_IDEALS['distance_to_line3']['max']) &
        (CONSTRAINT_IDEALS['distance_to_line8']['min'] <= distance_to_line8) & (distance_to_line8 <= CONSTRAINT_IDEALS['distance_to_line8']['max'])
    )

    return mask, distances


def find_center_point_adaptive(points, outer_point, initial_angle2_deg=36, min_angle2_deg=0, print_info=True,
                               ignore_angle_constraint=False, use_gpu=False, selftest_tolerance=1e-3):
    """
    通过自适应角度找到中心点

    Args:
        points: 从txt文件读取的所有坐标点
        outer_point: 外沿点坐标
        initial_angle2_deg: 初始angle2值（度）
        min_angle2_deg: 最小允许的angle2值（度）

    Returns:
        center_point: 计算得到的中心点坐标
        line2_angle: 线2与水平线的夹角（弧度）
        line3_angle: 线3与水平线的夹角（弧度）
        angle1_deg: 使用的angle1值（度）
        angle2_deg: 使用的angle2值（度）
    """
    # 获取线1的端点（用于计算中心点）
    line1_points = points[:2]

    # 计算线1的中点
    line1_midpoint = ((line1_points[0][0] + line1_points[1][0]) / 2,
                      (line1_points[0][1] + line1_points[1][1]) / 2)
    
    # 计算线1的角度（相对于水平线）
    line1_vector = (line1_points[1][0] - line1_points[0][0], line1_points[1][1] - line1_points[0][1])
    line1_angle = math.degrees(math.atan2(line1_vector[1], line1_vector[0]))

    # 判断外沿点在图像的哪一侧
    is_outer_point_left = outer_point[0] < line1_midpoint[0]

    # 根据外沿点位置设置角度
    angle1_deg = -140 if is_outer_point_left else -40  # 线1与线6的夹角

    # 计算线6和线7的角度（相对于水平线）
    line6_angle = line1_angle + angle1_deg  # 线1角度 + 角度1_deg
    line7_angle = line6_angle + initial_angle2_deg  # 线6角度 + 角度2_deg

    # 打印外沿点位置和角度信息
    if print_info:
        print(f"\n外沿点位置: {'左侧' if is_outer_point_left else '右侧'}")
        print(f"线1角度（相对于水平线）: {line1_angle:.1f}°")
        print(f"线6角度（相对于水平线）: {line6_angle:.1f}°")
        print(f"线7初始角度（相对于水平线）: {line7_angle:.1f}°")
        print(f"线1与线6夹角: {angle1_deg}°")
        print(f"线6与线7初始夹角: {initial_angle2_deg}°")

    # 构造角度列表（0.1°步幅，不早停，完整覆盖）
    angle_step = 0.1
    angle2_list = []
    a = initial_angle2_deg
    while a >= min_angle2_deg:
        angle2_list.append(round(a, 1))
        a = round(a - angle_step, 1)

    # 可选：GPU一致性自测（仅首次执行）
    try:
        global _GPU_SELFTEST_DONE
        if use_gpu and TORCH_AVAILABLE and torch.cuda.is_available() and not _GPU_SELFTEST_DONE:
            ok, info = verify_gpu_cpu_consistency(line1_points, outer_point, angle1_deg=angle1_deg,
                                                  angle2_deg=initial_angle2_deg, tolerance=selftest_tolerance)
            status = '通过' if ok else '未通过'
            if print_info:
                print(f"GPU/CPU一致性自测[{status}]，容差={selftest_tolerance}: {info}")
            _GPU_SELFTEST_DONE = True
    except Exception as _e_self:
        if print_info:
            print(f"一致性自测异常: {_e_self}")

    # 预计算并复用线系数（供约束批处理使用）
    line2_points = points[2:4]
    line3_points = points[4:6]
    line4_points = points[6:8]
    line8_point1 = ((line2_points[0][0] + line2_points[1][0]) / 2,
                    (line2_points[0][1] + line2_points[1][1]) / 2)
    line8_point2 = ((line3_points[0][0] + line3_points[1][0]) / 2,
                    (line3_points[0][1] + line3_points[1][1]) / 2)

    a1 = line1_points[1][1] - line1_points[0][1]
    b1 = line1_points[0][0] - line1_points[1][0]
    c1 = line1_points[1][0] * line1_points[0][1] - line1_points[0][0] * line1_points[1][1]
    c5 = -a1 * outer_point[0] - b1 * outer_point[1]
    a2 = line2_points[1][1] - line2_points[0][1]
    b2 = line2_points[0][0] - line2_points[1][0]
    c2 = line2_points[1][0] * line2_points[0][1] - line2_points[0][0] * line2_points[1][1]
    a3 = line3_points[1][1] - line3_points[0][1]
    b3 = line3_points[0][0] - line3_points[1][0]
    c3 = line3_points[1][0] * line3_points[0][1] - line3_points[0][0] * line3_points[1][1]
    a4 = line4_points[1][1] - line4_points[0][1]
    b4 = line4_points[0][0] - line4_points[1][0]
    c4 = line4_points[1][0] * line4_points[0][1] - line4_points[0][0] * line4_points[1][1]
    a8 = line8_point2[1] - line8_point1[1]
    b8 = line8_point1[0] - line8_point2[0]
    c8 = line8_point2[0] * line8_point1[1] - line8_point1[0] * line8_point2[1]
    den1 = math.sqrt(a1 * a1 + b1 * b1) if (a1 * a1 + b1 * b1) > 1e-12 else 1.0
    den2 = math.sqrt(a2 * a2 + b2 * b2) if (a2 * a2 + b2 * b2) > 1e-12 else 1.0
    den3 = math.sqrt(a3 * a3 + b3 * b3) if (a3 * a3 + b3 * b3) > 1e-12 else 1.0
    den4 = math.sqrt(a4 * a4 + b4 * b4) if (a4 * a4 + b4 * b4) > 1e-12 else 1.0
    den8 = math.sqrt(a8 * a8 + b8 * b8) if (a8 * a8 + b8 * b8) > 1e-12 else 1.0
    _line_coeffs = {
        'a1': a1, 'b1': b1, 'c1': c1, 'c5': c5,
        'a2': a2, 'b2': b2, 'c2': c2,
        'a3': a3, 'b3': b3, 'c3': c3,
        'a4': a4, 'b4': b4, 'c4': c4,
        'a8': a8, 'b8': b8, 'c8': c8,
        'den1': den1, 'den2': den2, 'den3': den3, 'den4': den4, 'den8': den8,
    }

    all_valid_points = []
    all_invalid_points = []
    # 预候选阶段诊断计数（仅打印和汇总，不参与筛选逻辑）
    pre_angle_trials = 0
    pre_angle_relation_failures = 0
    pre_angle_relation_pass_no_centers = 0

    try:
        if use_gpu and TORCH_AVAILABLE and torch.cuda.is_available():
            device = _initialize_gpu_device()
            centers_by_angle, line6_angle, line7_angles, line1_eq, line4_eq = find_center_point_gpu_batch(
                line1_points, outer_point, angle1_deg, angle2_list, device
            )
            for idx, center_points in enumerate(centers_by_angle):
                # 预候选：记录角度尝试次数
                pre_angle_trials += 1
                if line6_angle is None or line7_angles[idx] is None:
                    continue
                # 保持约束判定使用原始线6角度
                line6_angle_deg_original = math.degrees(line6_angle)
                line6_angle_deg = line6_angle_deg_original
                line7_angle_deg = math.degrees(line7_angles[idx])
                orig_angle1_deg = angle1_deg
                angle_constraint_satisfied = True if ignore_angle_constraint else (
                    (orig_angle1_deg == -140 and line6_angle_deg_original < line7_angle_deg) if is_outer_point_left else
                    (orig_angle1_deg == -40 and line6_angle_deg_original > line7_angle_deg)
                )
                if not center_points:
                    # 预候选：区分“角度关系不满足”与“角度关系满足但无候选”
                    if not angle_constraint_satisfied:
                        pre_angle_relation_failures += 1
                    else:
                        pre_angle_relation_pass_no_centers += 1
                    continue
                mask, dists = check_points_constraints_batch(center_points, outer_point, points, line_coeffs=_line_coeffs)
                for i, cp in enumerate(center_points):
                    distances = {
                        'circle_diameter': float(dists['circle_diameter'][i]),
                        'distance_to_line1': float(dists['distance_to_line1'][i]),
                        'distance_to_line2': float(dists['distance_to_line2'][i]),
                        'distance_to_line3': float(dists['distance_to_line3'][i]),
                        'distance_to_line4': float(dists['distance_to_line4'][i]),
                        'distance_to_line8': float(dists['distance_to_line8'][i]),
                    }
                    final_is_valid = bool(mask[i]) and angle_constraint_satisfied
                    # 针对每个圆心归一化线6角度，并统一为负角
                    normalized_line6 = normalize_line6_angle(cp, outer_point, line6_angle)
                    adj_line6 = adjust_negative_angle(normalized_line6)
                    adj_line7 = adjust_negative_angle(line7_angles[idx])
                    entry = {
                        'center_point': cp,
                        'line6_angle': adj_line6,
                        'line7_angle': adj_line7,
                        'line6_angle_deg': math.degrees(adj_line6),
                        'line7_angle_deg': math.degrees(adj_line7),
                        'line1_eq': line1_eq,
                        'line4_eq': line4_eq,
                        'angle2_deg': angle2_list[idx],
                        **distances
                    }
                    if final_is_valid:
                        all_valid_points.append(entry)
                    else:
                        all_invalid_points.append(entry)
        else:
            # CPU：逐角度生成，但约束检查用批量向量化
            for current_angle2_deg in angle2_list:
                # 预候选：记录角度尝试次数
                pre_angle_trials += 1
                # 即使尚未生成候选，也可依据几何角度关系进行预判
                line6_angle_deg_original = line1_angle + angle1_deg
                line7_angle_deg = line6_angle_deg_original + (current_angle2_deg if is_outer_point_left else -current_angle2_deg)
                orig_angle1_deg = angle1_deg
                angle_constraint_satisfied = True if ignore_angle_constraint else (
                    (orig_angle1_deg == -140 and line6_angle_deg_original < line7_angle_deg) if is_outer_point_left else
                    (orig_angle1_deg == -40 and line6_angle_deg_original > line7_angle_deg)
                )
                result = find_center_point(line1_points, outer_point, angle1_deg, current_angle2_deg, use_gpu=False)
                if result is None or len(result) != 5:
                    # 无候选：根据角度关系归因
                    if not angle_constraint_satisfied:
                        pre_angle_relation_failures += 1
                    else:
                        pre_angle_relation_pass_no_centers += 1
                    continue
                center_points, line6_angle, line7_angle, line1_eq, line4_eq = result
                if line6_angle is None or line7_angle is None:
                    continue
                # 保持约束判定使用原始线6角度
                line6_angle_deg_original = math.degrees(line6_angle)
                line6_angle_deg = line6_angle_deg_original
                line7_angle_deg = math.degrees(line7_angle)
                orig_angle1_deg = angle1_deg
                angle_constraint_satisfied = True if ignore_angle_constraint else (
                    (orig_angle1_deg == -140 and line6_angle_deg_original < line7_angle_deg) if is_outer_point_left else
                    (orig_angle1_deg == -40 and line6_angle_deg_original > line7_angle_deg)
                )
                if not center_points:
                    # 无候选：根据角度关系归因
                    if not angle_constraint_satisfied:
                        pre_angle_relation_failures += 1
                    else:
                        pre_angle_relation_pass_no_centers += 1
                    continue
                mask, dists = check_points_constraints_batch(center_points, outer_point, points, line_coeffs=_line_coeffs)
                for i, cp in enumerate(center_points):
                    distances = {
                        'circle_diameter': float(dists['circle_diameter'][i]),
                        'distance_to_line1': float(dists['distance_to_line1'][i]),
                        'distance_to_line2': float(dists['distance_to_line2'][i]),
                        'distance_to_line3': float(dists['distance_to_line3'][i]),
                        'distance_to_line4': float(dists['distance_to_line4'][i]),
                        'distance_to_line8': float(dists['distance_to_line8'][i]),
                    }
                    final_is_valid = bool(mask[i]) and angle_constraint_satisfied
                    # 针对每个圆心归一化线6角度，并统一为负角
                    normalized_line6 = normalize_line6_angle(cp, outer_point, line6_angle)
                    adj_line6 = adjust_negative_angle(normalized_line6)
                    adj_line7 = adjust_negative_angle(line7_angle)
                    entry = {
                        'center_point': cp,
                        'line6_angle': adj_line6,
                        'line7_angle': adj_line7,
                        'line6_angle_deg': math.degrees(adj_line6),
                        'line7_angle_deg': math.degrees(adj_line7),
                        'line1_eq': line1_eq,
                        'line4_eq': line4_eq,
                        'angle2_deg': current_angle2_deg,
                        **distances
                    }
                    if final_is_valid:
                        all_valid_points.append(entry)
                    else:
                        all_invalid_points.append(entry)
    except Exception as e:
        if print_info:
            print(f"自适应批量计算出错: {str(e)}")

    # 记录预候选阶段诊断（线程安全）
    try:
        with GLOBAL_DIAG_LOCK:
            GLOBAL_PRE_DIAG[tuple(outer_point)] = {
                'pre_angle_trials': pre_angle_trials,
                'pre_angle_relation_failures': pre_angle_relation_failures,
                'pre_angle_relation_pass_no_centers': pre_angle_relation_pass_no_centers,
            }
    except Exception:
        pass

    # 如果找到了有效点，返回所有结果
    if all_valid_points:
        if print_info:
            print(f"总共找到 {len(all_valid_points)} 个符合条件的点")
            print(f"外沿点在{'左' if is_outer_point_left else '右'}侧，使用线1与线6夹角: {angle1_deg}°")
        return [(point['center_point'],
                 point['line6_angle'],
                 point['line7_angle'],
                 point['line1_eq'],
                 point['line4_eq'],
                 point['circle_diameter'],
                 point['distance_to_line1'],
                 point['distance_to_line4'],
                 point['distance_to_line2'],
                 point['distance_to_line3'],
                 point['distance_to_line8'],
                 True) for point in all_valid_points], True

    # 如果所有角度都尝试过仍未找到合适的点，返回不满足条件的点
    if print_info:
        print(f"警告：未找到满足所有约束条件的中心点")
        print(f"外沿点在{'左' if is_outer_point_left else '右'}侧，使用线1与线6夹角: {angle1_deg}°")
        print(
            f"将显示 {min(5, len(all_invalid_points))} 个不满足条件但评分最高的方案（总计 {len(all_invalid_points)} 个）")

    if all_invalid_points:
        return [(point['center_point'],
                 point['line6_angle'],
                 point['line7_angle'],
                 point['line1_eq'],
                 point['line4_eq'],
                 point['circle_diameter'],
                 point['distance_to_line1'],
                 point['distance_to_line4'],
                 point['distance_to_line2'],
                 point['distance_to_line3'],
                 point['distance_to_line8'],
                 False) for point in all_invalid_points], False

    return None, False


def score_solution(solution, all_solutions):
    """
    对解决方案进行综合评分

    Args:
        solution: 单个解决方案字典
        all_solutions: 所有解决方案的列表，用于计算位置稳定性

    Returns:
        float: 综合评分，分数越高越好
    """
    scores = {}
    total_score = 0
    total_weight = 0

    # 1. 约束条件满足程度评分
    for constraint, config in CONSTRAINT_IDEALS.items():
        value = float(solution[constraint])
        min_val = config['min']
        max_val = config['max']
        ideal = config['ideal']
        weight = config['weight']

        # 计算与理想值的接近程度 (0-1之间，越接近理想值分数越高)
        range_size = max_val - min_val
        distance_from_ideal = abs(value - ideal)
        normalized_distance = 1 - (distance_from_ideal / (range_size / 2))
        normalized_distance = max(0, min(normalized_distance, 1))  # 确保在0-1之间

        # 保存各项评分
        scores[constraint] = normalized_distance
        total_score += normalized_distance * weight
        total_weight += weight

    # 2. 中心点位置稳定性评分
    # 检查中心点的聚集程度，如果多个方案的中心点彼此靠近，则可能更稳定
    center_point = solution['center_point']
    position_score = 0

    # 计算该中心点与其他中心点的接近程度
    close_points_count = 0
    proximity_threshold = 5.0  # 接近程度阈值（像素）

    for other_solution in all_solutions:
        other_center = other_solution['center_point']
        distance = math.sqrt((center_point[0] - other_center[0]) ** 2 +
                             (center_point[1] - other_center[1]) ** 2)
        if distance < proximity_threshold:
            close_points_count += 1

    # 归一化位置稳定性评分 (0-1)
    position_stability = min(1.0, close_points_count / max(1, len(all_solutions) * 0.2))
    position_weight = 0.3  # 位置稳定性权重

    scores['position_stability'] = position_stability
    total_score += position_stability * position_weight
    total_weight += position_weight

    # 3. 距离约束的整体平衡评分
    # 计算各项约束条件的平均满足度的标准差（越小越平衡）
    distance_constraints = ['distance_to_line1', 'distance_to_line2',
                            'distance_to_line3', 'distance_to_line4']
    distance_scores = [scores[constraint] for constraint in distance_constraints if constraint in scores]  # 确保键存在
    balance_score = 0
    if distance_scores:  # 仅当有距离分数时计算
        balance_score = 1 - min(1, np.std(distance_scores))  # 标准差越小，评分越高

    balance_weight = 0.2  # 平衡性权重
    scores['balance'] = balance_score
    total_score += balance_score * balance_weight
    total_weight += balance_weight

    # 计算加权总分
    final_score = total_score / total_weight if total_weight > 0 else 0

    # 添加各项评分
    solution['scores'] = scores
    solution['final_score'] = final_score

    return final_score


def calculate_coverage_angle(line6_angle_rad, line7_angle_rad):
    """计算覆盖率 - 方法1：基于角度"""
    if line6_angle_rad is None or line7_angle_rad is None:
        return 0
    angle67_rad = (line7_angle_rad - line6_angle_rad + math.pi) % (2 * math.pi) - math.pi
    angle67_deg_abs = abs(math.degrees(angle67_rad))
    coverage = ((180.0 - angle67_deg_abs) / 180.0) * 100.0 if angle67_deg_abs <= 180 else 0
    return coverage


def calculate_coverage_horizontal(outer_point, center_point, radius, line6_angle_rad, image_width):
    """计算覆盖率 - 方法2：基于水平距离，允许负值和大于100%的值"""
    if outer_point is None or center_point is None or radius is None or radius <= 0 or line6_angle_rad is None:
        return 0.0

    try:
        cx, cy = center_point
        ox = outer_point[0]

        cos_a = math.cos(line6_angle_rad)
        p1_x = cx + radius * cos_a
        p2_x = cx - radius * cos_a

        x_n = min(p1_x, p2_x)
        x_f = max(p1_x, p2_x)
        width_h = x_f - x_n

        effective_comparison_point_x = 0
        if image_width <= 0:
            print(
                "Warning: Invalid image_width for horizontal coverage. Defaulting to outer_point vs center_point mode.")
            effective_comparison_point_x = center_point[0]
        else:
            effective_comparison_point_x = image_width / 2.0

        coverage = 0.0
        if width_h < 1e-6:  # Diameter is almost vertical
            if abs(ox - cx) < 1e-6:  # Outer point x coincides with center x
                return 100.0
            else:
                # For vertical diameter, use arbitrary extreme values based on relative position to center of vertical diameter (cx)
                # The "mode" (left/right of image) influences which extreme is "more covered" vs "less covered"
                is_outer_left_of_comparison = outer_point[0] < effective_comparison_point_x
                if is_outer_left_of_comparison:  # "Left" mode (outer point left of image mid or center)
                    # If ox < cx, it's "more left" than the vertical diameter's center.
                    # In "left mode", coverage is conceptually from right to left.
                    # So, ox < cx means "super covered" relative to cx.
                    return 200.0 if ox < cx else -100.0
                else:  # "Right" mode
                    # If ox > cx, it's "more right" than the vertical diameter's center.
                    # In "right mode", coverage is conceptually from left to right.
                    # So, ox > cx means "super covered" relative to cx.
                    return 200.0 if ox > cx else -100.0

        # Normal case: width_h is significant
        if outer_point[0] < effective_comparison_point_x:
            # Outer point to the "left" of comparison point: Effective coverage from right (x_f) to left (x_n) of SEMICIRCLE
            covered_dist = x_f - ox
            coverage = (covered_dist / width_h) * 100.0
        else:
            # Outer point to the "right" of or at comparison point: Effective coverage from left (x_n) to right (x_f) of SEMICIRCLE
            covered_dist = ox - x_n
            coverage = (covered_dist / width_h) * 100.0

        return coverage

    except Exception as e:
        print(f"Error calculating horizontal coverage: {e}")


def calculate_circle_diameter_line4(center_point, line4_eq):
    """计算以中心点为圆心，与线4相切的圆的直径"""
    a, b, c = line4_eq
    # 计算中心点到线4的距离作为半径
    radius = abs(a * center_point[0] + b * center_point[1] + c) / math.sqrt(a * a + b * b)
    return radius * 2


def merge_similar_results(results, angle_threshold=3.0, diameter_threshold=3.0, point_threshold=3.0,
                          center_threshold=5.0):
    """
    合并相似的方案，满足任意一个条件就合并：
    1. 线6与线7的夹角差异 ≤ 3度，或
    2. 圆直径差异 ≤ 3，或
    3. 外沿点位置差异 ≤ 3像素，或
    4. 中心点位置差异 ≤ 5像素

    Args:
        results: 排序后的结果列表
        angle_threshold: 角度差异阈值（度）
        diameter_threshold: 直径差异阈值
        point_threshold: 外沿点位置差异阈值（像素）
        center_threshold: 中心点位置差异阈值（像素）

    Returns:
        合并后的结果列表
    """
    if not results:
        return []

    merged_results = []
    current_group = [results[0]]

    for i in range(1, len(results)):
        current = results[i]
        base = current_group[0]  # 使用组内第一个方案作为基准

        # 检查是否相似
        # 1. 检查角度差异
        angle_diff = abs(current['line7_angle_rad'] - current['line6_angle_rad'] -
                         (base['line7_angle_rad'] - base['line6_angle_rad']))
        angle_diff = math.degrees(angle_diff)

        # 2. 检查直径差异
        diameter_diff = abs(current['circle_diameter'] - base['circle_diameter'])

        # 3. 检查外沿点位置差异
        point_diff = math.sqrt(
            (current['outer_point'][0] - base['outer_point'][0]) ** 2 +
            (current['outer_point'][1] - base['outer_point'][1]) ** 2
        )

        # 4. 检查中心点位置差异
        center_diff = math.sqrt(
            (current['center_point'][0] - base['center_point'][0]) ** 2 +
            (current['center_point'][1] - base['center_point'][1]) ** 2
        )

        # 满足任意一个条件就认为是相似的
        if (angle_diff <= angle_threshold or
                diameter_diff <= diameter_threshold or
                point_diff <= point_threshold or
                center_diff <= center_threshold):
            # 如果相似，添加到当前组
            current_group.append(current)
        else:
            # 如果不相似，处理当前组并开始新组
            if current_group:
                # 选择组内评分最高的方案（已经是第一个）
                merged_results.append(base)
            current_group = [current]

    # 处理最后一组
    if current_group:
        merged_results.append(current_group[0])

    return merged_results


def thread_safe_cache_access(cache, key, cache_lock=None):
    """
    线程安全的缓存访问函数
    """
    if cache_lock is not None:
        with cache_lock:
            return cache.get(key)
    else:
        return cache.get(key)

def thread_safe_cache_update(cache, key, value, cache_lock=None):
    """
    线程安全的缓存更新函数
    """
    if cache_lock is not None:
        with cache_lock:
            cache[key] = value
    else:
        cache[key] = value

def check_circle_curve_intersection_thread_safe(center_point, radius, curve_img_path, curve_cache, cache_lock=None, image_cache=None):
    """
    线程安全版本的圆与曲线相交检查函数
    """
    # 线程安全地检查缓存
    cached_data = thread_safe_cache_access(curve_cache, curve_img_path, cache_lock)
    
    if cached_data is not None:
        curve_points, convex_hull = cached_data
    else:
        # 读取曲线图像（使用缓存）
        if image_cache is not None:
            curve_img = read_image_with_cache(curve_img_path, image_cache, cache_lock)
        else:
            curve_img = read_image_with_pil(curve_img_path)
        if curve_img is None:
            return False

        # 获取曲线上的所有点
        y_indices, x_indices = np.where(curve_img == 1)
        if len(y_indices) == 0:
            y_indices, x_indices = np.where(curve_img > 0)

        curve_points = list(zip(x_indices, y_indices))
        if len(curve_points) == 0:
            return False

        # 计算凸包
        points_array = np.array(curve_points).reshape(-1, 2)
        points_array = points_array.astype(np.int32)
        convex_hull = cv2.convexHull(points_array)

        # 线程安全地保存到缓存
        thread_safe_cache_update(curve_cache, curve_img_path, (curve_points, convex_hull), cache_lock)
    
    # 检查圆与凸包是否相交
    center_point_int = (int(center_point[0]), int(center_point[1]))
    distance_to_hull = cv2.pointPolygonTest(convex_hull, center_point_int, True)

    if distance_to_hull >= 0 or abs(distance_to_hull) <= radius:
        # 使用距离变换快速判断是否有曲线点位于圆内：D(center) <= radius
        try:
            dist_key = f"{curve_img_path}::dist_field"
            dist_field = thread_safe_cache_access(image_cache, dist_key, cache_lock) if image_cache is not None else None
            if dist_field is None:
                # 读取曲线图像
                curve_img = read_image_with_cache(curve_img_path, image_cache, cache_lock) if image_cache is not None else read_image_with_pil(curve_img_path)
                if curve_img is None:
                    return False
                # 生成距离变换：将曲线像素设为0，背景设为255
                curve_mask = (curve_img > 0)
                src = np.where(curve_mask, 0, 255).astype(np.uint8)
                dist_field = cv2.distanceTransform(src, cv2.DIST_L2, 3)
                if image_cache is not None:
                    thread_safe_cache_update(image_cache, dist_key, dist_field, cache_lock)

            h, w = dist_field.shape[:2]
            cx, cy = int(round(center_point[0])), int(round(center_point[1]))
            if cx < 0 or cy < 0 or cx >= w or cy >= h:
                return False
            d_center = float(dist_field[cy, cx])
            if d_center <= float(radius):
                return True
        except Exception:
            # 回退到向量化逐点检查
            if len(curve_points) > 1000:
                step = max(1, len(curve_points) // 1000)
                sampled_points = curve_points[::step]
            else:
                sampled_points = curve_points
            if sampled_points:
                pts = np.array(sampled_points, dtype=np.float64)
                xs = pts[:, 0]
                ys = pts[:, 1]
                cx, cy = float(center_point[0]), float(center_point[1])
                dists_sq = (cx - xs) ** 2 + (cy - ys) ** 2
                if np.any(dists_sq <= (radius ** 2)):
                    return True

    return False

def calculate_min_distance_circle_to_curve_thread_safe(center_point, radius, curve_img_path, curve_cache, cache_lock=None, image_cache=None):
    """
    线程安全版本的圆到曲线最小距离计算函数
    """
    try:
        if not os.path.exists(curve_img_path):
            return None

        # 线程安全地检查缓存
        cached_data = thread_safe_cache_access(curve_cache, curve_img_path, cache_lock)
        
        if cached_data is not None and isinstance(cached_data, tuple) and len(cached_data) >= 1:
            curve_points = cached_data[0]
        else:
            # 读取曲线图像（使用缓存）
            if image_cache is not None:
                curve_img = read_image_with_cache(curve_img_path, image_cache, cache_lock)
            else:
                curve_img = read_image_with_pil(curve_img_path)
            if curve_img is None:
                return None

            # 获取曲线上的所有点
            y_indices, x_indices = np.where(curve_img == 1)
            if len(y_indices) == 0:
                y_indices, x_indices = np.where(curve_img > 0)

            curve_points = list(zip(x_indices, y_indices))
            if len(curve_points) == 0:
                return None

            # 计算凸包
            points_array = np.array(curve_points).reshape(-1, 2)
            points_array = points_array.astype(np.int32)
            convex_hull = cv2.convexHull(points_array)

            # 线程安全地保存到缓存
            thread_safe_cache_update(curve_cache, curve_img_path, (curve_points, convex_hull), cache_lock)

        # 优先使用距离变换：最小距离 = max(0, D(center) - radius)
        try:
            dist_key = f"{curve_img_path}::dist_field"
            dist_field = thread_safe_cache_access(image_cache, dist_key, cache_lock) if image_cache is not None else None
            if dist_field is None:
                # 读取曲线图像
                curve_img = read_image_with_cache(curve_img_path, image_cache, cache_lock) if image_cache is not None else read_image_with_pil(curve_img_path)
                if curve_img is None:
                    return None
                curve_mask = (curve_img > 0)
                src = np.where(curve_mask, 0, 255).astype(np.uint8)
                dist_field = cv2.distanceTransform(src, cv2.DIST_L2, 3)
                if image_cache is not None:
                    thread_safe_cache_update(image_cache, dist_key, dist_field, cache_lock)

            h, w = dist_field.shape[:2]
            cx, cy = int(round(center_point[0])), int(round(center_point[1]))
            if cx < 0 or cy < 0 or cx >= w or cy >= h:
                return None
            d_center = float(dist_field[cy, cx])
            return max(0.0, d_center - float(radius))
        except Exception:
            # 回退到向量化距离计算
            if curve_points:
                pts = np.array(curve_points, dtype=np.float64)
                xs = pts[:, 0]
                ys = pts[:, 1]
                cx, cy = float(center_point[0]), float(center_point[1])
                dists = np.hypot(cx - xs, cy - ys) - float(radius)
                min_distance = float(dists.min())
                return max(0.0, min_distance)
            else:
                return None

    except Exception as e:
        return None

def process_single_outer_point(outer_point, points, curve2_img_path, scale, curve_cache, ignore_angle_constraint=False, file_name=None, actual_image_width=None, cache_lock=None, image_cache=None, use_gpu=False):
    """
    处理单个外沿点的函数，用于多线程并行处理
    
    Args:
        outer_point: 外沿点坐标
        points: 所有点的坐标
        curve2_img_path: 曲线2图像路径
        scale: 比例尺
        curve_cache: 曲线缓存
        ignore_angle_constraint: 是否忽略角度约束
        file_name: 文件名（用于曲线3路径构建）
        actual_image_width: 实际图像宽度
        cache_lock: 线程锁，用于线程安全的缓存操作
        image_cache: 图像缓存
    
    Returns:
        list: 该外沿点的所有有效结果
    """
    results_for_point = []
    
    try:
        # 使用自适应方法确定中心点并计算相关角度
        results, is_valid = find_center_point_adaptive(points, outer_point, print_info=False,
                                                       ignore_angle_constraint=ignore_angle_constraint, use_gpu=use_gpu)

        # 去除诊断统计，仅保留候选生成与筛选逻辑

        if results is not None:
            # 记录候选数量的诊断统计已移除

            for j, result in enumerate(results):
                center_point, line6_angle, line7_angle, line1_eq, line4_eq, circle_diameter, distance_to_line1, distance_to_line4, distance_to_line2, distance_to_line3, distance_to_line8, is_point_valid = result

                # 计算圆的半径
                radius = circle_diameter / 2

                curve3_img_path = None
                if FOLDER_C3 and file_name:
                    curve3_filename = file_name.replace('.png', '') + '_bkx.png'
                    curve3_img_path = os.path.join(FOLDER_C3, curve3_filename)

                circle_intersects_curve2 = False
                if curve2_img_path and os.path.exists(curve2_img_path):
                    circle_intersects_curve2 = check_circle_curve_intersection_thread_safe(
                        center_point, radius, curve2_img_path, curve_cache, cache_lock, image_cache
                    )
                    if circle_intersects_curve2:
                        continue

                circle_intersects_curve3 = False
                if curve3_img_path and os.path.exists(curve3_img_path):
                    circle_intersects_curve3 = check_circle_curve_intersection_thread_safe(
                        center_point, radius, curve3_img_path, curve_cache, cache_lock, image_cache
                    )
                    if circle_intersects_curve3:
                        continue

                # 计算安全的标准偶数直径 (需要先计算 actual_diameter)
                actual_diameter = circle_diameter * scale  # 计算实际直径
                safe_even_diameter = round_to_safe_even_diameter(center_point, actual_diameter, curve2_img_path,
                                                                 scale, curve_cache, cache_lock, image_cache, curve3_img_path=curve3_img_path)

                if safe_even_diameter is None or safe_even_diameter < MIN_SAFE_DIAMETER:
                    continue

                # 移除仅用于诊断的约束失败统计

                # 计算圆到曲线2的最小距离 (如果找到安全直径)
                min_dist_curve2 = None
                min_dist_curve2_actual = None
                if safe_even_diameter is not None:
                    standard_pixel_diameter = safe_even_diameter / scale
                    standard_radius = standard_pixel_diameter / 2
                    min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(center_point, standard_radius,
                                                                             curve2_img_path, curve_cache, cache_lock, image_cache)
                    if min_dist_curve2 is not None:
                        min_dist_curve2_actual = min_dist_curve2 * scale

                # 再次确保线6角度统一（幂等处理），并统一为负角
                line6_angle = normalize_line6_angle(center_point, outer_point, line6_angle)
                line6_angle = adjust_negative_angle(line6_angle)
                line7_angle = adjust_negative_angle(line7_angle)

                result_dict = {
                    'outer_point': outer_point,
                    'center_point': center_point,
                    'norm_denom': float(CURRENT_NORM_DENOM or 1.0),
                    'line6_angle_rad': line6_angle,
                    'line7_angle_rad': line7_angle,
                    'line6_angle_deg': math.degrees(line6_angle),
                    'line7_angle_deg': math.degrees(line7_angle),
                    'line1_eq': line1_eq,
                    'line4_eq': line4_eq,
                    'circle_diameter': circle_diameter,
                    'distance_to_line1': distance_to_line1,
                    'distance_to_line4': distance_to_line4,
                    'distance_to_line2': distance_to_line2,
                    'distance_to_line3': distance_to_line3,
                    'distance_to_line8': distance_to_line8,
                    'is_valid': is_point_valid,
                    'is_special_fallback': False,
                    'intersects_curve2': False,
                    'scale_factor': scale,
                    'safe_even_diameter': safe_even_diameter,
                    'actual_diameter': actual_diameter
                }
                
                # 计算两种覆盖率
                coverage_angle = calculate_coverage_angle(result_dict.get('line6_angle_rad'),
                                                          result_dict.get('line7_angle_rad'))
                current_radius = (result_dict.get('safe_even_diameter') / scale / 2) if result_dict.get(
                    'safe_even_diameter') is not None and scale > 0 else (result_dict.get('circle_diameter', 0) / 2)
                coverage_horizontal = calculate_coverage_horizontal(outer_point, center_point, current_radius,
                                                                    result_dict.get('line6_angle_rad'),
                                                                    actual_image_width) if actual_image_width else 0

                result_dict['coverage_rate_angle'] = coverage_angle
                result_dict['coverage_rate_horizontal'] = coverage_horizontal
                result_dict['need_cover'] = coverage_angle < COVERAGE_THRESHOLD
                
                # 添加圆到曲线2的距离信息
                if min_dist_curve2 is not None:
                    result_dict['circle_to_curve2_distance'] = min_dist_curve2
                    result_dict['circle_to_curve2_distance_actual'] = min_dist_curve2_actual
                    # 移除仅用于诊断的距离<1px统计

                # 添加圆到曲线3的距离（如果计算成功）
                min_dist_curve3 = None
                min_dist_curve3_actual = None
                if safe_even_diameter is not None and curve3_img_path:
                    standard_pixel_diameter_c3 = safe_even_diameter / scale
                    standard_radius_c3 = standard_pixel_diameter_c3 / 2
                    min_dist_curve3 = calculate_min_distance_circle_to_curve_thread_safe(center_point, standard_radius_c3,
                                                                             curve3_img_path, curve_cache, cache_lock, image_cache)
                    if min_dist_curve3 is not None:
                        min_dist_curve3_actual = min_dist_curve3 * scale
                        result_dict['circle_to_curve3_distance'] = min_dist_curve3
                        result_dict['circle_to_curve3_distance_actual'] = min_dist_curve3_actual

                # 对结果进行评分
                score_solution(result_dict, [result_dict])
                results_for_point.append(result_dict)

        else:
            # 无候选时，不进行诊断打印与统计，直接跳过
            pass
                
    except Exception as e:
        # 处理异常，但不打印错误信息
        pass
    
    return results_for_point


def check_circle_curve_intersection(center_point, radius, curve_img_path, curve_cache={}):
    """
    检查圆是否与曲线相交，使用凸包优化判断

    Args:
        center_point: 圆心坐标
        radius: 圆的半径
        curve_img_path: 曲线图像路径
        curve_cache: 缓存已读取的曲线点和凸包，避免重复计算

    Returns:
        bool: 如果圆与曲线相交返回True，否则返回False
    """
    try:
        # 使用缓存减少重复读取图像和计算凸包的开销
        if curve_img_path in curve_cache:
            curve_points, convex_hull = curve_cache[curve_img_path]
        else:
            # 读取曲线图像
            curve_img = read_image_with_pil(curve_img_path)
            if curve_img is None:
                # 不打印警告
                return False

            # 获取曲线上的所有点
            y_indices, x_indices = np.where(curve_img == 1)
            if len(y_indices) == 0:  # 如果没有找到值为1的点，尝试找白色点
                y_indices, x_indices = np.where(curve_img > 0)

            curve_points = list(zip(x_indices, y_indices))

            if len(curve_points) == 0:
                # 不打印警告
                return False

            # 计算凸包
            points_array = np.array(curve_points).reshape(-1, 2)
            # 确保点坐标为整数类型
            points_array = points_array.astype(np.int32)
            convex_hull = cv2.convexHull(points_array)

            # 保存到缓存
            curve_cache[curve_img_path] = (curve_points, convex_hull)
            # 不打印缓存信息

        # 1. 首先检查圆与凸包是否相交
        # 检查圆心是否在凸包内部
        center_point_int = (int(center_point[0]), int(center_point[1]))
        distance_to_hull = cv2.pointPolygonTest(convex_hull, center_point_int, True)

        # 如果圆心在凸包内部或者到凸包的距离小于等于半径，则圆与凸包相交
        if distance_to_hull >= 0 or abs(distance_to_hull) <= radius:
            # 进一步检查圆是否与曲线上的点相交
            # 为了提高性能，可以只检查部分采样点
            if len(curve_points) > 1000:
                step = len(curve_points) // 1000
                sampled_points = np.array(curve_points[::step])
            else:
                sampled_points = np.array(curve_points)

            if len(sampled_points) > 0:
                distances = np.sqrt(
                    (sampled_points[:, 0] - center_point[0]) ** 2 +
                    (sampled_points[:, 1] - center_point[1]) ** 2
                )
                return np.any(distances <= radius)

            # 如果没有采样点（应该不会发生），保守地返回True
            return True

        # 如果圆与凸包不相交，则肯定与曲线不相交
        return False

    except Exception as e:
        # 不打印错误信息
        # 出错时保守地返回True以避免生成无效结果
        return True


def round_to_even(value):
    return int(2 * round(value / 2))

def ceil_to_even(value):
    return int(2 * math.ceil(value / 2))


def round_to_safe_even_diameter(center_point, original_diameter, curve2_img_path, scale, curve_cache={}, cache_lock=None, image_cache=None, prefer_round_up=False, curve3_img_path=None):
    even_diameter = ceil_to_even(original_diameter) if prefer_round_up else round_to_even(original_diameter)

    min_c2 = _cfg_float('MIN_CURVE2_DISTANCE', 2.0)
    min_c3 = _cfg_float('MIN_CURVE3_DISTANCE', min_c2)

    has_c2 = bool(curve2_img_path and os.path.exists(curve2_img_path))
    has_c3 = bool(curve3_img_path and os.path.exists(curve3_img_path))
    if not has_c2 and not has_c3:
        return even_diameter

    def _min_dist_for(diameter_mm, curve_img_path):
        if not curve_img_path or not os.path.exists(curve_img_path):
            return None
        pixel_diameter = diameter_mm / scale if scale and scale > 0 else diameter_mm
        radius_px = pixel_diameter / 2.0
        return calculate_min_distance_circle_to_curve_thread_safe(center_point, radius_px, curve_img_path, curve_cache, cache_lock, image_cache)

    def _ok(diameter_mm):
        if has_c2:
            d2 = _min_dist_for(diameter_mm, curve2_img_path)
            if d2 is None or float(d2) < float(min_c2):
                return False
        if has_c3:
            d3 = _min_dist_for(diameter_mm, curve3_img_path)
            if d3 is None or float(d3) < float(min_c3):
                return False
        return True

    if _ok(even_diameter):
        return even_diameter
    current_diameter = even_diameter - 2
    while current_diameter >= MIN_SAFE_DIAMETER:
        if _ok(current_diameter):
            return current_diameter
        current_diameter -= 2

    # 如果所有尝试都失败，返回None表示无法找到安全的标准直径
    return None


def process_file_set_adaptive(file_name, show_individual_windows=True, target_outer_point=None,
                              ignore_angle_constraint=False, use_gpu=False, progress_callback=None):
    """使用自适应角度处理一组相关文件"""
    # 记录总开始时间
    total_start_time = time.time()
    personal_enable = _cfg_bool('PERSONALIZED_CONSTRAINTS_ENABLE', False)
    _log_case(file_name, f"个性化约束: {'启用' if personal_enable else '关闭'}")
    
    # 构建文件路径
    step_start_time = time.time()
    original_img_path = os.path.join(FOLDER_A, f'{file_name}.png')
    curve1_img_path = os.path.join(FOLDER_B, f'{file_name}_kjwy.png')  # 曲线1
    curve2_filename = file_name.replace('.png', '') + '_bks.png'
    curve2_img_path = os.path.join(FOLDER_C4, curve2_filename)  # 曲线2
    txt_path = os.path.join(FOLDER_C, f'{file_name}.txt')
    print(f"步骤1 - 构建文件路径: {(time.time() - step_start_time)*1000:.2f}ms")
    if progress_callback:
        try:
            progress_callback(22)
        except Exception:
            pass

    # 获取图像宽度
    step_start_time = time.time()
    actual_image_width = 0
    try:
        if os.path.exists(original_img_path):
            pil_img_for_width = Image.open(original_img_path)
            actual_image_width = pil_img_for_width.width
        else:
            print(
                f"Warning: Image file not found at {original_img_path} for process_file_set_adaptive. Width will be 0.")
    except Exception as e_img_width:
        print(f"Warning: Error reading image width from {original_img_path}: {e_img_width}. Width will be 0.")
        actual_image_width = 0
    print(f"步骤2 - 获取图像宽度: {(time.time() - step_start_time)*1000:.2f}ms")
    if progress_callback:
        try:
            progress_callback(24)
        except Exception:
            pass

    # 读取比例尺
    step_start_time = time.time()
    scale = read_scale_from_excel(file_name)
    print(f"步骤3 - 读取比例尺: {(time.time() - step_start_time)*1000:.2f}ms")
    print(f"比例尺: {scale}")
    if progress_callback:
        try:
            progress_callback(25)
        except Exception:
            pass

    # 1. 从txt文件读取所有点
    step_start_time = time.time()
    points = read_points_from_txt(txt_path)
    if points is None:
        raise ValueError(f"无法从文件中读取有效的坐标点: {txt_path}")
    print(f"步骤4 - 读取坐标点: {(time.time() - step_start_time)*1000:.2f}ms")
    if progress_callback:
        try:
            progress_callback(26)
        except Exception:
            pass

    global CURRENT_NORM_DENOM, CONSTRAINT_IDEALS
    CURRENT_NORM_DENOM = 1.0

    level = int(CURRENT_LEVEL or 1)
    fixed_raw = _get_fixed_constraint_ideals(level)
    if personal_enable:
        ok = _apply_personalized_constraint_ideals(file_name, level, fixed_raw=fixed_raw)
        if not ok or not CONSTRAINT_IDEALS:
            CONSTRAINT_IDEALS = fixed_raw
    else:
        CONSTRAINT_IDEALS = fixed_raw

    # 2. 从曲线图像中找到所有曲线点
    step_start_time = time.time()
    try:
        curve_points = find_curve_points(curve1_img_path)  # 从曲线1找点
        print(f"步骤5 - 提取曲线点: {(time.time() - step_start_time)*1000:.2f}ms")
        print(f"在曲线1中找到 {len(curve_points)} 个曲线点")
    except Exception as e:
        raise ValueError(f"无法从曲线1图像中找到曲线点: {str(e)}")
    if progress_callback:
        try:
            progress_callback(27)
        except Exception:
            pass

    # 检查曲线2是否存在，但不输出信息
    try:
        if not os.path.exists(curve2_img_path):
            pass  # 不打印警告
    except Exception:
        pass  # 不打印错误信息

    # 创建曲线点缓存和图像缓存
    curve_cache = {}
    image_cache = {}

    # 存储所有常规位置的结果
    all_regular_results = []

    # 3. 遍历曲线上的每个点作为外沿点 或 使用指定点
    total_points = len(curve_points)

    if target_outer_point is None:
        # 正常模式：遍历采样点
        step = 2  # 修改：使用固定的步长2，更密集地采样
        points_to_process = curve_points[::step]
        print("正在处理所有可能的外沿点位置...")
    else:
        # 交互模式：只处理指定点
        points_to_process = [target_outer_point]
        print(f"正在处理指定外沿点: {target_outer_point}")

    # 使用多线程并行处理外沿点
    step_start_time = time.time()
    
    if target_outer_point is None:
        # 正常模式：使用多线程并行处理
        if use_gpu:
            # GPU加速模式：增加线程数以充分利用GPU并行能力
            max_workers = min(16, len(points_to_process))  # GPU模式下使用更多线程
        else:
            max_workers = min(8, len(points_to_process))  # CPU模式限制线程数
        
        # 创建线程安全的缓存
        thread_safe_cache = {}
        thread_safe_image_cache = {}
        cache_lock = threading.Lock()
        # 移除全局诊断汇总的重置
        
        # 使用ThreadPoolExecutor进行并行处理
        completed_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_point = {}
            for outer_point in points_to_process:
                future = executor.submit(
                    process_single_outer_point,
                    outer_point, points, curve2_img_path, scale, thread_safe_cache,
                    ignore_angle_constraint, file_name, actual_image_width, cache_lock, thread_safe_image_cache, use_gpu
                )
                future_to_point[future] = outer_point
            
            # 收集结果
            for future in as_completed(future_to_point):
                outer_point = future_to_point[future]
                completed_count += 1
                
                # 仅通过回调更新进度
                if progress_callback:
                    try:
                        ui_progress = 20 + int(60.0 * completed_count / max(1, len(points_to_process)))
                        ui_progress = max(21, min(80, ui_progress))
                        progress_callback(ui_progress)
                    except Exception:
                        pass
                
                try:
                    results_for_point = future.result()
                    all_regular_results.extend(results_for_point)
                except Exception as e:
                    # 处理异常，但不打印错误信息
                    pass
        
        if progress_callback:
            try:
                progress_callback(82)
            except Exception:
                pass
        # 移除全局统计摘要打印
        
    else:
        # 交互模式：只处理指定点（单线程）
        try:
            # 移除单点模式的全局诊断汇总重置

            results_for_point = process_single_outer_point(
                target_outer_point, points, curve2_img_path, scale, curve_cache,
                ignore_angle_constraint, file_name, actual_image_width, None, image_cache, use_gpu
            )
            all_regular_results.extend(results_for_point)
        except Exception as e:
            print(f"\n处理外沿点 {target_outer_point} 时出错: {e}")

        # 移除单点模式的全局统计摘要打印

    # 移除处理耗时的诊断打印

    # === 计算备选方案 ===
    step_start_time = time.time()
    fallback_result = None  # 初始化备选方案为空
    best_fallback_result = None  # 用于存储最佳备选方案
    best_fallback_score = -float('inf')  # 初始化最佳评分为负无穷
    try:
        # 找到曲线1的最低点
        lowest_point = find_lowest_point(curve1_img_path)
        print(f"找到曲线1最低点: {lowest_point}")

        # 获取线1方程
        line1_eq = None
        if points and len(points) >= 2:
            line1_points = points[:2]
            a1 = line1_points[1][1] - line1_points[0][1]
            b1 = line1_points[0][0] - line1_points[1][0]
            c1 = line1_points[1][0] * line1_points[0][1] - line1_points[0][0] * line1_points[1][1]
            line1_eq = (a1, b1, c1)

        if lowest_point and line1_eq:
            a1, b1, c1 = line1_eq
            lx, ly = lowest_point

            # 计算线9方程 (平行于线1，在最低点下方20/scale像素处)
            norm_sq = a1 ** 2 + b1 ** 2  # norm for line 1
            if norm_sq < 1e-10: raise ValueError("Line 1 length is too small")
            norm = math.sqrt(norm_sq)
            pixel_distance = 20 / scale
            pixel_distance = max(5, pixel_distance)
            val_lowest = a1 * lx + b1 * ly
            offset = pixel_distance * norm
            line9_eq = None
            # --- 线9计算逻辑 ---
            if abs(b1) > 1e-10:  # 检查线1是否非垂直
                y_line1 = (-a1 * lx - (val_lowest + offset)) / b1
                y_line2 = (-a1 * lx - (val_lowest - offset)) / b1
                if y_line1 > ly:
                    c9 = -(val_lowest + offset)
                elif y_line2 > ly:
                    c9 = -(val_lowest - offset)
                else:
                    normal_points_down = b1 > 0; c9 = -(val_lowest + offset) if normal_points_down else -(
                                val_lowest - offset)
                if c9 is not None: line9_eq = (a1, b1, c9)
            elif abs(a1) > 1e-10:  # 处理垂直线1
                x_line1 = -(val_lowest + offset) / a1;
                x_line2 = -(val_lowest - offset) / a1
                c9 = -(val_lowest + offset) if x_line1 > lx else -(val_lowest - offset)
                line9_eq = (a1, b1, c9)
            # --- 线9计算结束 ---

            if line9_eq:
                a9, b9, c9 = line9_eq

                # 计算初始圆心：线9上距离最低点最近的点
                denom9_sq = a9 ** 2 + b9 ** 2
                if denom9_sq < 1e-10: raise ValueError("Line 9 length is too small for initial center calc")
                initial_center_x = (-a9 * c9 + b9 ** 2 * lx - a9 * b9 * ly) / denom9_sq
                initial_center_y = (-b9 * c9 - a9 * b9 * lx + a9 ** 2 * ly) / denom9_sq
                initial_center_point = (initial_center_x, initial_center_y)
                print(f"-- 备选方案初始圆心 (线9最近点): ({initial_center_x:.1f}, {initial_center_y:.1f})")

                # 计算固定半径：优先使用等级的 circle_diameter 理想值
                cd_cfg = {}
                try:
                    cd_cfg = dict(CONSTRAINT_IDEALS.get('circle_diameter') or {}) if CONSTRAINT_IDEALS else {}
                except Exception:
                    cd_cfg = {}

                cd_min = cd_cfg.get('min')
                cd_max = cd_cfg.get('max')
                cd_ideal = cd_cfg.get('ideal')

                fixed_diameter_pixels = None
                try:
                    if cd_ideal is not None and float(cd_ideal) > 0:
                        fixed_diameter_pixels = float(cd_ideal)
                except Exception:
                    fixed_diameter_pixels = None

                if fixed_diameter_pixels is None:
                    try:
                        if cd_min is not None and cd_max is not None:
                            fixed_diameter_pixels = (float(cd_min) + float(cd_max)) / 2.0
                    except Exception:
                        fixed_diameter_pixels = None

                if fixed_diameter_pixels is None:
                    fallback_result = None
                    raise ValueError("circle_diameter约束缺失，无法生成备选方案")

                try:
                    if cd_min is not None and fixed_diameter_pixels < float(cd_min):
                        fixed_diameter_pixels = float(cd_min)
                    if cd_max is not None and fixed_diameter_pixels > float(cd_max):
                        fixed_diameter_pixels = float(cd_max)
                except Exception:
                    pass

                fixed_radius_pixels = float(fixed_diameter_pixels) / 2.0

                # 定义内部函数计算备选方案详情
                def calculate_fallback_details(center_pt):
                    try:
                        min_c2 = _cfg_float('MIN_CURVE2_DISTANCE', 2.0)
                        min_c3 = _cfg_float('MIN_CURVE3_DISTANCE', min_c2)

                        # 线6角度（遵循常规方案规则）
                        line1_midpoint = None;
                        line1_angle_deg_calc = None
                        if points and len(points) >= 2: line1_points = points[:2]; line1_midpoint = (
                        (line1_points[0][0] + line1_points[1][0]) / 2,
                        (line1_points[0][1] + line1_points[1][1]) / 2); line1_angle_deg_calc = math.degrees(
                            calculate_line_angle(line1_points[0], line1_points[1]))
                        line6_angle_rad = None
                        if line1_midpoint and line1_angle_deg_calc is not None:
                            is_lowest_point_left = lowest_point[0] < line1_midpoint[
                                0]; angle1_deg = -140 if is_lowest_point_left else -40; line6_angle_rad = math.radians(
                                line1_angle_deg_calc + angle1_deg)
                        else:
                            vec_co_x_orig = lowest_point[0] - center_pt[0]; vec_co_y_orig = lowest_point[1] - center_pt[
                                1];
                        if line6_angle_rad is None and vec_co_x_orig ** 2 + vec_co_y_orig ** 2 > 1e-10: line6_angle_rad = math.atan2(
                            vec_co_y_orig, vec_co_x_orig)
                        if line6_angle_rad is None: return None  # 无法计算线6
                        # 源头统一线6角度（以最低点为外沿点使用同一规则），并统一为负角
                        line6_angle_rad = normalize_line6_angle(center_pt, lowest_point, line6_angle_rad)
                        line6_angle_rad = adjust_negative_angle(line6_angle_rad)
                        line6_angle_deg = math.degrees(line6_angle_rad)
                        # 线7角度（从新圆心到最低点）
                        vec_co_x = lowest_point[0] - center_pt[0];
                        vec_co_y = lowest_point[1] - center_pt[1]
                        if vec_co_x ** 2 + vec_co_y ** 2 < 1e-10: return None  # Center coincides with lowest point
                        line7_angle_rad = math.atan2(vec_co_y, vec_co_x)
                        line7_angle_rad = adjust_negative_angle(line7_angle_rad)
                        line7_angle_deg = math.degrees(line7_angle_rad)

                        # 计算两种覆盖率
                        coverage_angle = calculate_coverage_angle(line6_angle_rad, line7_angle_rad)
                        coverage_horizontal = calculate_coverage_horizontal(lowest_point, center_pt,
                                                                            fixed_radius_pixels, line6_angle_rad,
                                                                            actual_image_width)  # Pass actual_image_width
                        need_cover = coverage_angle < COVERAGE_THRESHOLD

                        # 检查圆到曲线2的距离是否 >= 阈值
                        min_distance_curve2 = calculate_min_distance_circle_to_curve_thread_safe(center_pt, fixed_radius_pixels,
                                                                                                  curve2_img_path, curve_cache, cache_lock=None, image_cache=image_cache)
                        if min_distance_curve2 is None or float(min_distance_curve2) < float(min_c2):
                            return None

                        min_distance_curve2_actual = min_distance_curve2 * scale if min_distance_curve2 is not None else None

                        # 计算距离
                        distance_to_line1 = abs(a1 * center_pt[0] + b1 * center_pt[1] + c1) / norm
                        line4_eq = None;
                        distance_to_line4 = float('inf');
                        if points and len(points) >= 8: line4_points = points[6:8]; a4 = line4_points[1][1] - \
                                                                                         line4_points[0][1]; b4 = \
                        line4_points[0][0] - line4_points[1][0]; c4 = line4_points[1][0] * line4_points[0][1] - \
                                                                      line4_points[0][0] * line4_points[1][
                                                                          1]; line4_eq = (a4, b4, c4);
                        if line4_eq and (a4 ** 2 + b4 ** 2) > 1e-10: distance_to_line4 = abs(
                            a4 * center_pt[0] + b4 * center_pt[1] + c4) / math.sqrt(a4 ** 2 + b4 ** 2)
                        distance_to_line2 = float('inf');
                        distance_to_line3 = float('inf');
                        distance_to_line8 = float('inf');
                        if points and len(points) >= 6:
                            line2_points = points[2:4];
                            a2 = line2_points[1][1] - line2_points[0][1];
                            b2 = line2_points[0][0] - line2_points[1][0];
                            c2 = line2_points[1][0] * line2_points[0][1] - line2_points[0][0] * line2_points[1][1]
                            if (a2 ** 2 + b2 ** 2) > 1e-10: distance_to_line2 = abs(
                                a2 * center_pt[0] + b2 * center_pt[1] + c2) / math.sqrt(a2 ** 2 + b2 ** 2)
                            line3_points = points[4:6];
                            a3 = line3_points[1][1] - line3_points[0][1];
                            b3 = line3_points[0][0] - line3_points[1][0];
                            c3 = line3_points[1][0] * line3_points[0][1] - line3_points[0][0] * line3_points[1][1]
                            if (a3 ** 2 + b3 ** 2) > 1e-10: distance_to_line3 = abs(
                                a3 * center_pt[0] + b3 * center_pt[1] + c3) / math.sqrt(a3 ** 2 + b3 ** 2)
                            line8_p1 = ((points[2][0] + points[3][0]) / 2, (points[2][1] + points[3][1]) / 2);
                            line8_p2 = ((points[4][0] + points[5][0]) / 2, (points[4][1] + points[5][1]) / 2)
                            a8 = line8_p2[1] - line8_p1[1];
                            b8 = line8_p1[0] - line8_p2[0];
                            c8 = line8_p2[0] * line8_p1[1] - line8_p1[0] * line8_p2[1]
                            if (a8 ** 2 + b8 ** 2) > 1e-10: distance_to_line8 = abs(
                                a8 * center_pt[0] + b8 * center_pt[1] + c8) / math.sqrt(a8 ** 2 + b8 ** 2)

                        curve3_img_path = None
                        if FOLDER_C3:
                            curve3_filename = file_name.replace('.png', '') + '_bkx.png'
                            curve3_img_path = os.path.join(FOLDER_C3, curve3_filename)
                            if not os.path.exists(curve3_img_path):
                                curve3_img_path = None

                        min_distance_curve3 = None
                        min_distance_curve3_actual = None
                        if curve3_img_path:
                            min_distance_curve3 = calculate_min_distance_circle_to_curve_thread_safe(center_pt, fixed_radius_pixels,
                                                                                                     curve3_img_path, curve_cache, cache_lock=None, image_cache=image_cache)
                            if min_distance_curve3 is None or float(min_distance_curve3) < float(min_c3):
                                return None
                            min_distance_curve3_actual = min_distance_curve3 * scale

                        actual_diameter = fixed_diameter_pixels * scale;
                        safe_even_diameter = round_to_safe_even_diameter(
                            center_pt,
                            actual_diameter,
                            curve2_img_path,
                            scale,
                            curve_cache,
                            cache_lock=None,
                            image_cache=image_cache,
                            prefer_round_up=True,
                            curve3_img_path=curve3_img_path,
                        )

                        if safe_even_diameter is None or safe_even_diameter < MIN_SAFE_DIAMETER:
                            return None

                        standard_pixel_diameter = safe_even_diameter / scale
                        standard_radius = standard_pixel_diameter / 2
                        min_distance_curve2 = calculate_min_distance_circle_to_curve_thread_safe(center_pt, standard_radius, curve2_img_path, curve_cache, cache_lock=None, image_cache=image_cache)
                        min_distance_curve2_actual = min_distance_curve2 * scale if min_distance_curve2 is not None else None
                        if curve3_img_path:
                            min_distance_curve3 = calculate_min_distance_circle_to_curve_thread_safe(center_pt, standard_radius, curve3_img_path, curve_cache, cache_lock=None, image_cache=image_cache)
                            min_distance_curve3_actual = min_distance_curve3 * scale if min_distance_curve3 is not None else None

                        # 创建结果字典
                        result = {'outer_point': lowest_point, 'center_point': center_pt, 'norm_denom': float(CURRENT_NORM_DENOM or 1.0),
                                  'line6_angle_rad': line6_angle_rad, 'line7_angle_rad': line7_angle_rad,
                                  'line6_angle_deg': line6_angle_deg, 'line7_angle_deg': line7_angle_deg,
                                  'line1_eq': line1_eq, 'line4_eq': line4_eq, 'circle_diameter': fixed_diameter_pixels,
                                  'distance_to_line1': distance_to_line1, 'distance_to_line4': distance_to_line4,
                                  'distance_to_line2': distance_to_line2, 'distance_to_line3': distance_to_line3,
                                  'distance_to_line8': distance_to_line8, 'is_valid': True, 'is_special_fallback': True,
                                  'intersects_curve2': False, 'scale_factor': scale,
                                  # 'coverage_rate': coverage_rate, # 旧键移除
                                  'need_cover': need_cover, 'safe_even_diameter': safe_even_diameter,
                                  'actual_diameter': actual_diameter, 'circle_to_curve2_distance': min_distance_curve2,
                                  'circle_to_curve2_distance_actual': min_distance_curve2_actual,
                                  'circle_to_curve3_distance': min_distance_curve3,
                                  'circle_to_curve3_distance_actual': min_distance_curve3_actual,  # Add curve3 dist
                                  'coverage_rate_angle': coverage_angle,  # 新增角度覆盖率
                                  'coverage_rate_horizontal': coverage_horizontal  # 新增水平覆盖率
                                  }
                        # 评分
                        score = score_solution(result, [])
                        result['final_score'] = score
                        return result
                    except Exception as detail_ex:
                        print(f"-- Error in calculate_fallback_details for center {center_pt}: {detail_ex}")
                        return None

                # --- 内部函数定义结束 ---

                norm9 = math.sqrt(denom9_sq)
                dir_x, dir_y = -b9 / norm9, a9 / norm9
                perp_x, perp_y = a9 / norm9, b9 / norm9

                def composite(r):
                    if not r:
                        return -float('inf')
                    a_cov = r.get('coverage_rate_angle', 0.0)
                    h_cov = r.get('coverage_rate_horizontal', 0.0)
                    return r.get('final_score', 0.0) + 0.3 * (a_cov / 100.0) + 0.2 * (h_cov / 100.0)

                # 粗搜索
                coarse_range_mm = 25.0
                coarse_step_mm = 2.0
                coarse_range_px = coarse_range_mm / scale
                coarse_step_px = coarse_step_mm / scale
                print(f"-- 开始搜索最佳备选圆心 (粗搜索±{coarse_range_mm}mm, 步长{coarse_step_mm}mm)")
                steps = int(coarse_range_px / coarse_step_px)
                for i in range(-steps, steps + 1):
                    off = i * coarse_step_px
                    cx = initial_center_x + off * dir_x
                    cy = initial_center_y + off * dir_y
                    cr = calculate_fallback_details((cx, cy))
                    cs = composite(cr)
                    if cs > best_fallback_score:
                        best_fallback_score = cs
                        best_fallback_result = cr

                # 细化搜索（沿线方向）
                if best_fallback_result is not None:
                    bx, by = best_fallback_result['center_point']
                    refine_range_mm = 4.0
                    refine_step_mm = 0.5
                    refine_range_px = refine_range_mm / scale
                    refine_step_px = refine_step_mm / scale
                    print(f"-- 细化搜索 (沿线±{refine_range_mm}mm, 步长{refine_step_mm}mm)")
                    rsteps = int(refine_range_px / refine_step_px)
                    for i in range(-rsteps, rsteps + 1):
                        off = i * refine_step_px
                        cx = bx + off * dir_x
                        cy = by + off * dir_y
                        cr = calculate_fallback_details((cx, cy))
                        cs = composite(cr)
                        if cs > best_fallback_score:
                            best_fallback_score = cs
                            best_fallback_result = cr

                # 二维微调（垂直方向）
                if best_fallback_result is not None:
                    bx, by = best_fallback_result['center_point']
                    fine_range_mm = 2.0
                    fine_step_mm = 0.5
                    fine_range_px = fine_range_mm / scale
                    fine_step_px = fine_step_mm / scale
                    print(f"-- 二维微调 (垂线±{fine_range_mm}mm, 步长{fine_step_mm}mm)")
                    fsteps = int(fine_range_px / fine_step_px)
                    for i in range(-fsteps, fsteps + 1):
                        for j in range(-fsteps, fsteps + 1):
                            off_d = i * fine_step_px
                            off_p = j * fine_step_px
                            cx = bx + off_d * dir_x + off_p * perp_x
                            cy = by + off_d * dir_y + off_p * perp_y
                            cr = calculate_fallback_details((cx, cy))
                            cs = composite(cr)
                            if cs > best_fallback_score:
                                best_fallback_score = cs
                                best_fallback_result = cr

                # 检查初始点（如果搜索循环未执行或未找到更好的）
                if best_fallback_result is None:
                    print("-- 搜索范围内未找到有效点，尝试计算初始点...")
                    initial_result = calculate_fallback_details(initial_center_point)
                    if initial_result:
                        print(f"-- 使用初始点作为备选方案，评分: {initial_result['final_score']:.4f}")
                        best_fallback_result = initial_result  # 使用初始点结果
                    else:
                        print("-- 初始点也无效（可能与曲线2相交）")

                # 搜索结束后，使用找到的最佳结果
                fallback_result = best_fallback_result

                # 打印最终备选方案信息
                if fallback_result:
                    print(f"-- 找到最佳备选方案，评分: {fallback_result.get('final_score', 0):.4f}")
                    bf_center = fallback_result['center_point']
                    print(f"-- 最佳圆心: ({bf_center[0]:.1f}, {bf_center[1]:.1f})")

                    # Use coverage_rate_angle for "need_cover" and for display here
                    angle_coverage_fallback = fallback_result.get('coverage_rate_angle', 0)  # Get angle coverage
                    print(f"-- 备选方案角度覆盖率: {angle_coverage_fallback:.1f}%")  # Display angle coverage

                    # need_cover in fallback_result should already be set based on its angle coverage during its creation
                    if fallback_result.get('need_cover', False):
                        print(f"-- 角度覆盖率为{angle_coverage_fallback:.1f}% (因小于80%)，需要添加盖子")
                else:
                    print("-- 未找到有效的备选方案")
            else:
                print("\n无法计算线9方程，跳过备选方案")
        else:
            print("\n无法找到曲线1最低点或计算线1方程，跳过备选方案")
    except Exception as e:
        print(f"\n计算备选方案时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        fallback_result = None  # 出错则备选方案为空
    # === 备选方案计算结束 ===
    print(f"步骤7 - 备选方案计算: {(time.time() - step_start_time)*1000:.2f}ms")
    if progress_callback:
        try:
            progress_callback(84)
        except Exception:
            pass

    if not all_regular_results and fallback_result is None:
        print("警告：未找到任何常规方案，且备选方案计算失败或未计算")
        return [], curve_points, actual_image_width  # Return empty results with image_width

    # === 在全局排序前，根据相同外沿点的直径进行局部评分调整 ===
    t_filter0 = _now_ms()
    step_start_time = time.time()
    grouped_results = {}
    for res in all_regular_results:
        op_tuple = tuple(res['outer_point'])  # Use tuple as key
        if op_tuple not in grouped_results:
            grouped_results[op_tuple] = []
        grouped_results[op_tuple].append(res)

    local_bonus_weight = 0.2  # 局部直径奖励的权重，可调整
    epsilon = 1e-6  # 避免除零

    for outer_point, group in grouped_results.items():
        if len(group) <= 1:  # Skip groups with 0 or 1 result
            continue

        # Find min/max safe_diameter in the group (handle None)
        diameters = [res.get('safe_even_diameter') for res in group if res.get('safe_even_diameter') is not None]
        if not diameters:
            continue  # Skip if no valid diameters in the group

        min_diam_group = min(diameters)
        max_diam_group = max(diameters)

        # Only apply bonus if there is a difference in diameters
        if max_diam_group - min_diam_group > epsilon:
            # print(f"  调整外沿点 {outer_point}: MinDiam={min_diam_group}, MaxDiam={max_diam_group}")
            for res in group:
                current_diam = res.get('safe_even_diameter')
                if current_diam is not None:
                    # Calculate bonus (0 to 1, 1 for min diameter, 0 for max diameter)
                    bonus_factor = (current_diam - min_diam_group) / (max_diam_group - min_diam_group + epsilon)
                    bonus_score = max(0, min(1, bonus_factor))  # Clamp between 0 and 1

                    # Add weighted bonus to final score
                    original_score = res.get('final_score', 0)
                    score_adjustment = bonus_score * local_bonus_weight
                    res['final_score'] = original_score + score_adjustment
                    res['scores']['local_diameter_bonus'] = score_adjustment  # Store bonus for potential inspection
                    # print(f"    方案直径 {current_diam}: BonusFactor={bonus_factor:.2f}, ScoreAdj={score_adjustment:.4f} -> NewScore={res['final_score']:.4f}")
    # === 局部评分调整结束 ===
    if progress_callback:
        try:
            progress_callback(85)
        except Exception:
            pass

    # 4. 选择池：优先只选满足约束(is_valid=True)的常规方案；如果一个都没有，再回退使用全部常规方案
    t_sort0 = time.time()
    valid_regular_results = [r for r in all_regular_results if r and r.get('is_valid')]
    select_pool = valid_regular_results if valid_regular_results else all_regular_results

    # 5. 对选择池按调整后的评分从高到低排序
    select_pool.sort(key=lambda x: x.get('final_score', -float('inf')), reverse=True)

    # 6. 合并相似方案
    if target_outer_point is None:
        merged_regular_results = merge_similar_results(select_pool)
    else:
        merged_regular_results = select_pool

    # 7. 选择前5个最佳常规方案
    best_regular_results = merged_regular_results[:5]
    _log_case(file_name, f"常规方案总数: {len(all_regular_results)}，选出方案数: {len(merged_regular_results)}")

    # 7. 准备最终返回的列表
    results_to_return = best_regular_results
    if fallback_result is not None:
        results_to_return.append(fallback_result)

    try:
        _log_case(file_name, f"筛选耗时: {float(_now_ms() - t_filter0):.2f}ms")
    except Exception:
        pass

    # 打印方案详情 (可选，UI会重新计算和显示)
    # for i, result in enumerate(results_to_return):
    #     # ... (打印逻辑可以保留或移除)
    #     pass

    # Return results AND curve1 points AND image_width
    total_time = time.time() - total_start_time
    _log_case(file_name, f"总耗时: {total_time*1000:.2f}ms ({total_time:.3f}s)")
    return results_to_return, curve_points, actual_image_width


def save_best_solution(file_name, results, level=None):
    """将最佳方案保存到文件"""
    if not results:
        print(f"没有可用的方案可供保存: {file_name}")
        return

    # 获取最佳方案（第一个）
    best_result = results[0]

    output_dir = os.path.join('results', file_name)
    os.makedirs(output_dir, exist_ok=True)

    # 保存文本信息
    txt_path = os.path.join(output_dir, f"{file_name}_best.txt")
    try:
        with open(txt_path, 'w', encoding='utf-8') as f:

            f.write(f"评分: {best_result.get('final_score', 0):.4f}\n")
            f.write(
                f"外沿点位置: ({best_result.get('outer_point', (0, 0))[0]:.1f}, {best_result.get('outer_point', (0, 0))[1]:.1f})\n")
            # 写入等级（如果提供）
            if level is not None:
                f.write(f"等级: {level}\n")

            # 计算线6与线7的夹角
            line6_angle_rad = best_result.get('line6_angle_rad', 0)
            line7_angle_rad = best_result.get('line7_angle_rad', 0)
            angle67_rad = (line7_angle_rad - line6_angle_rad + math.pi) % (2 * math.pi) - math.pi
            angle67_deg = abs(math.degrees(angle67_rad))

            # 计算覆盖率
            coverage_rate = ((180.0 - angle67_deg) / 180.0) * 100.0 if angle67_deg <= 180 else 0

            f.write(f"线6角度（相对于水平线）: {best_result.get('line6_angle_deg', 0):.1f}°\n")
            f.write(f"线7角度（相对于水平线）: {best_result.get('line7_angle_deg', 0):.1f}°\n")
            f.write(f"线6与线7夹角: {angle67_deg:.1f}°\n")
            f.write(f"覆盖率 (角度法): {best_result.get('coverage_rate_angle', 0):.1f}%\n")
            f.write(f"覆盖率 (水平距离法): {best_result.get('coverage_rate_horizontal', 0):.1f}%\n")

            # 如果覆盖率低于80%，添加备注 (仍基于角度法)
            if best_result.get('coverage_rate_angle', 100) < COVERAGE_THRESHOLD:
                f.write("备注: 需添加盖子\n")

            scale = best_result.get('scale_factor', 1.0)
            circle_diameter = best_result.get('circle_diameter', 0)
            actual_diameter = circle_diameter * scale

            f.write(f"圆的直径（像素）: {circle_diameter:.2f}\n")
            f.write(f"实际直径: {actual_diameter:.2f}mm\n")

            if 'safe_even_diameter' in best_result and best_result['safe_even_diameter']:
                f.write(f"标准直径: {best_result.get('safe_even_diameter', 0)}mm\n")

            f.write(f"中心点到线1的距离: {best_result.get('distance_to_line1', 0):.2f}\n")
            f.write(f"中心点到线4的距离: {best_result.get('distance_to_line4', 0):.2f}\n")
            f.write(f"中心点到线2的距离: {best_result.get('distance_to_line2', 0):.2f}\n")
            f.write(f"中心点到线3的距离: {best_result.get('distance_to_line3', 0):.2f}\n")
            f.write(f"中心点到线8的距离: {best_result.get('distance_to_line8', 0):.2f}\n")

            if 'circle_to_curve2_distance' in best_result:
                f.write(
                    f"圆到曲线2的最小距离: {best_result.get('circle_to_curve2_distance', 0):.2f}像素, {best_result.get('circle_to_curve2_distance_actual', 0):.2f}mm\n")

        print(f"已保存最佳方案文本信息到: {txt_path}")
    except Exception as e:
        print(f"保存文本信息时出错: {str(e)}")

    # 保存可视化结果图像
    img_path = os.path.join(output_dir, f"{file_name}_best.png")
    try:
        cv2.imwrite(img_path, visualize_results(original_img_path, points[:2], best_result['outer_point'],
                                                best_result['center_point'],
                                                best_result['line6_angle_rad'], best_result['line7_angle_rad'],
                                                best_result['line1_eq'], best_result['line4_eq'],
                                                use_line4_circle=not best_result['is_valid'],
                                                circle_diameter=best_result['circle_diameter'],
                                                scale=scale,
                                                ui_mode=False,
                                                is_special_fallback=best_result['is_special_fallback'],
                                                show_highest_point=True,
                                                show_lowest_point=True))
        print(f"已保存最佳方案图像到: {img_path}")
    except Exception as e:
        print(f"保存图像时出错: {str(e)}")


def calculate_min_distance_circle_to_curve(center_point, radius, curve_img_path, curve_cache={}):
    """
    计算圆到曲线的最小距离

    Args:
        center_point: 圆心坐标
        radius: 圆的半径
        curve_img_path: 曲线图像路径
        curve_cache: 曲线点缓存

    Returns:
        最小距离，如果曲线不存在或计算出错则返回None
    """
    try:
        # 如果曲线图像不存在，返回None
        if not os.path.exists(curve_img_path):
            return None

        # 使用缓存减少重复读取图像
        if curve_img_path in curve_cache and isinstance(curve_cache[curve_img_path], tuple) and len(
                curve_cache[curve_img_path]) >= 1:
            curve_points = curve_cache[curve_img_path][0]
        else:
            # 读取曲线图像
            curve_img = read_image_with_pil(curve_img_path)
            if curve_img is None:
                return None

            # 获取曲线上的所有点
            y_indices, x_indices = np.where(curve_img == 1)
            if len(y_indices) == 0:  # 如果没有找到值为1的点，尝试找白色点
                y_indices, x_indices = np.where(curve_img > 0)

            curve_points = list(zip(x_indices, y_indices))

            if len(curve_points) == 0:
                return None

            # 计算凸包
            points_array = np.array(curve_points).reshape(-1, 2)
            points_array = points_array.astype(np.int32)
            convex_hull = cv2.convexHull(points_array)

            # 保存到缓存
            curve_cache[curve_img_path] = (curve_points, convex_hull)

        # 计算圆心到曲线上各点的距离
        min_distance = float('inf')
        for x, y in curve_points:
            # 计算点到圆心的距离
            dist = math.sqrt((center_point[0] - x) ** 2 + (center_point[1] - y) ** 2)
            # 圆到点的距离 = 点到圆心的距离 - 半径
            point_to_circle = dist - radius  # 如果点在圆内，则距离为负
            # 取所有距离的最小值，但至少为0（点在圆外）
            if point_to_circle < min_distance:
                min_distance = point_to_circle

            # 如果已经找到在圆内的点，提前结束
            if min_distance <= 0:
                return 0

        return max(0, min_distance)  # 确保返回的距离不为负数

    except Exception as e:
        print(f"计算圆到曲线距离时出错: {str(e)}")
        return None


def main():
    """主函数"""
    global FOLDER_A, FOLDER_B, FOLDER_C, FOLDER_C4, FOLDER_C3, FILE_D

    # 设置文件夹路径
    if len(sys.argv) >= 6:
        # 如果提供了命令行参数，使用这些参数作为文件夹路径
        FOLDER_A = sys.argv[1]
        FOLDER_B = sys.argv[2]
        FOLDER_C = sys.argv[3]
        FOLDER_C4 = sys.argv[4]
        FOLDER_C3 = sys.argv[5]
        FILE_D = sys.argv[6]
    else:
        # 否则使用默认路径
        FOLDER_A = DEFAULT_FOLDER_A
        FOLDER_B = DEFAULT_FOLDER_B
        FOLDER_C = DEFAULT_FOLDER_C
        FOLDER_C4 = DEFAULT_FOLDER_C4
        FOLDER_C3 = DEFAULT_FOLDER_C3
        FILE_D = DEFAULT_FILE_D

    print(f"使用以下文件夹路径:")
    print(f"- 原图像文件夹: {FOLDER_A}")
    print(f"- 曲线1图像文件夹: {FOLDER_B}")
    print(f"- 坐标文本文件夹: {FOLDER_C}")
    print(f"- 曲线2图像文件夹: {FOLDER_C4}")
    print(f"- 曲线3图像文件夹: {FOLDER_C3}")
    print(f"- 比例尺文件: {FILE_D}")

    try:
        # 获取所有文件名（不带扩展名）
        file_names = []
        for f in os.listdir(FOLDER_C):
            if f.lower().endswith('.txt'):
                file_names.append(os.path.splitext(f)[0])

        for file_name in file_names:
            print(f"\n处理文件集: {file_name}")

            # 要求用户输入等级
            while True:
                try:
                    level = int(input("请输入等级（1-4）: "))
                    if 1 <= level <= 4:
                        break
                    else:
                        print("错误：等级必须是1-4之间的整数")
                except ValueError:
                    print("错误：请输入有效的数字")

            # 更新约束条件
            update_constraint_ideals(level)
            print(f"已选择等级{level}，使用对应的约束条件")

            try:
                results, _ = process_file_set_adaptive(file_name)  # Get results, ignore curve points here
                if len(results) == 0:
                    print(f"处理完成，但未找到任何可评估的中心点")
                else:
                    valid_count = sum(1 for r in results if r['is_valid'])
                    print(
                        f"处理完成。在所有外沿点位置中找到 {valid_count} 个满足条件的方案，{len(results) - valid_count} 个不满足条件的方案。")
                    print("已显示评分最高的前5个方案。")

                    # 保存最佳方案，写入当前等级
                    save_best_solution(file_name, results, level)
                    print("请在窗口中查看并按任意键继续...")

                # 等待用户按键关闭所有窗口
                if show_individual_windows:  # Only wait if windows were shown
                    cv2.waitKey(0)
                    cv2.destroyAllWindows()

            except Exception as e:
                print(f"处理文件集'{file_name}'时出错: {str(e)}")

    except Exception as e:
        print(f"运行程序时出错: {str(e)}")
        print(f"请确保目录结构正确，并检查以下路径是否存在:")
        print(f"- {FOLDER_A}/（原图像目录）")
        print(f"- {FOLDER_B}/（曲线图像目录）")
        print(f"- {FOLDER_C}/（文本文件目录）")


if __name__ == "__main__":
    main()
