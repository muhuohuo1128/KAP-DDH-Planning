# English interface for KAP-DDH.
# Generated from 方案可视化界面.py; planning logic and saved-data schema are unchanged.

def _crowe_label(value):
    try:
        return ("I", "II", "III", "IV")[int(value) - 1]
    except (TypeError, ValueError, IndexError):
        return str(value)

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


def _cfg_int(key, default):
    try:
        return int(_CONFIG_PARAMS.get(key, default))
    except Exception:
        return int(default)


def _cfg_bool(key, default=False):
    v = _CONFIG_PARAMS.get(key, default)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
    return bool(default)



COVERAGE_THRESHOLD = _cfg_float('COVERAGE_THRESHOLD', 80.0)
MIN_SAFE_DIAMETER = _cfg_float('MIN_SAFE_DIAMETER', 40.0)
MIN_CURVE2_DISTANCE = _cfg_float('MIN_CURVE2_DISTANCE', 0.1)
ZOOM_MIN = _cfg_float('ZOOM_MIN', 0.1)
ZOOM_MAX = _cfg_float('ZOOM_MAX', 10.0)
SAVE_FOLDER = _cfg_path('SAVE_FOLDER', "")
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QScrollArea, QSplitter, QFrame, QPushButton, QFileDialog,
                             QComboBox, QGridLayout, QGroupBox, QCheckBox, QMessageBox,
                             QProgressBar, QShortcut, QAction, QMenu, QWidgetAction)
from PyQt5.QtGui import QPixmap, QImage, QFont, QColor, QPainter, QCursor, QKeySequence
from PyQt5.QtCore import Qt, pyqtSlot, QEvent, QPoint, QUuid, QUrl, QObject, pyqtSignal, QThread
import json
import math
import copy  # Add import copy
import time  # Add time import for timing
from PIL import Image  # Ensure PIL Image is imported

# 导入原有程序中的函数 (Ensure all necessary functions are imported here)
from planning_core import (
    process_file_set_adaptive,
    update_constraint_ideals,
    read_scale_from_excel,
    calculate_min_distance_circle_to_curve,
    calculate_min_distance_circle_to_curve_thread_safe,
    read_points_from_txt,  # Add missing import
    score_solution,  # Ensure score_solution is imported
    CONSTRAINT_IDEALS,  # Ensure CONSTRAINT_IDEALS is imported (if used globally, otherwise keep local import)
    visualize_results,  # Ensure visualize_results is imported
    find_lowest_point,  # Add find_lowest_point import
    find_center_point,  # Add find_center_point import
    round_to_even,  # Add round_to_even import
    calculate_coverage_angle,  # Import coverage calculation
    calculate_coverage_horizontal,  # Import coverage calculation
    normalize_line6_angle,  # Import normalization helper
    adjust_negative_angle  # Import angle adjustment helper
)

import traceback as _traceback
try:
    _traceback.print_exc = lambda *args, **kwargs: None
except Exception:
    pass


def print(*args, **kwargs):
    return


    if not line_eq:
        return float('inf')
    a, b, c = line_eq
    a, b, c = line_eq
    denominator = math.sqrt(a ** 2 + b ** 2)
    if denominator == 0:
        return float('inf')
    return abs(a * point[0] + b * point[1] + c) / denominator


# --- Core Worker for Background Processing ---
class CoreWorker(QObject):
    """在后台线程中运行核心算法并通过信号上报进度和结果"""
    progressChanged = pyqtSignal(int, str)
    finishedWithResults = pyqtSignal(object, object, int)
    errorOccurred = pyqtSignal(str)

    def __init__(self, file_name, use_gpu=False, ignore_angle_constraint=False, parent=None):
        super().__init__(parent)
        self.file_name = file_name
        self.use_gpu = use_gpu
        self.ignore_angle_constraint = ignore_angle_constraint

    def run(self):
        try:
            def cb(val):
                try:
                    self.progressChanged.emit(int(val), "Planning algorithm in progress...")
                except Exception:
                    pass
            start_ts = time.time()
            results, curve1_points, processed_image_width = process_file_set_adaptive(
                self.file_name,
                show_individual_windows=False,
                target_outer_point=None,
                ignore_angle_constraint=self.ignore_angle_constraint,
                use_gpu=self.use_gpu,
                progress_callback=cb,
            )
            if results is None:
                results = []
            # 为单文件生成记录总耗时（毫秒与秒）
            try:
                elapsed_ms = int((time.time() - start_ts) * 1000)
                for r in results:
                    if isinstance(r, dict):
                        r.setdefault('total_time_ms', elapsed_ms)
                        r.setdefault('total_time_seconds', round(elapsed_ms / 1000.0, 3))
            except Exception:
                pass
            self.finishedWithResults.emit(results, curve1_points, processed_image_width)
        except Exception as e:
            self.errorOccurred.emit(str(e))

# --- Batch Worker for Batch Processing ---
class BatchWorker(QObject):
    """在后台线程中执行Batch Process，每个文件完成后通过信号同步到UI"""
    progressChanged = pyqtSignal(int, str)
    fileFinished = pyqtSignal(str, object, int)
    done = pyqtSignal(int, int)
    errorOccurred = pyqtSignal(str)

    def __init__(self, folder_a, folder_b, folder_c, folder_c4, folder_c3, file_d, use_gpu=False, level=0, parent=None):
        super().__init__(parent)
        self.folder_a = folder_a
        self.folder_b = folder_b
        self.folder_c = folder_c
        self.folder_c4 = folder_c4
        self.folder_c3 = folder_c3
        self.file_d = file_d
        self.use_gpu = use_gpu
        self.level = level

    def run(self):
        try:
            import os
            # 更新约束
            update_constraint_ideals(self.level)
            # 打补丁自适应模块全局路径
            import planning_core as adaptive_mod
            adaptive_mod.FOLDER_A = self.folder_a
            adaptive_mod.FOLDER_B = self.folder_b
            adaptive_mod.FOLDER_C = self.folder_c
            adaptive_mod.FOLDER_C4 = self.folder_c4
            adaptive_mod.FOLDER_C3 = self.folder_c3
            adaptive_mod.FILE_D = self.file_d

            # 构建待处理列表（仅包含原图存在的基名）
            txt_files = [f for f in os.listdir(self.folder_c) if f.lower().endswith('.txt')]
            candidate_names = [os.path.splitext(f)[0] for f in txt_files]
            file_names = [fn for fn in candidate_names if os.path.exists(os.path.join(self.folder_a, fn + '.png'))]
            total = len(file_names)
            if total == 0:
                self.done.emit(0, 0)
                return

            success_count = 0
            skip_count = 0
            for idx, fn in enumerate(file_names):
                try:
                    file_start_ts = time.time()
                    results, curve1_points, processed_image_width = process_file_set_adaptive(
                        fn,
                        show_individual_windows=False,
                        target_outer_point=None,
                        ignore_angle_constraint=False,
                        use_gpu=self.use_gpu,
                    )
                    all_results = results or []
                    # 记录该文件的总耗时（毫秒与秒），并确保结果项包含此字段
                    try:
                        file_elapsed_ms = int((time.time() - file_start_ts) * 1000)
                        for r in all_results:
                            if isinstance(r, dict):
                                r.setdefault('total_time_ms', file_elapsed_ms)
                                r.setdefault('total_time_seconds', round(file_elapsed_ms / 1000.0, 3))
                    except Exception:
                        pass
                    if not all_results:
                        skip_count += 1
                    else:
                        # 直接将全量结果发回UI线程，由UI根据展示列表Select评分最高项
                        self.fileFinished.emit(fn, all_results, processed_image_width or 0)
                        success_count += 1
                except Exception as e:
                    skip_count += 1
                    try:
                        self.errorOccurred.emit(f"Batch processing failed for {fn}: {e}")
                    except Exception:
                        pass
                finally:
                    progress = int(((idx + 1) / total) * 100)
                    try:
                        self.progressChanged.emit(progress, f"Batch processing: {progress}% ({idx+1}/{total})")
                    except Exception:
                        pass
            try:
                self.done.emit(success_count, skip_count)
            except Exception:
                pass
        except Exception as e:
            try:
                self.errorOccurred.emit(str(e))
            except Exception:
                pass

# --- Drag Handler Class (Integrated from 移动.py) ---
class DragHandler:
    def __init__(self, ui):
        self.ui = ui  # Reference to the main UI instance (PlanVisualizationUI)

    def handle_event(self, source, event):
        try:
            return self._handle_event_impl(source, event)
        except Exception:
            try:
                self.ui.dragging_outer_point = False
                self.ui.dragging_line5 = False
                self.ui.dragging_semicircle = False
                self.ui.dragging_line6_rotate = False
            except Exception:
                pass
            try:
                self.ui.image_label.unsetCursor()
            except Exception:
                pass
            try:
                self.ui.statusBar().showMessage("Interaction failed")
            except Exception:
                pass
            return False

    def _handle_event_impl(self, source, event):
        """Handles mouse events related to dragging on the image label."""
        # Add print for event type
        # print(f"DragHandler received event: {event.type()} from {source}")
        if source != self.ui.image_label:
            return False  # Not handled

        # --- Mouse Button Press ---
        if event.type() == QEvent.MouseButtonPress:
            print(f"Mouse Press Event at {event.pos()}")  # DEBUG
            if event.button() == Qt.LeftButton and 0 <= self.ui.current_index < len(self.ui.results):
                image_coords_qpoint = self.map_widget_to_image_coords(event.pos())
                print(f"Mapped Image Coords: {image_coords_qpoint}")  # DEBUG
                if image_coords_qpoint:
                    image_coords = (image_coords_qpoint.x(), image_coords_qpoint.y())  # Convert to tuple
                    print(f"Image Coords (tuple): {image_coords}")  # DEBUG
                    current_result = self.ui.results[self.ui.current_index]
                    current_outer_point = current_result.get('outer_point')
                    current_center_point = current_result.get('center_point')
                    line1_eq = current_result.get('line1_eq')  # Get line1 equation
                    line6_angle_rad = current_result.get('line6_angle_rad')

                    self.dragged_plan_method = current_result.get('coverage_method', 'angle')
                    print(
                        f"DEBUG DRAG START: current_method='{current_result.get('coverage_method')}', self.dragged_plan_method='{self.dragged_plan_method}'")  # DEBUG PRINT

                    print(
                        f"Current Outer: {current_outer_point}, Center: {current_center_point}, L1: {line1_eq is not None}, L6: {line6_angle_rad is not None}")  # DEBUG

                    self.ui.dragging_outer_point = False
                    self.ui.dragging_line5 = False
                    self.ui.dragging_semicircle = False
                    self.ui.initial_drag_data = {}  # Clear previous drag data

                    # 1. Check if near outer point
                    if current_outer_point:
                        dist_sq_outer = (image_coords[0] - current_outer_point[0]) ** 2 + \
                                        (image_coords[1] - current_outer_point[1]) ** 2
                        print(f"Checking Outer Point: DistSq={dist_sq_outer:.1f}")  # DEBUG
                        if dist_sq_outer < 100:  # Threshold 10 pixels
                            self.ui.dragging_outer_point = True
                            self.ui.drag_temp_outer_point = current_outer_point
                            self.ui.image_label.setCursor(Qt.ClosedHandCursor)
                            print(f"Dragging Outer Point started near {current_outer_point}")
                            return True  # Handled

                    # 2. Check if near line 5
                    if not self.ui.dragging_outer_point and line1_eq and current_outer_point:
                        # Calculate Line 5 equation (parallel to Line 1 through outer_point)
                        a1, b1, _ = line1_eq
                        c5 = -a1 * current_outer_point[0] - b1 * current_outer_point[1]
                        line5_eq = (a1, b1, c5)
                        dist_to_line5 = calculate_distance_point_to_line(image_coords, line5_eq)
                        print(f"Checking Line 5: Dist={dist_to_line5:.2f}")  # DEBUG
                        if dist_to_line5 < 5.0:  # Threshold 5 pixels for line 5
                            self.ui.dragging_line5 = True
                            self.ui.initial_drag_data['dist_to_line1'] = calculate_distance_point_to_line(image_coords,
                                                                                                          line1_eq)
                            self.ui.initial_drag_data['outer_point'] = current_outer_point
                            self.ui.drag_temp_outer_point = current_outer_point
                            self.ui.image_label.setCursor(Qt.SizeVerCursor)
                            print(
                                f"Dragging Line 5 started. Initial click dist to line1: {self.ui.initial_drag_data.get('dist_to_line1', 0):.2f}")
                            return True  # Handled

                    # 3. Check if near Line 6 for rotation
                    if not self.ui.dragging_outer_point and not self.ui.dragging_line5 and \
                            current_center_point and line6_angle_rad is not None:
                        # Build Line 6 implicit equation through center using its angle
                        nx = -math.sin(line6_angle_rad)
                        ny = math.cos(line6_angle_rad)
                        c6 = -(nx * current_center_point[0] + ny * current_center_point[1])
                        line6_eq = (nx, ny, c6)
                        dist_to_line6 = calculate_distance_point_to_line(image_coords, line6_eq)
                        radius = self.ui.get_standard_radius_for_result(current_result)
                        dist_to_center = math.hypot(image_coords[0] - current_center_point[0], image_coords[1] - current_center_point[1])
                        on_arc_side = self.is_point_on_arc_side(image_coords, current_center_point, line6_angle_rad)
                        print(f"Checking Line 6 Rotation: DistToLine6={dist_to_line6:.2f}, DistToCenter={dist_to_center:.1f}, OnArcSide={on_arc_side}")  # DEBUG
                        # Require click near the diameter at the semicircle boundary to start rotation
                        if dist_to_line6 < 5.0 and radius > 0 and abs(dist_to_center - radius) <= 12.0 and on_arc_side:
                            self.ui.dragging_line6_rotate = True
                            self.ui.initial_drag_data['original_line6_angle_rad'] = line6_angle_rad
                            self.ui.initial_drag_data['line6_center_point'] = current_center_point
                            self.ui.image_label.setCursor(Qt.OpenHandCursor)
                            print("Dragging Line 6 rotation started.")
                            return True

                    # 4. Check if inside semicircle area
                    if not self.ui.dragging_outer_point and not self.ui.dragging_line5 and \
                            current_center_point and line6_angle_rad is not None:
                        radius = self.ui.get_standard_radius_for_result(current_result)  # 使用UI中的方法
                        print(f"Checking Semicircle: Center={current_center_point}, Radius={radius:.1f}")  # DEBUG
                        if radius > 0:
                            dist_to_center = math.sqrt((image_coords[0] - current_center_point[0]) ** 2 + \
                                                       (image_coords[1] - current_center_point[1]) ** 2)
                            on_arc_side = self.is_point_on_arc_side(image_coords, current_center_point, line6_angle_rad)
                            print(f"DistToCenter={dist_to_center:.1f}, OnArcSide={on_arc_side}")  # DEBUG
                            if dist_to_center <= radius and on_arc_side:
                                self.ui.dragging_semicircle = True
                                # Store original Y and X-offset
                                self.ui.initial_drag_data['original_center_y'] = current_center_point[1]
                                self.ui.initial_drag_data['original_center_point_for_semicircle'] = copy.deepcopy(
                                    current_center_point)  # Save original center

                                # Assign a temporary GUID to the plan being dragged
                                dragged_plan_guid = QUuid().toString()
                                current_result['temp_drag_id'] = dragged_plan_guid  # Add to the result dict directly
                                self.ui.initial_drag_data[
                                    'dragged_plan_guid'] = dragged_plan_guid  # Also store in initial_drag_data

                                self.ui.initial_drag_data['original_result_for_semicircle_drag'] = copy.deepcopy(
                                    current_result)  # Save original result (now with temp_drag_id)

                                self.ui.drag_offset = QPoint(int(image_coords[0] - current_center_point[0]),
                                                             0)  # Only X offset matters now
                                self.ui.drag_temp_center_point = current_center_point  # Initialize temp center
                                self.ui.image_label.setCursor(Qt.SizeHorCursor)  # Horizontal movement cursor
                                print(
                                    f"Dragging Semicircle started (Horizontal). Original Y: {self.ui.initial_drag_data['original_center_y']:.1f}, X Offset: {self.ui.drag_offset.x()}")
                                return True
        # --- Mouse Move ---
        elif event.type() == QEvent.MouseMove:
            # print(f"Mouse Move Event at {event.pos()}") # DEBUG (can be very verbose)
            # Dragging Outer Point
            if self.ui.dragging_outer_point:
                # print("Dragging Outer Point...") # DEBUG
                image_coords_qpoint = self.map_widget_to_image_coords(event.pos())
                if image_coords_qpoint and self.ui.curve1_points:
                    target_y = image_coords_qpoint.y()
                    closest_point = min(self.ui.curve1_points, key=lambda p: abs(p[1] - target_y))
                    self.ui.drag_temp_outer_point = closest_point
                    # 更新临时线5和交点
                    self._update_temp_line5(closest_point)
                    # print(f"Dragging Outer Point to curve point: {closest_point}") # Debug
                return True

            # Dragging Line 5
            elif self.ui.dragging_line5:
                # print("Dragging Line 5...") # DEBUG
                image_coords_qpoint = self.map_widget_to_image_coords(event.pos())
                current_result = self.ui.results[self.ui.current_index]
                line1_eq = current_result.get('line1_eq')

                if image_coords_qpoint and line1_eq and self.ui.curve1_points:
                    image_coords = (image_coords_qpoint.x(), image_coords_qpoint.y())
                    # Calculate the current mouse position's distance to Line 1
                    current_mouse_dist_to_line1 = calculate_distance_point_to_line(image_coords, line1_eq)

                    # Find the curve point whose distance to Line 1 is closest to the mouse distance
                    closest_curve_point = min(self.ui.curve1_points, key=lambda p: abs(
                        calculate_distance_point_to_line(p, line1_eq) - current_mouse_dist_to_line1))

                    self.ui.drag_temp_outer_point = closest_curve_point
                    # 更新临时线5和交点
                    self._update_temp_line5(closest_curve_point)
                    # print(f"Dragging Line 5, targeting curve point: {closest_curve_point} (Dist to L1: {calculate_distance_point_to_line(closest_curve_point, line1_eq):.2f})") # Debug
                return True

            # Dragging Line 6 Rotation
            elif self.ui.dragging_line6_rotate:
                try:
                    image_coords_qpoint = self.map_widget_to_image_coords(event.pos())
                    if not image_coords_qpoint: return True
                    current_result = self.ui.results[self.ui.current_index]
                    center_point = current_result.get('center_point')
                    outer_point = current_result.get('outer_point')
                    line7_angle_rad = current_result.get('line7_angle_rad')  # Keep original line7 angle
                    if center_point and outer_point and line7_angle_rad is not None:
                        mx = image_coords_qpoint.x() - center_point[0]
                        my = image_coords_qpoint.y() - center_point[1]
                        new_angle_rad = math.atan2(my, mx)
                        # 归一化线6角度，确保半圆开口侧一致，并统一为负角表示
                        normalized_angle_rad = normalize_line6_angle(center_point, outer_point, new_angle_rad)
                        normalized_angle_rad = adjust_negative_angle(normalized_angle_rad)
                        current_result['line6_angle_rad'] = normalized_angle_rad
                        # 线6角度以 [-180, 180] 输出
                        current_result['line6_angle_deg'] = math.degrees(normalized_angle_rad)
                        # line7_angle_rad remains unchanged during line6 rotation
                        # Update coverage metrics
                        try:
                            coverage_angle_temp = calculate_coverage_angle(normalized_angle_rad, line7_angle_rad)
                            current_result['coverage_rate_angle'] = coverage_angle_temp
                            active_image_width = self.ui.current_image_width
                            radius = self.ui.get_standard_radius_for_result(current_result)
                            if radius and radius > 0:
                                coverage_horizontal_temp = calculate_coverage_horizontal(outer_point, center_point, radius, normalized_angle_rad, active_image_width)
                                current_result['coverage_rate_horizontal'] = coverage_horizontal_temp
                        except Exception as e_cov:
                            print(f"Rotation coverage update error: {e_cov}")
                        # Refresh visualization and details
                        self.ui.update_image()
                        self.ui.update_details()
                except Exception as e:
                    print(f"Line 6 rotation error: {e}")
                    # Reset dragging state on error
                    self.ui.dragging_line6_rotate = False
                    self.ui.image_label.unsetCursor()
                return True

            # Dragging Semicircle (Horizontal Only)
            elif self.ui.dragging_semicircle:
                # print("Dragging Semicircle...") # DEBUG
                image_coords_qpoint = self.map_widget_to_image_coords(event.pos())
                if not image_coords_qpoint: return True  # Exit if mapping fails

                current_result = self.ui.results[
                    self.ui.current_index]  # This is the original result before drag modification
                original_outer_point = current_result.get('outer_point')
                line6_angle_rad = current_result.get('line6_angle_rad')
                radius = self.ui.get_standard_radius_for_result(current_result)
                scale = current_result.get('scale_factor', 1.0)
                curve2_filename = self.ui.current_file.replace('.png', '') + '_bks.png'
                curve2_img_path = os.path.join(self.ui.folder_c4, curve2_filename)  # Use ui.folder_c4
                original_center_y = self.ui.initial_drag_data.get('original_center_y')

                if original_outer_point and line6_angle_rad is not None and radius > 0 and original_center_y is not None:
                    image_coords = (image_coords_qpoint.x(), image_coords_qpoint.y())
                    # Calculate potential new X, keep original Y
                    potential_center_x = image_coords[0] - self.ui.drag_offset.x()
                    potential_center_y = original_center_y
                    potential_center = (potential_center_x, potential_center_y)

                    # Always update temp center point for smooth visual feedback
                    self.ui.drag_temp_center_point = potential_center

                    # --- Check Constraints ---
                    constraints_met = True  # Assume true initially
                    coverage_rate_angle_temp = 0
                    coverage_rate_horizontal_temp = 0
                    min_dist_curve2 = float('inf')
                    method = current_result.get('coverage_method', 'angle')

                    try:
                        vec_co_x = original_outer_point[0] - potential_center[0]
                        vec_co_y = original_outer_point[1] - potential_center[1]
                        potential_line7_angle_rad = math.atan2(vec_co_y, vec_co_x)
                        potential_line7_angle_rad = adjust_negative_angle(potential_line7_angle_rad)
                        coverage_rate_angle_temp = calculate_coverage_angle(line6_angle_rad, potential_line7_angle_rad)

                        active_image_width = self.ui.current_image_width
                        if active_image_width <= 0: print(
                            "Warning: DragHandler.handle_event using invalid image_width for horizontal coverage.")
                        coverage_rate_horizontal_temp = calculate_coverage_horizontal(original_outer_point,
                                                                                      potential_center, radius,
                                                                                      line6_angle_rad,
                                                                                      active_image_width)
                    except Exception as e:
                        print(f"Error calculating coverage during drag: {e}")
                        constraints_met = False

                    if constraints_met:
                        if method == 'angle':
                            if coverage_rate_angle_temp < COVERAGE_THRESHOLD: constraints_met = False
                        elif method == 'horizontal':
                            if coverage_rate_horizontal_temp < COVERAGE_THRESHOLD: constraints_met = False

                    if constraints_met:
                        if not (0.0 <= coverage_rate_horizontal_temp <= 100.0): constraints_met = False

                    if constraints_met:
                        try:
                            min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(
                                potential_center, radius, curve2_img_path, self.ui.curve_cache, None, self.ui.image_cache)
                            if min_dist_curve2 is None or min_dist_curve2 <= MIN_CURVE2_DISTANCE: constraints_met = False
                        except Exception as e:
                            print(f"Error checking curve distance constraint: {e}")
                            constraints_met = False

                    # Always update visualization and details, passing the constraints_met status
                    self._update_temporary_visualization(self.ui.drag_temp_center_point, constraints_met)
                    self._update_details_temporarily(self.ui.drag_temp_center_point, constraints_met)
                return True

        # --- Mouse Button Release ---
        elif event.type() == QEvent.MouseButtonRelease:
            print(f"Mouse Release Event at {event.pos()}")  # DEBUG
            if event.button() == Qt.LeftButton:
                # Release Outer Point Drag
                if self.ui.dragging_outer_point:
                    print("Releasing Outer Point Drag")  # DEBUG
                    self.ui.dragging_outer_point = False
                    self.ui.image_label.unsetCursor()
                    self.ui.revert_btn.setEnabled(True)  # Enable revert after drag attempt
                    new_outer_point = self.ui.drag_temp_outer_point
                    self.ui.drag_temp_outer_point = None  # Clear temp point
                    # 清除临时线5数据
                    self.ui.temp_line5_eq = None
                    self.ui.temp_line5_intersection = None
                    # Get original outer point for comparison
                    original_outer_point = self.ui.results[self.ui.current_index].get('outer_point')
                    if new_outer_point and new_outer_point != original_outer_point:
                        print(f"Outer Point drag released, recalculating for: {new_outer_point}")
                        self._recalculate_with_new_outer_point(new_outer_point)
                    else:
                        print("Outer Point drag released, point unchanged.")
                        # Even if unchanged, refresh visualization to remove temp elements
                        self._update_temporary_visualization()
                    return True

                # Release Line 5 Drag
                elif self.ui.dragging_line5:
                    print("Releasing Line 5 Drag")  # DEBUG
                    self.ui.dragging_line5 = False
                    self.ui.image_label.unsetCursor()
                    self.ui.revert_btn.setEnabled(True)  # Enable revert after drag attempt
                    new_outer_point = self.ui.drag_temp_outer_point
                    self.ui.drag_temp_outer_point = None  # Clear temp point
                    # 清除临时线5数据
                    self.ui.temp_line5_eq = None
                    self.ui.temp_line5_intersection = None
                    original_outer_point = self.ui.initial_drag_data.get('outer_point')  # Get original from drag start
                    self.ui.initial_drag_data = {}  # Clear initial data
                    if new_outer_point and new_outer_point != original_outer_point:
                        print(f"Line 5 drag released, recalculating for curve point: {new_outer_point}")
                        self._recalculate_with_new_outer_point(new_outer_point)
                    else:
                        print("Line 5 drag released, point unchanged.")
                        # Even if unchanged, refresh visualization to remove temp elements
                        self._update_temporary_visualization()
                    return True

                # Release Line 6 Rotation
                elif self.ui.dragging_line6_rotate:
                    print("Releasing Line 6 Rotation")  # DEBUG
                    self.ui.dragging_line6_rotate = False
                    self.ui.image_label.unsetCursor()
                    self.ui.revert_btn.setEnabled(True)
                    # Commit visualization refresh
                    self.ui.update_image()
                    self.ui.update_details()
                    return True

                # Release Semicircle Drag
                elif self.ui.dragging_semicircle:
                    print("Releasing Semicircle Drag")  # DEBUG
                    self.ui.dragging_semicircle = False
                    self.ui.image_label.unsetCursor()  # Reset cursor
                    self.ui.revert_btn.setEnabled(True)  # Enable revert after drag attempt

                    final_center_point = self.ui.drag_temp_center_point  # This is the position where mouse was released
                    original_center_for_comparison = self.ui.initial_drag_data.get(
                        'original_center_point_for_semicircle')
                    original_result_for_drag = self.ui.initial_drag_data.get('original_result_for_semicircle_drag')

                    self.ui.drag_temp_center_point = None  # Clear temp point for next drag or if this one is invalid
                    self.ui.drag_offset = QPoint(0, 0)  # Reset offset
                    # initial_drag_data will be cleared at the end

                    if final_center_point and original_result_for_drag:  # Ensure we have data to work with
                        # --- Perform a final, strict constraint check at the release position ---
                        is_final_position_valid = True  # Assume true initially
                        current_result_copy = copy.deepcopy(
                            original_result_for_drag)  # Use a copy of the original state for checking

                        # Get necessary parameters from the original result state
                        original_outer_point_for_check = current_result_copy.get('outer_point')
                        line6_angle_rad_for_check = current_result_copy.get('line6_angle_rad')
                        radius_for_check = self.ui.get_standard_radius_for_result(current_result_copy)
                        # scale_for_check = current_result_copy.get('scale_factor', 1.0)
                        curve2_filename_for_check = self.ui.current_file.replace('.png', '') + '_bks.png'
                        curve2_img_path_for_check = os.path.join(self.ui.folder_c4, curve2_filename_for_check)
                        method_for_check = current_result_copy.get('coverage_method', 'angle')
                        active_image_width_for_check = self.ui.current_image_width

                        coverage_angle_final = 0
                        coverage_horizontal_final = 0

                        try:
                            if original_outer_point_for_check and line6_angle_rad_for_check and radius_for_check > 0:
                                vec_co_x = original_outer_point_for_check[0] - final_center_point[0]
                                vec_co_y = original_outer_point_for_check[1] - final_center_point[1]
                                final_line7_angle_rad = math.atan2(vec_co_y, vec_co_x)
                                final_line7_angle_rad = adjust_negative_angle(final_line7_angle_rad)
                                coverage_angle_final = calculate_coverage_angle(line6_angle_rad_for_check,
                                                                                final_line7_angle_rad)

                                if active_image_width_for_check <= 0: print(
                                    "Warning: DragRelease final check using invalid image_width.")
                                coverage_horizontal_final = calculate_coverage_horizontal(
                                    original_outer_point_for_check, final_center_point, radius_for_check,
                                    line6_angle_rad_for_check, active_image_width_for_check)
                            else:
                                is_final_position_valid = False  # Essential data missing for check
                        except Exception as e_check:
                            print(f"Error during final constraint check (coverage): {e_check}")
                            is_final_position_valid = False

                        if is_final_position_valid:
                            if method_for_check == 'angle':
                                if coverage_angle_final < COVERAGE_THRESHOLD: is_final_position_valid = False
                            elif method_for_check == 'horizontal':
                                if coverage_horizontal_final < COVERAGE_THRESHOLD: is_final_position_valid = False

                        if is_final_position_valid:
                            if not (0.0 <= coverage_horizontal_final <= 100.0): is_final_position_valid = False

                        if is_final_position_valid:
                            try:
                                min_dist_curve2_final = calculate_min_distance_circle_to_curve_thread_safe(
                                    final_center_point, radius_for_check, curve2_img_path_for_check,
                                    self.ui.curve_cache, None, self.ui.image_cache)
                                if min_dist_curve2_final is None or min_dist_curve2_final <= MIN_CURVE2_DISTANCE:
                                    is_final_position_valid = False
                            except Exception as e_dist_check:
                                print(f"Error during final constraint check (distance): {e_dist_check}")
                                is_final_position_valid = False
                        # --- End of final constraint check ---

                        if is_final_position_valid:
                            # Check if the center point actually changed significantly
                            if original_center_for_comparison and \
                                    math.sqrt((final_center_point[0] - original_center_for_comparison[0]) ** 2 + (
                                            final_center_point[1] - original_center_for_comparison[1]) ** 2) > 1e-3:
                                print(
                                    f"Semicircle drag released. Final position VALID. Updating result with final center: {final_center_point}")
                                self._update_result_after_drag(
                                    final_center_point)  # This updates self.ui.results[self.ui.current_index]
                                # self.ui.update_ui() # update_result_after_drag will call update_plan_list which updates UI
                            else:
                                print(
                                    "Semicircle drag released. Final position VALID, but center unchanged or very close to original. No update.")
                                # Even if no change, refresh UI to ensure correct (non-red) final display
                                self.ui.update_image()
                                self.ui.update_details()
                        else:
                            print("Semicircle drag released. Final position INVALID. Reverting to original state.")
                            # --- Print detailed constraint failures for diagnostics ---
                            try:
                                # Prepare inputs
                                current_file = self.ui.current_file
                                txt_path = os.path.join(self.ui.folder_c, f'{current_file}.txt')
                                points = read_points_from_txt(txt_path)
                                curve2_filename = current_file.replace('.png', '') + '_bks.png'
                                curve2_img_path = os.path.join(self.ui.folder_c4, curve2_filename)

                                # Use original result data for parameters
                                ref_result = original_result_for_drag if original_result_for_drag else self.ui.results[self.ui.current_index]
                                outer_point = ref_result.get('outer_point')
                                line6_angle_rad = ref_result.get('line6_angle_rad')
                                radius = self.ui.get_standard_radius_for_result(ref_result)
                                active_image_width = self.ui.current_image_width

                                # Compute UI constraints (coverage and curve2 distance)
                                ui_msgs = []
                                if final_center_point and outer_point and line6_angle_rad is not None and radius and radius > 0:
                                    try:
                                        vec_x = outer_point[0] - final_center_point[0]
                                        vec_y = outer_point[1] - final_center_point[1]
                                        line7_angle_rad = math.atan2(vec_y, vec_x)
                                        line7_angle_rad = adjust_negative_angle(line7_angle_rad)
                                        coverage_angle = calculate_coverage_angle(line6_angle_rad, line7_angle_rad)
                                        ui_msgs.append(f"覆盖角度: 实际 {coverage_angle:.2f}°, 需求 ≥ {COVERAGE_THRESHOLD:.2f}°")
                                        if coverage_angle < COVERAGE_THRESHOLD:
                                            print(f"约束未通过: 覆盖角度不足 (实际 {coverage_angle:.2f}°, 需求 ≥ {COVERAGE_THRESHOLD:.2f}°)")
                                    except Exception as e_cov:
                                        print(f"覆盖角度计算失败: {e_cov}")

                                    try:
                                        if active_image_width <= 0:
                                            print("Warning: invalid image width for horizontal coverage during release diagnostics.")
                                        coverage_h = calculate_coverage_horizontal(outer_point, final_center_point, radius, line6_angle_rad, active_image_width)
                                        ui_msgs.append(f"水平Acetabular cup bone coverage: 实际 {coverage_h:.2f}%, 需求 ≥ {COVERAGE_THRESHOLD:.2f}%")
                                        if coverage_h < COVERAGE_THRESHOLD:
                                            print(f"约束未通过: 水平Cup bone coverage不足 (实际 {coverage_h:.2f}%, 需求 ≥ {COVERAGE_THRESHOLD:.2f}%)")
                                    except Exception as e_h:
                                        print(f"水平Cup bone coverage计算失败: {e_h}")

                                    try:
                                        min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(final_center_point, radius, curve2_img_path, self.ui.curve_cache, None, self.ui.image_cache)
                                        if min_dist_curve2 is None:
                                            print("约束未通过: 圆到曲线2最小距离无效 (None)")
                                        else:
                                            ui_msgs.append(f"圆到曲线2距离: 实际 {min_dist_curve2:.4f}  px, 需求 > {MIN_CURVE2_DISTANCE:.4f}  px")
                                            if min_dist_curve2 <= MIN_CURVE2_DISTANCE:
                                                print(f"约束未通过: 圆到曲线2距离不足 (实际 {min_dist_curve2:.4f}  px, 需求 > {MIN_CURVE2_DISTANCE:.4f}  px)")
                                    except Exception as e_c2:
                                        print(f"曲线2距离计算失败: {e_c2}")

                                # Compute global constraints (CONSTRAINT_IDEALS)
                                if points and final_center_point and outer_point:
                                    try:
                                        ok, distances = check_point_constraints(final_center_point, outer_point, points)
                                        cons = CONSTRAINT_IDEALS
                                        def _fmt_check(name, val, lo, hi):
                                            status = "合格" if lo <= val <= hi else "不合格"
                                            print(f"约束{status}: {name} 实际 {val:.2f}, 允许范围 [{lo:.2f}, {hi:.2f}]")
                                        if cons is not None and distances:
                                            _fmt_check('circle_diameter', distances.get('circle_diameter', 0), cons['circle_diameter']['min'], cons['circle_diameter']['max'])
                                            _fmt_check('distance_to_line1', distances.get('distance_to_line1', 0), cons['distance_to_line1']['min'], cons['distance_to_line1']['max'])
                                            _fmt_check('distance_to_line4', distances.get('distance_to_line4', 0), cons['distance_to_line4']['min'], cons['distance_to_line4']['max'])
                                            _fmt_check('distance_to_line2', distances.get('distance_to_line2', 0), cons['distance_to_line2']['min'], cons['distance_to_line2']['max'])
                                            _fmt_check('distance_to_line3', distances.get('distance_to_line3', 0), cons['distance_to_line3']['min'], cons['distance_to_line3']['max'])
                                            _fmt_check('distance_to_line8', distances.get('distance_to_line8', 0), cons['distance_to_line8']['min'], cons['distance_to_line8']['max'])
                                    except Exception as e_cons:
                                        print(f"全局约束计算失败: {e_cons}")
                            except Exception as e_diag:
                                print(f"Failed to print invalid-drag diagnostics: {e_diag}")

                            QMessageBox.warning(self.ui, "Invalid drag position", "The selected drag position does not meet the geometric constraints. The change has been cancelled.")
                            # Revert to the original result state for the current index
                            if original_result_for_drag:
                                self.ui.results[self.ui.current_index] = original_result_for_drag
                            # Refresh the UI to show the reverted state
                            self.ui.update_image()
                            self.ui.update_details()

                    # Ensure final details are displayed correctly using the standard method
                    self.ui.update_details()

                    # Clean up temp_drag_id from the potentially modified or restored result in self.ui.results
                    if self.ui.current_index >= 0 and self.ui.current_index < len(self.ui.results):
                        current_plan_in_results = self.ui.results[self.ui.current_index]
                        if 'temp_drag_id' in current_plan_in_results:
                            del current_plan_in_results['temp_drag_id']
                            print(f"Cleaned up temp_drag_id from results index {self.ui.current_index}")

                    self.ui.initial_drag_data = {}  # Clear all drag data
                    return True

        # If none of the above handled the event
        return False

    # --- Helper Methods (Moved from PlanVisualizationUI) ---

    def map_widget_to_image_coords(self, widget_pos):
        """Maps QPoint from image_label widget coordinates to original image coordinates."""
        if not self.ui.original_pixmap or self.ui.original_pixmap.isNull():
            return None

        # Get the pixmap currently displayed (it might be scaled)
        current_pixmap = self.ui.image_label.pixmap()
        if not current_pixmap or current_pixmap.isNull():
            return None

        # Calculate the actual geometry of the displayed pixmap within the label
        label_size = self.ui.image_label.size()
        pixmap_size = current_pixmap.size()

        # Account for alignment (Qt.AlignCenter)
        x_offset = (label_size.width() - pixmap_size.width()) / 2
        y_offset = (label_size.height() - pixmap_size.height()) / 2

        # Adjust widget position relative to the pixmap's top-left corner
        pixmap_x = widget_pos.x() - x_offset
        pixmap_y = widget_pos.y() - y_offset

        # Check if the click is within the pixmap bounds
        if not (0 <= pixmap_x < pixmap_size.width() and 0 <= pixmap_y < pixmap_size.height()):
            return None

        # Map coordinates from the displayed (potentially scaled) pixmap to the original pixmap
        original_width = self.ui.original_pixmap.width()
        original_height = self.ui.original_pixmap.height()

        image_x = (pixmap_x / pixmap_size.width()) * original_width
        image_y = (pixmap_y / pixmap_size.height()) * original_height

        return QPoint(int(image_x), int(image_y))

    def is_point_on_arc_side(self, point, center, line6_angle_rad):
        """Check if a point is on the correct side of the semicircle diameter (line 6)."""
        try:
            # 当前索引的结果
            if self.ui.current_index < 0 or self.ui.current_index >= len(self.ui.results):
                return False

            result = self.ui.results[self.ui.current_index]
            outer_point = result.get('outer_point')

            if not outer_point:
                return False

            # 线6的方向向量
            line6_dx = math.cos(line6_angle_rad)
            line6_dy = math.sin(line6_angle_rad)

            # 从中心点到外沿点的向量
            outer_dx = outer_point[0] - center[0]
            outer_dy = outer_point[1] - center[1]

            # 从中心点到点击点的向量
            point_dx = point[0] - center[0]
            point_dy = point[1] - center[1]

            # 计算垂直于线6的向量（顺时针旋转90度）
            perp_dx = line6_dy
            perp_dy = -line6_dx

            # 计算外沿点与垂直向量的点积，确定外沿点在哪一侧
            outer_dot = outer_dx * perp_dx + outer_dy * perp_dy

            # 如果外沿点与垂直向量点积为负，需要反转垂直向量
            if outer_dot < 0:
                perp_dx = -perp_dx
                perp_dy = -perp_dy

            # 计算点击点与垂直向量的点积
            point_dot = point_dx * perp_dx + point_dy * perp_dy

            # 如果点积为正，则点击点在外沿点同侧，即半圆弧线侧
            return point_dot >= 0

        except Exception as e:
            print(f"Error in is_point_on_arc_side: {e}")
            return False

    def _update_temporary_visualization(self, temp_center_point=None, constraints_met=True):
        """Update the visualization with a temporary center point or line 5."""
        if self.ui.current_index < 0 or self.ui.current_index >= len(self.ui.results):
            return

        result = self.ui.results[self.ui.current_index]
        visibility_flags = self.ui._get_visibility_flags()  # Use UI's method to get flags

        # Determine drawing colors based on constraints_met for semicircle drag
        center_color = (0, 255, 0)  # Default Green for center
        semicircle_color = (0, 255, 0)  # Default Green for semicircle
        if self.ui.dragging_semicircle and not constraints_met:
            center_color = (0, 0, 255)  # Red for center if drag invalid
            semicircle_color = (0, 0, 255)  # Red for semicircle if drag invalid

        try:
            original_img_path = os.path.join(self.ui.folder_a, f'{self.ui.current_file}.png')  # Use ui.folder_a
            txt_path = os.path.join(self.ui.folder_c, f'{self.ui.current_file}.txt')  # Use ui.folder_c
            points = read_points_from_txt(txt_path)

            if points:
                # 获取方案参数
                center_point = result['center_point']  # Original center for some calculations if needed
                outer_point = result['outer_point']
                line6_angle = result['line6_angle_rad']
                # Calculate line 7 angle based on temp center if dragging semicircle
                if self.ui.dragging_semicircle and temp_center_point:
                    vec_co_x = outer_point[0] - temp_center_point[0]
                    vec_co_y = outer_point[1] - temp_center_point[1]
                    line7_angle = math.atan2(vec_co_y, vec_co_x)
                    line7_angle = adjust_negative_angle(line7_angle)
                else:
                    line7_angle = result['line7_angle_rad']  # Otherwise use original

                line1_eq = result['line1_eq']
                line4_eq = result.get('line4_eq', None)
                # Use standard diameter if available, otherwise calculated pixel diameter for display
                circle_diameter = result.get('circle_diameter')
                standard_diameter = result.get('safe_even_diameter')
                scale = result.get('scale_factor', 1.0)
                if standard_diameter is not None and scale > 0:
                    display_diameter = standard_diameter / scale
                else:
                    display_diameter = circle_diameter

                is_special_fallback = result.get('is_special_fallback', False)
                # is_using_line4_circle is based on validity for non-fallback, but fallback might be valid
                # Let visualize_results handle the circle logic based on diameter/line equations passed

                # Determine which center point to use for display
                display_center = temp_center_point if temp_center_point else center_point
                display_outer = self.ui.drag_temp_outer_point if self.ui.dragging_outer_point or self.ui.dragging_line5 else outer_point

                # Generate image with overridden points if needed
                result_img = visualize_results(
                    original_img_path, points[:2], outer_point, center_point,  # Pass original points for calculations
                    line6_angle, line7_angle, line1_eq, line4_eq,
                    # use_line4_circle parameter removed, let visualize handle it
                    circle_diameter=display_diameter,  # Pass the diameter to be drawn
                    scale=scale,
                    ui_mode=True,
                    visibility_flags=visibility_flags,
                    override_center_point=display_center,  # Override displayed center
                    override_outer_point=display_outer,  # Override displayed outer point
                    is_special_fallback=is_special_fallback,
                    show_highest_point=visibility_flags.get('highest_point', False),
                    show_lowest_point=visibility_flags.get('lowest_point', False),
                    # Pass colors for semicircle drag
                    center_color_override=center_color if self.ui.dragging_semicircle else (0, 255, 0),
                    # Green if not dragging semicircle
                    semicircle_color_override=semicircle_color if self.ui.dragging_semicircle else (0, 255, 0)
                    # Green if not dragging semicircle
                )

                # 绘制白色虚线和蓝色交点 (线5拖拽)
                if self.ui.temp_line5_eq and (self.ui.dragging_line5 or self.ui.dragging_outer_point):
                    # 获取图像大小
                    h, w = result_img.shape[:2]

                    # 解析临时线5方程
                    a, b, c = self.ui.temp_line5_eq

                    # 计算线段端点 (从图像左侧到右侧)
                    if b != 0:
                        # y = (-ax - c) / b
                        x1, x2 = 0, w - 1
                        y1_f = (-a * x1 - c) / b
                        y2_f = (-a * x2 - c) / b
                        # Clip y values to image boundaries
                        y1 = max(0, min(h - 1, int(y1_f)))
                        y2 = max(0, min(h - 1, int(y2_f)))
                        # Recalculate x if y was clipped (optional, for precision)
                        if a != 0:
                            if y1_f != y1: x1 = int((-b * y1 - c) / a)
                            if y2_f != y2: x2 = int((-b * y2 - c) / a)
                        x1 = max(0, min(w - 1, x1))
                        x2 = max(0, min(w - 1, x2))

                    elif a != 0:
                        # 垂直线 x = -c / a
                        x1 = x2 = max(0, min(w - 1, int(-c / a)))
                        y1, y2 = 0, h - 1
                    else:  # Should not happen for valid lines
                        x1, y1, x2, y2 = 0, 0, 0, 0

                    # 绘制白色虚线 (5 px的虚线)
                    cv2.line(result_img, (x1, y1), (x2, y2), (255, 255, 255), 1, cv2.LINE_AA)  # Thinner line

                    # 绘制蓝色交点 (如果存在)
                    if self.ui.temp_line5_intersection:
                        x, y = self.ui.temp_line5_intersection
                        # 绘制蓝色小圆点
                        cv2.circle(result_img, (int(x), int(y)), 5, (255, 0, 0), -1)  # Blue color

                # 转换为QPixmap
                height, width, channel = result_img.shape
                bytes_per_line = 3 * width
                result_img_rgb = cv2.cvtColor(result_img, cv2.COLOR_BGR2RGB)
                q_img = QImage(result_img_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(q_img)

                # Directly update label, bypassing original_pixmap for temporary display
                if self.ui.original_pixmap:  # Keep original aspect ratio/zoom basis
                    new_width = int(self.ui.original_pixmap.width() * self.ui.zoom_factor)
                    new_height = int(self.ui.original_pixmap.height() * self.ui.zoom_factor)
                    scaled_pixmap = pixmap.scaled(new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.ui.image_label.setPixmap(scaled_pixmap)
                else:  # Fallback if original not loaded yet
                    self.ui.image_label.setPixmap(pixmap)

            else:
                print("Temporary visualization failed: Could not read points.")
        except Exception as e:
            print(f"Error during temporary visualization: {e}")
            import traceback
            traceback.print_exc()

    def _update_details_temporarily(self, temp_center_point, constraints_met=True):
        """使用临时中心点实时更新详情面板"""
        if self.ui.current_index < 0 or self.ui.current_index >= len(self.ui.results):
            return

        result = self.ui.results[self.ui.current_index]
        original_outer_point = result.get('outer_point')
        line1_eq = result.get('line1_eq')
        line6_angle_rad = result.get('line6_angle_rad')
        scale = result.get('scale_factor', 1.0)
        radius = self.ui.get_standard_radius_for_result(result)  # 使用UI类中的方法
        curve2_filename = self.ui.current_file.replace('.png', '') + '_bks.png'
        curve2_img_path = os.path.join(self.ui.folder_c4, curve2_filename)  # Use ui.folder_c4

        if not all([original_outer_point, line1_eq, line6_angle_rad is not None, radius > 0]):
            # Cannot calculate temporary details if essential original data is missing
            return

        drag_status_text = ""
        if self.ui.dragging_semicircle and not constraints_met:
            drag_status_text = " <span style='color: red;'><b>(Invalid drag position)</b></span>"

        details = f"<h2>Plan {self.ui.current_index + 1} (Drag preview){drag_status_text}</h2>"  # Indicate preview and validity
        details += f"<p><b>Crowe class:</b> {_crowe_label(self.ui.current_level)}</p>"
        # Add fixed info
        details += f"<p><b>Score:</b> (Not calculated during dragging)</p>"
        details += f"<p><b>Lateral acetabular edge:</b> ({original_outer_point[0]:.1f}, {original_outer_point[1]:.1f}) (fixed)</p>"
        details += f"<p><b>Cup centre:</b> ({temp_center_point[0]:.1f}, {temp_center_point[1]:.1f}) (temporary)</p>"

        # --- Recalculate values based on temp_center_point ---
        # Coverage & Line 7 Angle
        try:
            vec_co_x = original_outer_point[0] - temp_center_point[0]
            vec_co_y = original_outer_point[1] - temp_center_point[1]
            temp_line7_angle_rad = math.atan2(vec_co_y, vec_co_x)
            temp_line7_angle_rad = adjust_negative_angle(temp_line7_angle_rad)
            temp_line7_angle_deg = math.degrees(temp_line7_angle_rad)

            # 计算角度Cup bone coverage (方法1)
            angle67_rad = (temp_line7_angle_rad - line6_angle_rad + math.pi) % (2 * math.pi) - math.pi
            angle67_deg_abs = abs(math.degrees(angle67_rad))
            coverage_angle = calculate_coverage_angle(line6_angle_rad, temp_line7_angle_rad)  # 使用导入的函数

            # 计算水平Cup bone coverage (方法2)
            active_image_width = self.ui.current_image_width  # Use stored image width
            if active_image_width <= 0:
                print(
                    "Warning: DragHandler._update_details_temporarily using invalid image_width for horizontal coverage.")
            coverage_horizontal = calculate_coverage_horizontal(original_outer_point, temp_center_point, radius,
                                                                line6_angle_rad, active_image_width)  # 使用导入的函数

            details += f"<p><b>Cup-orientation/coverage-boundary angle:</b> {angle67_deg_abs:.1f}°</p>"
            # details += f"<p><b>Acetabular cup bone coverage:</b> {coverage_rate:.1f}%</p>"
            details += f"<p><b>Cup bone coverage (angular geometry):</b> {coverage_angle:.1f}%</p>"
            details += f"<p><b>Cup bone coverage (horizontal position):</b> {coverage_horizontal:.1f}%</p>"
            details += f"<p><b>Coverage-boundary angle (horizontal reference):</b> {temp_line7_angle_deg:.1f}° (temporary)</p>"
        except Exception as e:
            print(f"Error calculating coverage: {e}")  # 更具体的错误信息
            details += "<p><b>Acetabular cup bone coverage:</b> Calculation error</p>"
            details += "<p><b>Coverage-boundary angle (horizontal reference):</b> Calculation error</p>"

        # Abduction Angle (Line 6 vs Line 1)
        try:
            a1, b1, c1 = line1_eq
            line1_angle_rad = math.atan2(-a1, b1)
            angle_diff_rad = line6_angle_rad - line1_angle_rad
            norm_angle_diff_rad = (angle_diff_rad + math.pi) % (2 * math.pi) - math.pi
            abduction_angle_deg = abs(math.degrees(norm_angle_diff_rad))
            # Display the acute angle between unoriented lines; keep stored axis angles unchanged.
            abduction_angle_deg = min(abduction_angle_deg, 180.0 - abduction_angle_deg)
            details += f"<p><b>Radiographic cup inclination:</b> {abduction_angle_deg:.1f}° (fixed)</p>"
        except Exception:
            details += "<p><b>Radiographic cup inclination:</b> Calculation error</p>"

        details += f"<p><b>Cup-orientation axis angle (horizontal reference):</b> {result.get('line6_angle_deg', 0):.1f}° (fixed)</p>"

        # Diameter (fixed during drag)
        safe_even_diameter = result.get('safe_even_diameter')
        pixel_diameter = radius * 2.0
        actual_diameter = pixel_diameter * scale
        details += f"<p><b>Cup diameter (pixels):</b> {pixel_diameter:.2f}</p>"
        if safe_even_diameter is not None:
            details += f"<p><b>Calibrated cup diameter:</b> {actual_diameter:.2f}mm → <b>Standard cup diameter:</b> {safe_even_diameter}mm</p>"
        else:
            details += f"<p><b>Calibrated cup diameter:</b> {actual_diameter:.2f}mm (No safe standard diameter)</p>"

        # Distance to Curve 2
        try:
            min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(
                temp_center_point, radius, curve2_img_path, self.ui.curve_cache, None, self.ui.image_cache)
            if min_dist_curve2 is not None:
                dist_actual_curve2 = min_dist_curve2 * scale
                color = "red" if min_dist_curve2 < 1.0 else "black"  # Highlight invalid distance (less than 1.0)
                details += f"<p style='color:{color};'><b style='color:black;'>Minimum cup-to-superior-obturator-boundary distance:</b> {min_dist_curve2:.2f} px, {dist_actual_curve2:.2f}mm</p>"
            else:
                details += "<p><b>Minimum cup-to-superior-obturator-boundary distance:</b> Not calculated or boundary unavailable</p>"
        except Exception:
            details += "<p><b>Minimum cup-to-superior-obturator-boundary distance:</b> Calculation error</p>"

        # Distance to Curve 3 (新增)
        try:
            if self.ui.folder_c3:  # Check if C3 folder is selected
                curve3_filename = self.ui.current_file.replace('.png', '') + '_bkx.png'
                curve3_img_path = os.path.join(self.ui.folder_c3, curve3_filename)
                min_dist_curve3 = calculate_min_distance_circle_to_curve_thread_safe(
                    temp_center_point, radius, curve3_img_path, self.ui.curve_cache, None, self.ui.image_cache)
                if min_dist_curve3 is not None:
                    dist_actual_curve3 = min_dist_curve3 * scale
                    details += f"<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> {min_dist_curve3:.2f} px, {dist_actual_curve3:.2f}mm</p>"
                else:
                    details += "<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> Not calculated or boundary unavailable</p>"
            else:
                details += "<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> (folder not selected)</p>"
        except Exception:
            details += "<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> Calculation error</p>"

        # Distances to fixed lines (using temp_center_point)
        try:
            # Need to recalculate line equations 2, 3, 4, 8 if they weren't stored originally
            # Or just display original values? For temporary, maybe just show line 1 distance?
            if line1_eq:
                dist_line1 = calculate_distance_point_to_line(temp_center_point, line1_eq)
                details += f"<p><b>Cup centre–inter-teardrop distance:</b> {dist_line1:.2f} px ({dist_line1 * scale:.2f}mm)</p>"
            # Add other distances if easily calculable or needed for preview
            # details += f"<p><b>Cup centre–Köhler distance:</b> ... </p>"
            # details += f"<p><b>Cup centre–superior iliac line distance:</b> ... </p>"
            # details += f"<p><b>Cup centre–ischial line distance:</b> ... </p>"
            # details += f"<p><b>Cup centre–iliac–ischial midpoint line distance:</b> ... </p>"
        except Exception:
            details += "<p><b>Distance to the fixed reference line:</b> Calculation error</p>"

        self.ui.details_label.setText(details)

    def _find_white_line_curve_intersection(self, line_eq, curve_points):
        """查找白色虚线和曲线1的交点"""
        if not line_eq or not curve_points:
            return None

        a, b, c = line_eq
        closest_point = None
        min_distance = float('inf')

        # Check if denominator is zero
        denom_sq = a ** 2 + b ** 2
        if denom_sq == 0: return None
        denom = math.sqrt(denom_sq)

        # 遍历曲线1上的所有点，找到离直线最近的点
        for point in curve_points:
            dist = abs(a * point[0] + b * point[1] + c) / denom
            if dist < min_distance:
                min_distance = dist
                closest_point = point

        # 如果距离小于阈值，认为是交点
        if min_distance < 2.0:  # 2 px内认为是交点
            return closest_point
        return None

    def _update_temp_line5(self, curve_point):
        """更新临时线5方程和交点，用于拖拽外沿点或线5时的可视化"""
        if not curve_point or self.ui.current_index < 0 or self.ui.current_index >= len(self.ui.results):
            return

        current_result = self.ui.results[self.ui.current_index]
        line1_eq = current_result.get('line1_eq')

        # 计算临时线5方程 (平行于线1，过临时外沿点)
        if line1_eq:
            a1, b1, _ = line1_eq
            temp_c5 = -a1 * curve_point[0] - b1 * curve_point[1]
            self.ui.temp_line5_eq = (a1, b1, temp_c5)  # Store in UI's attribute

            # 查找与曲线1的交点
            self.ui.temp_line5_intersection = self._find_white_line_curve_intersection(self.ui.temp_line5_eq,
                                                                                       self.ui.curve1_points)  # Store in UI's attribute

            # 更新临时可视化
            self._update_temporary_visualization()  # Call without center point override

    def _recalculate_with_new_outer_point(self, new_outer_point):
        """Recalculate all results with a new outer point."""
        # Store original state to revert if needed
        original_results = copy.deepcopy(self.ui.results)  # Use copy module
        original_index = self.ui.current_index
        revert_btn_was_enabled = self.ui.revert_btn.isEnabled()

        try:
            print(f"Recalculating with new outer point: {new_outer_point}")
            # --- Call the adaptive process function with the target outer point ---
            # Get the currently set paths
            current_folder_a = self.ui.folder_a
            current_folder_b = self.ui.folder_b
            current_folder_c = self.ui.folder_c
            current_folder_c4 = self.ui.folder_c4
            current_folder_c3 = self.ui.folder_c3
            current_file_d = self.ui.file_d

            # Patch the global variables in planning_core before calling
            import planning_core
            planning_core.FOLDER_A = current_folder_a
            planning_core.FOLDER_B = current_folder_b
            planning_core.FOLDER_C = current_folder_c
            planning_core.FOLDER_C4 = current_folder_c4
            planning_core.FOLDER_C3 = current_folder_c3
            planning_core.FILE_D = current_file_d  # Make sure file D is set too

            # 检查GPU加速选项
            use_gpu = self.ui.gpu_acceleration_checkbox.isChecked()
            if use_gpu:
                print("拖拽重新计算：GPU加速已启用")
            else:
                print("拖拽重新计算：使用CPU处理")

            new_results, _, processed_image_width = process_file_set_adaptive(  # Adjusted to receive three values
                self.ui.current_file,
                show_individual_windows=False,
                target_outer_point=new_outer_point,
                ignore_angle_constraint=True,
                use_gpu=use_gpu
            )
            if processed_image_width > 0:  # Update image width if a valid one was returned
                self.ui.current_image_width = processed_image_width

            if new_results is None: new_results = []  # Ensure list

            # --- 新增：过滤掉直径超过 54 的方案 ---
            original_count = len(new_results)
            new_results = [
                res for res in new_results
                if res.get('safe_even_diameter') is None or res.get('safe_even_diameter') <= 54
            ]
            filtered_count = original_count - len(new_results)
            if filtered_count > 0:
                print(f"过滤掉 {filtered_count} 个直径 > 54 的方案。")
            # --- 过滤结束 ---

            # 分离备选方案和常规方案
            special_fallback_plan = None
            regular_plans = []
            for res in new_results:
                if res.get('is_special_fallback', False):
                    if special_fallback_plan is None:  # 只取第一个备选方案
                        special_fallback_plan = res
                else:
                    if res.get('safe_even_diameter') is not None and res.get('safe_even_diameter') >= MIN_SAFE_DIAMETER:
                        regular_plans.append(res)

            # === 如果没有找到任何常规方案，则执行回退 ===
            if not regular_plans:
                QMessageBox.warning(self.ui, "No suitable plan", "No suitable regular plan is available at this position. The original position has been restored.")
                # 还原到原始状态
                self.ui.results = original_results
                self.ui.current_index = original_index
                self.ui.update_plan_list()  # Refresh列表
                if self.ui.current_index >= 0:
                    self.ui.plan_list.setCurrentRow(self.ui.current_index)
                self.ui.update_ui()  # Refresh界面
                # 确保还原按钮状态正确 (之前的修改已在 release 时启用)
                self.ui.revert_btn.setEnabled(True)
                return # 停止进一步处理

            # === 如果找到了常规方案，继续处理 ===
            # 对常规方案按评分排序 (初始排序)
            regular_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)
            print(f"常规方案过滤后剩余 {len(regular_plans)} 个 (直径>={MIN_SAFE_DIAMETER:g})")

            # === 在全局排序前，根据相同外沿点的直径进行局部评分调整 ===
            print("\\n正在根据相同外沿点的直径调整评分...")
            grouped_results = {}
            for res in regular_plans:  # Use regular_plans here
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
                diameters = [res.get('safe_even_diameter') for res in group if
                              res.get('safe_even_diameter') is not None]
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
                            # --- 修改：计算奖励较大直径的 bonus ---
                            # 原公式: bonus_factor = (max_diam_group - current_diam) / (max_diam_group - min_diam_group + epsilon) # 奖励小直径
                            bonus_factor = (current_diam - min_diam_group) / (
                                        max_diam_group - min_diam_group + epsilon)  # 奖励大直径
                            # --- 修改结束 ---
                            bonus_score = max(0, min(1, bonus_factor))  # Clamp between 0 and 1

                            # Add weighted bonus to final score
                            original_score = res.get('final_score', 0)
                            score_adjustment = bonus_score * local_bonus_weight
                            res['final_score'] = original_score + score_adjustment
                            # Store bonus for potential inspection, ensure 'scores' dict exists
                            if 'scores' not in res: res['scores'] = {}
                            res['scores']['local_diameter_bonus'] = score_adjustment
                            # print(f"    方案直径 {current_diam}: BonusFactor={bonus_factor:.2f}, ScoreAdj={score_adjustment:.4f} -> NewScore={res['final_score']:.4f}")
            # === 局部评分调整结束 ===

            # 对调整后的常规方案重新按评分排序
            regular_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)

            # === 组合最终结果列表（Angular-geometry） ===
            final_angle_results = copy.deepcopy(regular_plans)  # 先放入调整和排序后的常规方案
            if special_fallback_plan:
                angle_fallback = copy.deepcopy(special_fallback_plan)
                final_angle_results.append(angle_fallback)  # 在末尾添加备选方案

            # 标记Angular-geometry plans
            for plan in final_angle_results:
                plan['coverage_method'] = 'angle'
                # 确保Cup bone coverage评估使用Angular-geometry
                angle67_rad = (plan['line7_angle_rad'] - plan['line6_angle_rad'] + math.pi) % (2 * math.pi) - math.pi
                angle67_deg_abs = abs(math.degrees(angle67_rad))
                coverage_angle = ((180.0 - angle67_deg_abs) / 180.0) * 100.0 if angle67_deg_abs <= 180 else 0
                plan['coverage_rate_angle'] = coverage_angle
                plan['is_valid'] = coverage_angle >= COVERAGE_THRESHOLD and (
                            plan.get('circle_to_curve2_distance') is None or plan.get(
                        'circle_to_curve2_distance') >= 1.0)
                plan['need_cover'] = coverage_angle < COVERAGE_THRESHOLD

            # === 创建Horizontal-position plans ===
            final_horizontal_results = copy.deepcopy(regular_plans)
            if special_fallback_plan:
                horizontal_fallback = copy.deepcopy(special_fallback_plan)
                final_horizontal_results.append(horizontal_fallback)

            # 标记Horizontal-position plans
            for plan in final_horizontal_results:
                plan['coverage_method'] = 'horizontal'
                # 确保水平Cup bone coverage计算
                outer_point = plan.get('outer_point')
                center_point = plan.get('center_point')
                radius = self.ui.get_standard_radius_for_result(plan)  # 使用UI中的方法
                line6_angle_rad = plan.get('line6_angle_rad')
                if all([outer_point, center_point, radius > 0, line6_angle_rad is not None]):
                    active_image_width = self.ui.current_image_width  # Get stored image width
                    if active_image_width <= 0:
                        print(
                            "Warning: DragHandler._recalculate_with_new_outer_point using invalid image_width for horizontal coverage mark (in loop).")
                    coverage_horizontal = calculate_coverage_horizontal(outer_point, center_point, radius,
                                                                        line6_angle_rad, active_image_width)
                    plan['coverage_rate_horizontal'] = coverage_horizontal
                    plan['is_valid'] = coverage_horizontal >= COVERAGE_THRESHOLD and (
                                plan.get('circle_to_curve2_distance') is None or plan.get(
                            'circle_to_curve2_distance') >= 1.0)
                    plan['need_cover'] = coverage_horizontal < COVERAGE_THRESHOLD

            # === 合并两种方法的结果 ===
            combined_results = final_angle_results + final_horizontal_results

            # --- Store results and Update UI ---
            # 更新当前显示的结果
            self.ui.results = combined_results

            # 更新列表显示 (会应用排序和过滤逻辑)
            self.ui.update_plan_list()

            if self.ui.results and len(self.ui.results) > 0:
                # === 修改：根据拖拽的方案类型Select第一个显示的方案 ===
                target_method = getattr(self, 'dragged_plan_method', 'angle')  # 获取保存的方法，默认为angle
                print(
                    f"DEBUG RECALC: self.dragged_plan_method='{self.dragged_plan_method}', target_method='{target_method}'")  # DEBUG

                first_index_of_method = -1
                # First, try to find a non-fallback plan of the target method
                print(
                    f"DEBUG RECALC: Searching for NON-FALLBACK in new self.ui.results (len: {len(self.ui.results)}):")  # DEBUG
                for i, res in enumerate(self.ui.results):
                    print(
                        f"  - Index {i}, Method: {res.get('coverage_method')}, Valid: {res.get('is_valid')}, Fallback: {res.get('is_special_fallback')}")  # DEBUG
                    if res.get('coverage_method') == target_method and not res.get('is_special_fallback', False):
                        first_index_of_method = i
                        break

                # If no non-fallback plan is found, try to find a fallback plan of the target method
                if first_index_of_method == -1:
                    print(f"DEBUG RECALC: No regular plan for '{target_method}', searching for FALLBACK:")  # DEBUG
                    for i, res in enumerate(self.ui.results):
                        # print(f"  - Index {i}, Method: {res.get('coverage_method')}, Fallback: {res.get('is_special_fallback')}") # DEBUG
                        if res.get('coverage_method') == target_method and res.get('is_special_fallback', False):
                            first_index_of_method = i
                            print(f"DEBUG RECALC: Found fallback for '{target_method}' at index {i}")  # DEBUG
                            break

                if first_index_of_method != -1:
                    print(f"DEBUG RECALC: Found first_index_of_method = {first_index_of_method}")  # DEBUG
                    self.ui.current_index = first_index_of_method
                    self.ui.select_plan_by_results_index(first_index_of_method)
                else:
                    # If still not found, fallback to the very first plan in the list if any
                    print(
                        f"DEBUG RECALC: No plan found for target_method='{target_method}' (regular or fallback). Falling back to first overall.")  # DEBUG
                    if self.ui.results:  # Check if there are any results at all
                        self.ui.current_index = 0
                        self.ui.select_plan_by_results_index(0)
                    else:
                        self.ui.current_index = -1  # No results, nothing to select
                        self.ui.plan_list.clearSelection()
                # === 修改结束 ===

                # Debug print for final selection
                if self.ui.current_index != -1 and self.ui.current_index < len(self.ui.results):
                    final_selected_res = self.ui.results[self.ui.current_index]
                    print(
                        f"DEBUG RECALC: Final selected index: {self.ui.current_index}, Method: {final_selected_res.get('coverage_method')}, Fallback: {final_selected_res.get('is_special_fallback')}")  # DEBUG
                else:
                    print(
                        f"DEBUG RECALC: Final selected index is invalid or list empty: {self.ui.current_index}")  # DEBUG

                self.ui.update_ui() # This was missing, ensure UI updates after selection
                self.ui.save_btn.setEnabled(True)
                # self.ui.go_to_best_btn.setEnabled(True) # No restore button currently

                angle_valid_count = sum(1 for r in self.ui.results if
                                        r.get('is_valid', True) and r.get('coverage_method') == 'angle' and not r.get(
                                            'is_special_fallback', False))
                horizontal_valid_count = sum(1 for r in self.ui.results if r.get('is_valid', True) and r.get(
                    'coverage_method') == 'horizontal' and not r.get('is_special_fallback', False))
                fallback_present = special_fallback_plan is not None

                final_message = f"Processing completed — valid angular-geometry plans: {angle_valid_count}; valid horizontal-position plans: {horizontal_valid_count}"
                if fallback_present:
                    final_message += "; fallback plan available"

                self.ui.statusBar().showMessage(final_message)
            else:
                # This else block should technically not be reachable now due to the earlier check
                self.ui.current_index = -1
                self.ui.update_ui() # Clear UI if no results
                self.ui.save_btn.setEnabled(False)
                # self.ui.go_to_best_btn.setEnabled(False)
                self.ui.revert_btn.setEnabled(True) # Enable revert even if no valid results after recalc
                self.ui.statusBar().showMessage("Processing completed, but no plan was found")  # Updated message
        except Exception as e:
            self.ui.statusBar().showMessage(f"Error processing case: {str(e)}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.ui, "Processing error", f"Error processing case: {str(e)}")
            # Revert to original state on error
            self.ui.results = original_results
            self.ui.current_index = original_index
            self.ui.update_plan_list()  # Refresh list
            if self.ui.current_index >= 0:
                self.ui.plan_list.setCurrentRow(self.ui.current_index)
            self.ui.update_ui()  # Refresh UI
            self.ui.save_btn.setEnabled(self.ui.current_index >= 0)
            # self.ui.go_to_best_btn.setEnabled(False)
            # Keep revert button state unchanged on error? Or disable?
            # Let's keep it enabled if it was enabled before the error.
            self.ui.revert_btn.setEnabled(True) # Ensure revert is enabled after a failed recalc attempt
        finally:
            # 重新启用UI元素
            self.ui.generate_btn.setEnabled(True)

    def _update_result_after_drag(self, new_center_point):
        """Update the current result dictionary after a drag operation (modifies self.ui.results).
           Finds new outer point tangent to the fixed-radius circle, possibly reducing radius.
        """
        try:
            if self.ui.current_index < 0 or self.ui.current_index >= len(self.ui.results):
                print("Error updating result: Invalid index")
                return

            result = self.ui.results[self.ui.current_index]  # Get the dictionary to modify
            original_center = result.get('center_point')
            original_outer_point = result.get('outer_point')
            line1_eq = result.get('line1_eq')
            scale = result.get('scale_factor')
            line6_angle_rad = result.get('line6_angle_rad')
            curve1_points = self.ui.curve1_points  # Use the stored curve points

            # Get the fixed radius from the original result
            original_radius = self.ui.get_standard_radius_for_result(result)  # 使用UI中的方法
            radius = original_radius  # 初始使用原始半径

            # --- Basic data validation ---
            if not all([original_center, original_outer_point, line1_eq, scale is not None,
                        line6_angle_rad is not None, curve1_points, radius > 0]):
                print(f"Error updating result: Missing essential data for recalculating outer point.")
                self.ui.update_image()  # Refresh to original state
                return

            print(
                f"Updating result {self.ui.current_index} after drag. Original center: {original_center}, New center: {new_center_point}")

            # 保存原始结果的副本，以便在需要时恢复
            original_result = copy.deepcopy(result)  # Use copy module
            revert_btn_was_enabled = self.ui.revert_btn.isEnabled()

            # 计算缩小圆直径的步长（2/比例尺）
            diameter_reduction_step = 2.0 / scale if scale > 0 else 2.0
            min_diameter = MIN_SAFE_DIAMETER / scale if scale > 0 else MIN_SAFE_DIAMETER
            min_radius = min_diameter / 2.0

            new_outer_point = None
            success = False  # Flag to track if update was successful
            attempts = 0  # 尝试次数计数
            final_radius = original_radius  # Store the radius that worked

            # 先尝试使用原始半径
            while not success and radius >= min_radius:
                attempts += 1
                print(f"尝试半径: {radius:.2f} (最小允许: {min_radius:.2f})")

                # --- Find the new outer point (tangent logic) ---
                a1, b1, c1 = line1_eq
                dist_denom_sq = a1 ** 2 + b1 ** 2
                if dist_denom_sq == 0:
                    raise ValueError("Line 1 has zero length.")
                dist_denom = math.sqrt(dist_denom_sq)

                val_center = a1 * new_center_point[0] + b1 * new_center_point[1]
                target_c1 = -val_center + radius * dist_denom
                target_c2 = -val_center - radius * dist_denom

                tangent_line1_eq = (a1, b1, target_c1)
                tangent_line2_eq = (a1, b1, target_c2)

                # Find the points on curve1 closest to each tangent line
                min_dist1 = float('inf')
                point1_candidate = None
                min_dist2 = float('inf')
                point2_candidate = None

                for p in curve1_points:
                    dist1 = calculate_distance_point_to_line(p, tangent_line1_eq)
                    if dist1 < min_dist1:
                        min_dist1 = dist1
                        point1_candidate = p

                    dist2 = calculate_distance_point_to_line(p, tangent_line2_eq)
                    if dist2 < min_dist2:
                        min_dist2 = dist2
                        point2_candidate = p

                if not point1_candidate and not point2_candidate:
                    print(f"尝试 #{attempts}: 半径 {radius:.2f} - 未找到切线外沿点")
                    # 减小半径并继续尝试
                    radius -= diameter_reduction_step / 2.0
                    continue

                # Choose candidate closest to original outer point
                temp_new_outer_point = None
                if point1_candidate and point2_candidate:
                    dist_sq_p1 = (point1_candidate[0] - original_outer_point[0]) ** 2 + (
                                point1_candidate[1] - original_outer_point[1]) ** 2
                    dist_sq_p2 = (point2_candidate[0] - original_outer_point[0]) ** 2 + (
                                point2_candidate[1] - original_outer_point[1]) ** 2
                    temp_new_outer_point = point1_candidate if dist_sq_p1 < dist_sq_p2 else point2_candidate
                elif point1_candidate:
                    temp_new_outer_point = point1_candidate
                elif point2_candidate:
                    temp_new_outer_point = point2_candidate
                else:  # Should not happen based on check above
                    print(f"尝试 #{attempts}: 半径 {radius:.2f} - 逻辑错误，Not selected候选外沿点")
                    radius -= diameter_reduction_step / 2.0
                    continue

                print(f"尝试 #{attempts}: 半径 {radius:.2f} - 候选外沿点: {temp_new_outer_point}")

                # --- Check constraints with the candidate outer point and current radius ---
                vec_co_x = temp_new_outer_point[0] - new_center_point[0]
                vec_co_y = temp_new_outer_point[1] - new_center_point[1]
                new_line7_angle_rad = math.atan2(vec_co_y, vec_co_x)
                new_line7_angle_rad = adjust_negative_angle(new_line7_angle_rad)

                # Coverage Rate
                angle67_rad = (new_line7_angle_rad - line6_angle_rad + math.pi) % (2 * math.pi) - math.pi
                angle67_deg_abs = abs(math.degrees(angle67_rad))
                coverage_rate = ((180.0 - angle67_deg_abs) / 180.0) * 100.0 if angle67_deg_abs <= 180 else 0

                # Curve 2 Distance
                curve2_filename = self.ui.current_file.replace('.png', '') + '_bks.png'
                curve2_img_path = os.path.join(self.ui.folder_c4, curve2_filename)  # Use ui.folder_c4
                min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(
                    new_center_point, radius, curve2_img_path, self.ui.curve_cache, None, self.ui.image_cache)

                is_coverage_valid = coverage_rate >= COVERAGE_THRESHOLD
                is_curve2_valid = min_dist_curve2 is None or min_dist_curve2 >= 1.0  # Check >= 1.0

                if is_coverage_valid and is_curve2_valid:
                    print(
                        f"尝试 #{attempts}: 半径 {radius:.2f} - 找到满足条件的方案！Acetabular cup bone coverage: {coverage_rate:.1f}%, 曲线2距离: {min_dist_curve2}")
                    success = True
                    new_outer_point = temp_new_outer_point  # Confirm the outer point
                    final_radius = radius  # Store the successful radius
                    break  # Exit the loop
                else:
                    print(
                        f"尝试 #{attempts}: 半径 {radius:.2f} - 不满足约束 (Cup bone coverage有效: {is_coverage_valid}, 曲线2距离有效: {is_curve2_valid})")
                    # 减小半径并继续尝试
                    radius -= diameter_reduction_step / 2.0
                    continue

            # Check if a successful configuration was found
            if not success:
                print("All attempts failed to identify a valid plan. Reverting to the original plan.")
                QMessageBox.warning(self.ui, "No plan",
                                    "No valid plan can be found at this position, even after reducing the cup diameter to the minimum threshold. The original plan will be restored.")

                # 恢复原始数据 (modify the dict in self.ui.results directly)
                for key, value in original_result.items():
                    result[key] = value

                # RefreshUI显示原始方案
                self.ui.update_image()
                self.ui.update_details()
                return

            print(f"找到新外沿点: {new_outer_point}，使用半径: {final_radius:.2f}")

            # --- Update result dictionary with the successful configuration ---
            result['center_point'] = new_center_point
            result['outer_point'] = new_outer_point

            # 更新圆直径 (如果半径发生了变化)
            pixel_diameter = final_radius * 2.0  # Use final_radius
            actual_diameter = pixel_diameter * scale

            # Preserve original safe diameter if it existed
            safe_even_diameter = result.get('safe_even_diameter')

            result['circle_diameter'] = pixel_diameter
            result['circle_diameter_actual'] = actual_diameter

            # Don't automatically update safe_even_diameter. It's fixed unless recalculated.
            # If the radius changed, it means the original safe_even_diameter might not be applicable
            # to the new 'actual_diameter', but we keep the original value for display.
            if final_radius != original_radius:
                print(f"半径已从 {original_radius:.2f} 调整为 {final_radius:.2f}")

            # --- Recalculate dependent values ---
            # Line 7 angle
            try:
                vec_co_x = new_outer_point[0] - new_center_point[0]
                vec_co_y = new_outer_point[1] - new_center_point[1]
                new_line7_angle_rad = math.atan2(vec_co_y, vec_co_x)
                new_line7_angle_rad = adjust_negative_angle(new_line7_angle_rad)
                result['line7_angle_rad'] = new_line7_angle_rad
                result['line7_angle_deg'] = math.degrees(new_line7_angle_rad)
            except Exception as e:
                print(f"Error calculating line 7 angle: {e}")
                result['line7_angle_rad'] = None
                result['line7_angle_deg'] = None

            # Distances to lines (Need line equations 1, 4 from result, calc 2, 3, 8)
            line4_eq = result.get('line4_eq')  # Get original line 4 eq
            line2_eq_calc, line3_eq_calc, line8_eq_calc = None, None, None
            try:
                # Correctly access folder_c from the UI instance (self.ui)
                txt_path = os.path.join(self.ui.folder_c, f'{self.ui.current_file}.txt')  # Use self.ui.folder_c
                points = read_points_from_txt(txt_path)
                if points and len(points) >= 8:
                    # Calculate line equations 2, 3, 8 based on points from file
                    line2_points = points[2:4]
                    line3_points = points[4:6]
                    line8_p1 = ((points[2][0] + points[3][0]) / 2, (points[2][1] + points[3][1]) / 2)
                    line8_p2 = ((points[4][0] + points[5][0]) / 2, (points[4][1] + points[5][1]) / 2)
                    if line2_points[0] != line2_points[1]:
                        a2 = line2_points[1][1] - line2_points[0][1]
                        b2 = line2_points[0][0] - line2_points[1][0]
                        c2 = line2_points[1][0] * line2_points[0][1] - line2_points[0][0] * line2_points[1][1]
                        line2_eq_calc = (a2, b2, c2)
                    if line3_points[0] != line3_points[1]:
                        a3 = line3_points[1][1] - line3_points[0][1]
                        b3 = line3_points[0][0] - line3_points[1][0]
                        c3 = line3_points[1][0] * line3_points[0][1] - line3_points[0][0] * line3_points[1][1]
                        line3_eq_calc = (a3, b3, c3)
                    if line8_p1 != line8_p2:
                        a8 = line8_p2[1] - line8_p1[1]
                        b8 = line8_p1[0] - line8_p2[0]
                        c8 = line8_p2[0] * line8_p1[1] - line8_p1[0] * line8_p2[1]
                        line8_eq_calc = (a8, b8, c8)
                else:
                    print("Warning: Could not read points for line distance recalculation.")
            except Exception as e:
                print(f"Error reading points or calculating line equations: {e}")

            # Calculate distances safely using new_center_point
            if line1_eq:
                result['distance_to_line1'] = calculate_distance_point_to_line(new_center_point, line1_eq)
            else:
                result['distance_to_line1'] = float('inf')
            if line4_eq:
                result['distance_to_line4'] = calculate_distance_point_to_line(new_center_point, line4_eq)
            else:
                result['distance_to_line4'] = float('inf')
            if line2_eq_calc:
                result['distance_to_line2'] = calculate_distance_point_to_line(new_center_point, line2_eq_calc)
            else:
                result['distance_to_line2'] = float('inf')
            if line3_eq_calc:
                result['distance_to_line3'] = calculate_distance_point_to_line(new_center_point, line3_eq_calc)
            else:
                result['distance_to_line3'] = float('inf')
            if line8_eq_calc:
                result['distance_to_line8'] = calculate_distance_point_to_line(new_center_point, line8_eq_calc)
            else:
                result['distance_to_line8'] = float('inf')

            # Circle to curve 2 distance (uses new_center_point and final_radius)
            try:
                curve2_filename = self.ui.current_file.replace('.png', '') + '_bks.png'
                curve2_img_path = os.path.join(self.ui.folder_c4, curve2_filename)  # Use ui paths
                # Recalculate distance with the final radius
                min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(
                    new_center_point, final_radius, curve2_img_path, self.ui.curve_cache, None, self.ui.image_cache)
                if min_dist_curve2 is not None:
                    result['circle_to_curve2_distance'] = min_dist_curve2
                    result['circle_to_curve2_distance_actual'] = min_dist_curve2 * scale
                else:
                    result['circle_to_curve2_distance'] = float('inf')
                    result['circle_to_curve2_distance_actual'] = float('inf')
                    print("Warning: Could not calculate distance to curve 2.")
            except Exception as e:
                print(f"Error calculating distance to curve 2: {e}")
                result['circle_to_curve2_distance'] = float('inf')
                result['circle_to_curve2_distance_actual'] = float('inf')

            # --- Recalculate Score ---
            try:
                # Patch globals before calling score_solution
                import planning_core
                planning_core.FOLDER_A = self.ui.folder_a
                planning_core.FOLDER_B = self.ui.folder_b
                planning_core.FOLDER_C = self.ui.folder_c
                planning_core.FOLDER_C4 = self.ui.folder_c4
                planning_core.FOLDER_C3 = self.ui.folder_c3
                planning_core.FILE_D = self.ui.file_d

                # Check validity before scoring
                is_valid = self.ui._check_plan_validity(result)  # Use UI's method
                result['is_valid'] = is_valid

                current_score = score_solution(result, self.ui.results)  # Use ui.results
                result['final_score'] = current_score
            except Exception as e:
                print(f"Error recalculating score: {e}")
                result['final_score'] = 0

            # --- Recalculate and Update Coverage Rates --- (新增)
            try:
                final_coverage_angle = calculate_coverage_angle(line6_angle_rad, result['line7_angle_rad'])
                active_image_width = self.ui.current_image_width  # Use stored image width
                if active_image_width <= 0:
                    print(
                        "Warning: DragHandler._update_result_after_drag using invalid image_width for horizontal coverage.")
                final_coverage_horizontal = calculate_coverage_horizontal(new_outer_point, new_center_point,
                                                                          final_radius, line6_angle_rad,
                                                                          active_image_width)
                result['coverage_rate_angle'] = final_coverage_angle
                result['coverage_rate_horizontal'] = final_coverage_horizontal
                # Update need_cover based on final angle coverage
                result['need_cover'] = final_coverage_angle < COVERAGE_THRESHOLD
            except Exception as e:
                print(f"Error recalculating coverage rates after drag: {e}")
                result['coverage_rate_angle'] = 0  # Default on error
                result['coverage_rate_horizontal'] = 0
                result['need_cover'] = True

            # --- Update list widget text ---
            # (The list update is now handled by update_plan_list after this function)

            # Clear image cache for this updated index
            cache_key_prefix = (self.ui.current_index,)
            keys_to_remove = [k for k in self.ui.image_cache if k[0] == self.ui.current_index]
            for k in keys_to_remove:
                try:
                    del self.ui.image_cache[k]
                except KeyError:
                    pass

            # --- 更新列表和UI --- (This section will be heavily modified)
            print(
                f"Result {self.ui.current_index} (GUID: {result.get('temp_drag_id')}) updated successfully with new center, outer point, and radius.")

            dragged_plan_guid = self.ui.initial_drag_data.get('dragged_plan_guid')
            # The result object (which is a reference to an item in self.ui.results) now contains all updated data.
            # If it had a temp_drag_id, it's still there.

            self.ui.update_plan_list()  # This re-populates self.ui.results and the QListWidget

            selected_new_index = -1
            if dragged_plan_guid:
                for i, res_item in enumerate(
                        self.ui.results):  # self.ui.results is now the new, possibly filtered/sorted list
                    if res_item.get('temp_drag_id') == dragged_plan_guid:
                        selected_new_index = i
                        # Clean up the temporary ID from the item in the new self.ui.results list
                        if 'temp_drag_id' in res_item:  # Should always be true if found by guid
                            del res_item['temp_drag_id']
                        break

            if selected_new_index != -1:
                print(f"Found dragged plan by GUID at new index: {selected_new_index}")
                self.ui.current_index = selected_new_index
                # self.ui.plan_list.setCurrentRow(selected_new_index) # This might be tricky due to headers
                # Instead, we need a robust way to select the item in QListWidget based on self.ui.results index
                self.ui.select_plan_by_results_index(selected_new_index)  # NEW HELPER METHOD NEEDED
            else:
                print(f"Warning: Dragged plan with GUID {dragged_plan_guid} not found after list update. Falling back.")
                # Fallback: if not found by ID (e.g., filtered out or ID issue), try previous logic or select first
                target_method_fallback = getattr(self, 'dragged_plan_method', 'angle')
                first_index_of_method = -1
                for i, res_item in enumerate(self.ui.results):
                    if res_item.get('coverage_method') == target_method_fallback:
                        first_index_of_method = i
                        break
                if first_index_of_method != -1:
                    self.ui.current_index = first_index_of_method
                    self.ui.select_plan_by_results_index(first_index_of_method)
                elif self.ui.results:
                    self.ui.current_index = 0
                    self.ui.select_plan_by_results_index(0)
                else:
                    self.ui.current_index = -1
                    self.ui.plan_list.clearSelection()  # Or clear UI

            # self.ui.update_ui() # select_plan_by_results_index should call update_ui
            self.ui.revert_btn.setEnabled(True)  # Enable revert after successful drag update

        except Exception as e:
            print(f"Unexpected error during result update (finding new outer point): {e}")
            import traceback
            traceback.print_exc()
            # Attempt to revert data
            for key, value in original_result.items():
                result[key] = value

            print("Reverted result data due to error.")
            QMessageBox.critical(self.ui, "Update error", f"Error updating the plan: {e}")  # Show critical error
            # Refresh UI to show the reverted state (will be called by event filter)
            # self.ui.update_ui()
            return

        # UI update is handled by the calling event filter upon successful completion


# --- Main UI Class ---
class PlanVisualizationUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KAP-DDH Acetabular Reconstruction Planning")
        self.setGeometry(100, 100, 1600, 900)  # 设置窗口大小

        # 初始化数据
        self.results = []  # 存储所有方案结果 (Current state)
        self.last_recalculation_results = []  # Stores results from last full recalc (Generate or Outer/Line5 drag)
        self.initial_generation_results = []  # Stores results from the very first "Generate" button click
        self.current_index = -1  # Initialize to -1, indicates no selection
        self.current_file = ""  # 当前处理的文件名
        self.current_level = 1  # 当前Crowe Class
        self.image_cache = {}  # 缓存方案图像
        self.curve_cache = {}  # 缓存曲线点与距离变换
        self.zoom_factor = 1.0  # Zoom factor for the image
        self.original_pixmap = None  # Store the original unscaled pixmap
        self.curve1_points = []  # Store points of curve 1 for interaction
        self.dragging_outer_point = False  # Flag for dragging state for outer point
        self.dragging_line5 = False  # Flag for dragging state for line 5
        self.dragging_semicircle = False  # Flag for dragging semicircle
        self.dragging_line6_rotate = False  # Flag for rotating semicircle via Line 6
        self.drag_temp_outer_point = None  # Temporary point during drag
        self.drag_temp_center_point = None  # Temporary center point during drag
        self.drag_offset = QPoint(0, 0)  # Offset for semicircle drag
        self.initial_drag_data = {}  # Store initial data for line 5 drag
        self.current_outer_point_display = None  # Store the displayed outer point coords
        self.current_image_width = 0  # Store current image width

        # 临时拖拽显示数据
        self.temp_line5_eq = None  # 临时线5方程
        self.temp_line5_intersection = None  # 临时线5与曲线1的交点

        # Create DragHandler instance
        self.drag_handler = DragHandler(self)

        # 文件夹路径
        self.folder_a = _cfg_path('FOLDER_A', "")
        self.folder_b = _cfg_path('FOLDER_B', "")
        self.folder_c = _cfg_path('FOLDER_C', "")
        self.folder_c4 = _cfg_path('FOLDER_C4', "")
        self.folder_c3 = _cfg_path('FOLDER_C3', "")
        self.file_d = _cfg_path('FILE_D', "")
        self.save_folder = SAVE_FOLDER

        try:
            self._print_runtime_kb_config()
        except Exception:
            pass


        # 设置中央窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # 1. 左侧区域 - Ranked Plans和控制按钮
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 创建Case Selection组
        file_group = QGroupBox("Case Selection")
        file_layout = QGridLayout()

        # 原图文件夹Select
        self.folder_a_label = QLabel("Source-radiograph folder:")
        self.folder_a_btn = QPushButton("Select")
        self.folder_a_btn.clicked.connect(lambda: self.select_folder('a'))
        self.folder_a_text = QLabel("Not selected")
        file_layout.addWidget(self.folder_a_label, 0, 0)
        file_layout.addWidget(self.folder_a_btn, 0, 1)
        file_layout.addWidget(self.folder_a_text, 0, 2)

        # 其他文件夹路径已在程序中指定，不需要用户Select

        # 文件名Select
        self.file_label = QLabel("Case ID:")
        self.file_combo = QComboBox()
        self.file_combo.currentTextChanged.connect(self.on_file_selected)
        self.file_refresh_btn = QPushButton("Refresh")
        self.file_refresh_btn.clicked.connect(self.refresh_file_list)
        file_layout.addWidget(self.file_label, 1, 0)
        file_layout.addWidget(self.file_combo, 1, 1, 1, 2)
        file_layout.addWidget(self.file_refresh_btn, 1, 3)

        # 移除保存路径Select（保存位置默认为原图文件夹）

        file_group.setLayout(file_layout)
        try:
            file_group.setParent(self)
            file_group.hide()
        except Exception:
            pass

        # Crowe Classification下拉框
        level_group = QGroupBox("Crowe Classification")
        level_layout = QHBoxLayout()

        self.level_label = QLabel("Select Crowe class:")
        self.level_combo = QComboBox()
        for i, crowe_class in enumerate(("I", "II", "III", "IV"), start=1):
            self.level_combo.addItem(f"Crowe {crowe_class}")
        self.level_combo.currentIndexChanged.connect(self.on_level_changed)

        level_layout.addWidget(self.level_label)
        level_layout.addWidget(self.level_combo)
        level_group.setLayout(level_layout)
        try:
            level_group.setParent(self)
            level_group.hide()
        except Exception:
            pass


        # 添加Generate Preoperative Plans按钮到"Planning"组
        buttons_group = QGroupBox("Planning")
        buttons_main_layout = QVBoxLayout()

        # 按钮行
        buttons_layout = QHBoxLayout()

        self.generate_btn = QPushButton("Generate Preoperative Plans")
        self.generate_btn.clicked.connect(self.process_file)
        self.generate_btn.setEnabled(False)  # 初始状态禁用
        buttons_layout.addWidget(self.generate_btn)

        self.save_btn = QPushButton("Save Current Plan")
        self.save_btn.clicked.connect(self.save_current_plan)
        self.save_btn.setEnabled(False)  # 初始状态禁用
        buttons_layout.addWidget(self.save_btn)

        # 移除“保存所有方案”按钮

        # 添加"Restore Initial Plan"按钮
        self.revert_btn = QPushButton("Restore Initial Plan")
        self.revert_btn.clicked.connect(self.revert_to_initial_generation)
        self.revert_btn.setEnabled(False)  # 初始状态禁用
        buttons_layout.addWidget(self.revert_btn)

        self.batch_btn = QPushButton("Batch Process")
        self.batch_btn.clicked.connect(self.batch_process_all_files)
        buttons_layout.addWidget(self.batch_btn)

        # GPU加速选项
        gpu_layout = QHBoxLayout()
        self.gpu_acceleration_checkbox = QCheckBox("Enable GPU Acceleration")

        # 检测GPU支持情况
        gpu_available, gpu_info = self.check_gpu_support()
        if gpu_available:
            self.gpu_acceleration_checkbox.setChecked(True)  # 默认勾选
            tooltip_text = f"Use the GPU to accelerate parallel computation\n{gpu_info}"
        else:
            self.gpu_acceleration_checkbox.setChecked(False)  # GPU不可用时默认不勾选
            self.gpu_acceleration_checkbox.setEnabled(False)  # 禁用复选框
            tooltip_text = f"GPU acceleration is unavailable\n{gpu_info}"

        self.gpu_acceleration_checkbox.setToolTip(tooltip_text)
        gpu_layout.addWidget(self.gpu_acceleration_checkbox)
        gpu_layout.addStretch()  # 添加弹性空间，使复选框左对齐

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)  # 初始状态隐藏
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Processing: %p%")

        buttons_main_layout.addLayout(buttons_layout)
        buttons_main_layout.addLayout(gpu_layout)
        buttons_main_layout.addWidget(self.progress_bar)
        buttons_group.setLayout(buttons_main_layout)
        try:
            buttons_group.setParent(self)
            buttons_group.hide()
        except Exception:
            pass

        # Ranked Plans
        plans_group = QGroupBox("Ranked Plans")
        plans_layout = QVBoxLayout()

        self.plan_list = QListWidget()
        self.plan_list.setMinimumWidth(300)
        self.plan_list.itemClicked.connect(self.on_plan_selected)
        plans_layout.addWidget(self.plan_list)

        plans_group.setLayout(plans_layout)

        # 键盘快捷键：A上一张，D下一张
        try:
            self.shortcut_next = QShortcut(QKeySequence('D'), self)
            self.shortcut_next.setAutoRepeat(False)
            self.shortcut_next.activated.connect(self._on_shortcut_next)
            self.shortcut_prev = QShortcut(QKeySequence('A'), self)
            self.shortcut_prev.setAutoRepeat(False)
            self.shortcut_prev.activated.connect(self._on_shortcut_prev)
        except Exception:
            pass

        # 2. 中间区域 - 图像显示
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(800, 800)  # Keep minimum size for layout
        self.image_label.setFrameShape(QFrame.Box)
        self.image_label.setText("Select a case and Crowe class")
        self.image_label.installEventFilter(self)  # Install event filter for drag functionality

        # 使用滚动区域容纳图像
        self.scroll_area = QScrollArea()  # Store scroll area reference
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.image_label)
        middle_layout.addWidget(self.scroll_area)

        # Event Filter for Mouse Events on Scroll Area Viewport
        self.scroll_area.viewport().installEventFilter(self)  # Install on viewport

        # 3. 右侧区域 - 详细数据和Display Options
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 详细数据区域
        details_group = QGroupBox("Plan Details")
        details_layout = QVBoxLayout()
        self.details_label = QLabel("Plan Details")
        self.details_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.details_label.setWordWrap(True)
        self.details_label.setMinimumWidth(400)
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setWidget(self.details_label)
        details_layout.addWidget(details_scroll)
        details_group.setLayout(details_layout)
        

        # Display Options区域
        visibility_group = QGroupBox("Display Options")
        visibility_layout = QGridLayout()
        self.visibility_checkboxes = {}
        elements = {
            'line1': "Inter-teardrop line (red)", 'line2': "Superior iliac crest line (yellow)", 'line3': "Ischial tuberosity line (cyan)",
            'line4': "Köhler line (brown)", 'line5': "Lateral-edge reference line (white)", 'line6': "Cup-orientation axis (orange)",
            'line7': "Coverage boundary line (purple)", 'line8': "Iliac–ischial midpoint reference line (pink)",
            'outer_point': "Lateral acetabular edge (blue)", 'center_point': "Cup centre (green)",
            'half_circle': "Acetabular cup (green)",
            'curve1': "Acetabular reconstruction boundary (yellow)", 'curve2': "Superior obturator boundary (cyan)",
            'curve3': "Inferior obturator boundary (magenta)",  # 新增曲线3选项
            'highest_point': "Superior-most point (sky blue)", 'lowest_point': "Inferior-most point (gold)",
            # 下面两行已被注释或删除
            # 'line9': "线9 (灰)",
            # 'line9_closest_point': "线9最近点 (暗红)"
        }
        row, col = 0, 0
        for key, text in elements.items():
            checkbox = QCheckBox(text)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(lambda state, k=key: self._on_visibility_checkbox_changed(k, state == Qt.Checked))
            self.visibility_checkboxes[key] = checkbox
            visibility_layout.addWidget(checkbox, row, col)
            col += 1
            if col >= 3:  # Adjust columns as needed
                col = 0
                row += 1

        visibility_group.setLayout(visibility_layout)
        try:
            visibility_group.setParent(self)
            visibility_group.hide()
        except Exception:
            pass

        # 初始化主菜单栏
        try:
            self._init_menubar()
        except Exception:
            pass

        right_vsplit = QSplitter(Qt.Vertical)
        right_vsplit.addWidget(plans_group)
        right_vsplit.addWidget(details_group)
        right_vsplit.setSizes([200, 400])
        right_layout.addWidget(right_vsplit)

        files_group = QGroupBox("Case List")
        files_layout = QVBoxLayout()
        self.file_list = QListWidget()
        self.file_list.itemDoubleClicked.connect(lambda item: self.on_file_selected(item.text()))
        files_layout.addWidget(self.file_list)
        files_group.setLayout(files_layout)
        left_layout.addWidget(files_group)

        # 将三个区域添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(middle_widget)
        splitter.addWidget(right_widget)

        # 设置区域初始大小比例 (左侧:中间:右侧)
        splitter.setSizes([300, 700, 400])

        # 状态栏显示Current case和Crowe Class
        self.statusBar().showMessage("Ready")

        # 初始化Case List（如已Select文件夹）
        try:
            self.refresh_file_list()
        except Exception:
            pass


    def select_folder(self, folder_type):
        """Select文件夹"""
        if folder_type == 'a':
            folder_path = QFileDialog.getExistingDirectory(self, "Select Source-radiograph Folder")
            if folder_path:
                self.folder_a = folder_path
                self.folder_a_text.setText(os.path.basename(folder_path))
                # Select Source-radiograph Folder后直接Refresh Case List
                self.refresh_file_list()
                try:
                    if hasattr(self, 'file_menu_folder_action'):
                        self.file_menu_folder_action.setText(f"Current source-radiograph folder: {self.folder_a}")
                except Exception:
                    pass
                try:
                    self._auto_complete_line6_endpoints_in_folder(self._get_save_folder())
                except Exception as e:
                    print(f"批量补全line6_endpoints时出错: {e}")





    def refresh_file_list(self):
        """Refresh Case List"""
        # 只检查原图文件夹是否已Select
        if not self.folder_a:
            self.statusBar().showMessage("Select the source-radiograph folder first")
            return

        try:
            # 从点坐标文件夹获取Case List
            self.file_combo.clear()

            img_files = [f for f in os.listdir(self.folder_a) if f.lower().endswith('.png')]
            img_names = {os.path.splitext(f)[0] for f in img_files}

            if os.path.isdir(getattr(self, 'folder_c', '')):
                txt_files = [f for f in os.listdir(self.folder_c) if f.lower().endswith('.txt')]
                txt_names = {os.path.splitext(f)[0] for f in txt_files}
                file_names = sorted(img_names & txt_names)
            else:
                file_names = sorted(img_names)

            self.file_combo.addItems(file_names)
            if hasattr(self, 'file_list'):
                self.file_list.clear()
                for name in file_names:
                    self.file_list.addItem(name)

            if file_names:
                self.statusBar().showMessage(f"Found {len(file_names)} matching cases")
                # 自动Select第一个文件（通过 currentTextChanged 触发 on_file_selected ）
                self.file_combo.setCurrentIndex(0)
            else:
                self.statusBar().showMessage("No matching landmark files were found")
                if hasattr(self, 'file_list'):
                    self.file_list.clear()
        except Exception as e:
            self.statusBar().showMessage(f"Error refreshing the case list: {str(e)}")

    def _get_save_folder(self):
        folder = (getattr(self, 'save_folder', '') or '').strip()
        if folder:
            return folder
        return getattr(self, 'folder_a', '') or ''

    def _auto_complete_line6_endpoints_in_folder(self, root_folder):
        """遍历root_folder下的所有json，缺失line6_endpoints则自动补全并保存。"""
        import os
        import json
        completed = 0
        problems = []
        for dirpath, _, filenames in os.walk(root_folder):
            for fn in filenames:
                if not fn.lower().endswith('.json'):
                    continue
                jf = os.path.join(dirpath, fn)
                try:
                    with open(jf, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'line6_endpoints' in data and isinstance(data['line6_endpoints'], list):
                        continue
                    center_point = data.get('center_point')
                    angle_rad = data.get('line6_angle_rad')
                    radius = self.get_standard_radius_for_result(data)
                    if (center_point is None or angle_rad is None or radius is None or radius <= 0):
                        problems.append(jf)
                        continue
                    dx = radius * math.cos(float(angle_rad))
                    dy = radius * math.sin(float(angle_rad))
                    p1 = [float(center_point[0]) + dx, float(center_point[1]) + dy]
                    p2 = [float(center_point[0]) - dx, float(center_point[1]) - dy]
                    data['line6_endpoints'] = [p1, p2]
                    with open(jf, 'w', encoding='utf-8') as f:
                        json.dump(self._make_json_safe(data), f, ensure_ascii=False, indent=2)
                    completed += 1
                except Exception as e:
                    problems.append(jf)
                    print(f"补全 {jf} 失败: {e}")
        print(f"Saved-plan compatibility check complete: updated {completed}; issues {len(problems)}")
        if problems:
            print("问题文件：")
            for jf in problems:
                print(jf)
        self.statusBar().showMessage(f"Saved-plan compatibility check complete: updated {completed}; issues {len(problems)}")

    def display_first_image(self, file_name):
        """显示第一张图像"""
        try:
            # 构建原图文件路径
            image_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']
            image_path = None

            # 尝试不同的图像扩展名
            for ext in image_extensions:
                potential_path = os.path.join(self.folder_a, file_name + ext)
                if os.path.exists(potential_path):
                    image_path = potential_path
                    break

            if image_path and os.path.exists(image_path):
                # 使用PIL读取图像以支持中文路径
                pil_img = Image.open(image_path)
                # 转换为RGB模式（如果不是的话）
                if pil_img.mode != 'RGB':
                    pil_img = pil_img.convert('RGB')

                # 转换为numpy数组
                img_array = np.array(pil_img)

                # 转换为OpenCV格式（BGR）
                img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

                # 转换为QPixmap显示
                height, width, channel = img_bgr.shape
                bytes_per_line = 3 * width
                img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                q_img = QImage(img_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(q_img)

                # 保存原始pixmap并应用缩放
                self.original_pixmap = pixmap
                self._apply_zoom()

                self.statusBar().showMessage(f"Radiograph displayed: {file_name}")
            else:
                self.image_label.setText(f"Radiograph not found: {file_name}")
                self.original_pixmap = None
                self._apply_zoom()

        except Exception as e:
            self.statusBar().showMessage(f"Error displaying radiograph: {str(e)}")
            self.image_label.setText(f"Error displaying radiograph: {str(e)}")
            self.original_pixmap = None
            self._apply_zoom()

    def on_file_selected(self, file_name):
        """当用户从下拉框Select文件时触发"""
        if not file_name:
            return

        self.current_file = file_name
        self.statusBar().showMessage(f"Current case: {file_name}, Crowe class: {_crowe_label(self.current_level)}")

        # 启用/禁用Planning
        try:
            self.generate_btn.setEnabled(True)
            self.save_btn.setEnabled(False)
            self.revert_btn.setEnabled(False)
        except Exception:
            pass
        try:
            if hasattr(self, 'action_generate'):
                self.action_generate.setEnabled(True)
            if hasattr(self, 'action_save'):
                self.action_save.setEnabled(False)
            if hasattr(self, 'action_revert'):
                self.action_revert.setEnabled(False)
        except Exception:
            pass
        try:
            if hasattr(self, 'file_list') and self.current_file:
                items = self.file_list.findItems(self.current_file, Qt.MatchExactly)
                if items:
                    self.file_list.blockSignals(True)
                    self.file_list.setCurrentItem(items[0])
                    self.file_list.scrollToItem(items[0])
                    self.file_list.blockSignals(False)
        except Exception:
            pass
        self.plan_list.clear()
        self.image_label.clear()
        self.details_label.clear()
        self.results = []
        self.current_index = -1
        self.current_image_width = 0  # Reset image width

        # 先尝试从原图文件夹加载该文件对应的Saved方案
        try:
            self.try_load_saved_plans_for_current_file()
        except Exception as e:
            print(f"加载Saved方案时出错: {e}")
            # 保持生成按钮可用，供用户重新生成
            pass

        # 若未加载到Saved方案，则显示对应的原图
        if not self.results:
            self.display_first_image(file_name)

        try:
            self._warn_current_file_points_mismatch()
        except Exception:
            pass

        # 注意：不再自动处理文件，需要用户点击生成按钮

    def batch_process_all_files(self):
        """Batch Process当前点坐标文件夹中的所有文件，后台执行并逐个RefreshUI与保存"""
        import os
        from PyQt5.QtWidgets import QApplication

        # 基本校验
        if not getattr(self, 'folder_a', '') or not os.path.isdir(self.folder_a):
            self.statusBar().showMessage("Select the source-radiograph folder first")
            return
        if not os.path.isdir(getattr(self, 'folder_c', '')):
            self.statusBar().showMessage("The landmark-coordinate folder does not exist")
            return

        # 进度条初始化
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Batch processing...")
        QApplication.processEvents()

        try:
            self._print_runtime_kb_config(prefix="Batch Process")
            self._warn_batch_points_mismatch()
        except Exception:
            pass

        use_gpu = self.gpu_acceleration_checkbox.isChecked()

        # 启动后台批量线程
        self.batch_thread = QThread()
        self.batch_worker = BatchWorker(
            self.folder_a,
            self.folder_b,
            self.folder_c,
            self.folder_c4,
            self.folder_c3,
            self.file_d,
            use_gpu=use_gpu,
            level=getattr(self, 'current_level', 0)
        )
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.started.connect(self.batch_worker.run)
        self.batch_worker.progressChanged.connect(self._on_batch_progress)
        self.batch_worker.fileFinished.connect(self._on_batch_file_finished)
        self.batch_worker.done.connect(self._on_batch_done)
        self.batch_worker.errorOccurred.connect(self._on_batch_error)
        self.batch_thread.finished.connect(self.batch_thread.deleteLater)

        self.batch_thread.start()

    def on_level_changed(self, index):
        """当用户SelectCrowe Class时触发"""
        self.current_level = index + 1  # 索引从0开始，Crowe Class从1开始
        self.statusBar().showMessage(f"Current case: {self.current_file}, Crowe class: {_crowe_label(self.current_level)}")

        # 如果已有Select的文件，确保生成按钮可用
        if self.current_file:
            self.generate_btn.setEnabled(True)
        try:
            if hasattr(self, 'level_combo_menu'):
                if self.level_combo_menu.currentIndex() != index:
                    self.level_combo_menu.blockSignals(True)
                    self.level_combo_menu.setCurrentIndex(index)
                    self.level_combo_menu.blockSignals(False)
        except Exception:
            pass

    def _on_level_menu_changed(self, index):
        try:
            if hasattr(self, 'level_combo') and self.level_combo.currentIndex() != index:
                self.level_combo.blockSignals(True)
                self.level_combo.setCurrentIndex(index)
                self.level_combo.blockSignals(False)
        except Exception:
            pass
        self.on_level_changed(index)

    def process_file(self):
        """处理文件并更新UI"""
        if not self.current_file:
            return

        try:
            self._print_runtime_kb_config(prefix=f"单文件 {self.current_file}")
            self._warn_current_file_points_mismatch()
        except Exception:
            pass

        # 显示进度条并初始化
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Initialising...")
        QApplication.processEvents()  # 强制更新UI

        # 禁用生成按钮防止重复点击
        self.generate_btn.setEnabled(False)

        # 开始计时
        ui_start_time = time.time()
        print(f"\n=== UI处理开始 ===")
        print(f"UI处理开始时间: {time.strftime('%H:%M:%S', time.localtime(ui_start_time))}")

        try:
            # 清空缓存
            self.image_cache = {}

            # 更新进度：10%
            self.progress_bar.setValue(10)
            self.progress_bar.setFormat("Configuring parameters...")
            QApplication.processEvents()

            # 更新Crowe Class约束
            update_constraint_ideals(self.current_level)

            # 设置全局文件夹路径
            from planning_core import FOLDER_A, FOLDER_B, FOLDER_C, FOLDER_C4, FILE_D

            # 使用monkey patch来替换全局变量
            import planning_core
            planning_core.FOLDER_A = self.folder_a
            planning_core.FOLDER_B = self.folder_b
            planning_core.FOLDER_C = self.folder_c
            planning_core.FOLDER_C4 = self.folder_c4
            planning_core.FOLDER_C3 = self.folder_c3

            # 设置比例尺文件路径（已硬编码指定）
            planning_core.FILE_D = self.file_d

            # 更新进度：20%
            self.progress_bar.setValue(20)
            self.progress_bar.setFormat("Starting the planning algorithm...")
            QApplication.processEvents()

            # === 第一步：调用原程序中的处理函数，获取所有方案（包括备选） ===
            core_start_time = time.time()
            print(f"\n--- 核心算法处理开始 ---")
            print(f"核心算法开始时间: {time.strftime('%H:%M:%S', time.localtime(core_start_time))}")

            # 检查GPU加速选项
            use_gpu = self.gpu_acceleration_checkbox.isChecked()
            if use_gpu:
                print("GPU加速已启用")
            else:
                print("使用CPU处理")

            # 启动后台线程运行核心算法，并接收实时进度
            self.progress_bar.setFormat("Running the planning algorithm...")
            QApplication.processEvents()

            self.core_thread = QThread()
            self.core_worker = CoreWorker(self.current_file, use_gpu=use_gpu, ignore_angle_constraint=False)
            self.core_worker.moveToThread(self.core_thread)

            self.core_thread.started.connect(self.core_worker.run)
            self.core_worker.progressChanged.connect(self._on_core_progress)
            self.core_worker.finishedWithResults.connect(self._on_core_finished)
            self.core_worker.errorOccurred.connect(self._on_core_error)
            self.core_thread.finished.connect(self.core_thread.deleteLater)

            self.core_thread.start()
        except Exception as e:
            try:
                self.statusBar().showMessage(f"Failed to start the planning algorithm: {e}")
            except Exception:
                pass
            try:
                QMessageBox.critical(self, "Start-up error", f"Failed to start the planning algorithm: {e}")
            except Exception:
                pass
            try:
                self.progress_bar.setVisible(False)
            except Exception:
                pass
            try:
                self.generate_btn.setEnabled(True)
            except Exception:
                pass
        return

    def _print_runtime_kb_config(self, prefix=""):
        enable = _cfg_bool("PERSONALIZED_CONSTRAINTS_ENABLE", False)
        hdr = f"[运行配置]{(' ' + prefix) if prefix else ''}"
        print(hdr)
        print(f"PERSONALIZED_CONSTRAINTS_ENABLE={int(enable)}")
        if not enable:
            return
        print(f"KB_GNN_DIR={_cfg_path('KB_GNN_DIR', '')}")
        print(f"KB_WEIGHTS_PATH={_cfg_path('KB_WEIGHTS_PATH', '')}")
        print(f"KB_XLSX_PATH={_cfg_path('KB_XLSX_PATH', '')}")
        print(f"KB_TXT_ROOT={_cfg_path('KB_TXT_ROOT', '')}")
        print(f"KB_VECTOR_CACHE_ENABLE={int(_cfg_bool('KB_VECTOR_CACHE_ENABLE', True))}")
        print(f"KB_VECTOR_CACHE_PATH={_cfg_path('KB_VECTOR_CACHE_PATH', '')}")
        print(f"KB_FORCE_REBUILD_CACHE={int(_cfg_bool('KB_FORCE_REBUILD_CACHE', False))}")
        print(f"KB_DYNAMIC_TOPK_ENABLE={int(_cfg_bool('KB_DYNAMIC_TOPK_ENABLE', True))}")
        print(f"KB_TOPK_FIXED={_cfg_int('KB_TOPK_FIXED', 0)}")
        print(f"KB_EXPECT_N_POINTS={_cfg_int('KB_EXPECT_N_POINTS', 0)}")

    def _count_txt_points(self, txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    def _warn_current_file_points_mismatch(self):
        import os
        enable = _cfg_bool("PERSONALIZED_CONSTRAINTS_ENABLE", False)
        expected = _cfg_int("KB_EXPECT_N_POINTS", 0)
        if (not enable) or expected <= 0:
            return
        if not getattr(self, "current_file", "") or not getattr(self, "folder_c", ""):
            return
        txt_path = os.path.join(self.folder_c, f"{self.current_file}.txt")
        actual = self._count_txt_points(txt_path)
        if actual and actual != expected:
            msg = f"txt点数不一致：case={self.current_file} expected={expected} actual={actual}（个性化约束会回退固定约束）"
            print(msg)
            try:
                self.statusBar().showMessage(msg)
            except Exception:
                pass

    def _warn_batch_points_mismatch(self):
        import os
        enable = _cfg_bool("PERSONALIZED_CONSTRAINTS_ENABLE", False)
        expected = _cfg_int("KB_EXPECT_N_POINTS", 0)
        if (not enable) or expected <= 0:
            return
        folder_c = getattr(self, "folder_c", "")
        if not folder_c or (not os.path.isdir(folder_c)):
            return
        try:
            txt_files = [f for f in os.listdir(folder_c) if f.lower().endswith(".txt")]
        except Exception:
            txt_files = []
        if not txt_files:
            return
        sample = os.path.join(folder_c, txt_files[0])
        actual = self._count_txt_points(sample)
        if actual and actual != expected:
            print(f"Batch Process样例点数不一致：file={os.path.basename(sample)} expected={expected} actual={actual}（个性化约束会回退固定约束）")
            return

    def _on_core_progress(self, value, text):
        try:
            v = max(0, min(100, int(value)))
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(v)
            self.progress_bar.setFormat(text or f"Processing: {v}%")
            QApplication.processEvents()
        except Exception:
            pass

    def _on_core_error(self, message):
        try:
            self.statusBar().showMessage(f"Error processing case: {message}")
            QMessageBox.critical(self, "Processing error", f"Error processing case: {message}")
        finally:
            try:
                if hasattr(self, 'core_thread'):
                    self.core_thread.quit()
                    self.core_thread.wait()
            except Exception:
                pass
            self.progress_bar.setVisible(False)
            self.generate_btn.setEnabled(True)

    def _on_core_finished(self, new_results, curve1_points, processed_image_width):
        # 后台核心算法完成后的数据整理与UI更新
        try:
            self.progress_bar.setValue(50)
            self.progress_bar.setFormat("Planning algorithm completed; processing results...")
            QApplication.processEvents()

            core_end_time = time.time()
            print(f"核心算法结束时间: {time.strftime('%H:%M:%S', time.localtime(core_end_time))}")
            print(f"--- 核心算法处理结束 ---\n")

            self.curve1_points = curve1_points
            self.current_image_width = processed_image_width
            if new_results is None:
                new_results = []

            # 数据处理开始计时
            data_process_start = time.time()
            print(f"--- 数据处理开始 ---")
            print(f"数据处理开始时间: {time.strftime('%H:%M:%S', time.localtime(data_process_start))}")

            # DEBUG: 打印接收到的结果信息
            print(f"DEBUG UI: Received {len(new_results)} results from backend.")
            for idx, res_debug in enumerate(new_results):
                print(
                    f"DEBUG UI: Result {idx} -> is_special_fallback: {res_debug.get('is_special_fallback', 'Not Set')}, score: {res_debug.get('final_score')}")

            # 更新进度：60%
            self.progress_bar.setValue(60)
            self.progress_bar.setFormat("Assessing candidate plans...")
            QApplication.processEvents()

            # 分离备选与常规方案
            special_fallback_plan = None
            regular_plans = []
            for res in new_results:
                if res.get('is_special_fallback', False):
                    if special_fallback_plan is None:
                        special_fallback_plan = res
                else:
                    diameter = res.get('safe_even_diameter')
                    if diameter is not None and diameter >= MIN_SAFE_DIAMETER:
                        regular_plans.append(res)

            if not regular_plans:
                print("Initial generation found no REGULAR results.")
                # 无常规方案原因汇总（仅打印统计，不改变逻辑）
                try:
                    total_candidates = len(new_results)
                    skipped_none = sum(1 for r in new_results if r.get('safe_even_diameter') is None)
                    skipped_lt40 = sum(
                        1 for r in new_results
                        if (r.get('safe_even_diameter') is not None and r.get('safe_even_diameter') < MIN_SAFE_DIAMETER)
                    )
                    fallback_count = 1 if special_fallback_plan is not None else 0
                    diameters = [r.get('safe_even_diameter') for r in new_results if r.get('safe_even_diameter') is not None]
                    print("无常规方案原因：")
                    print(f"  - 候选总数: {total_candidates}")
                    print(f"  - 备选方案数量: {fallback_count}")
                    print(f"  - 无有效标准偶数直径: {skipped_none}")
                    print(f"  - 标准偶数直径 < {MIN_SAFE_DIAMETER:g}mm: {skipped_lt40}")
                    if diameters:
                        print(f"  - 直径范围: {min(diameters)} ~ {max(diameters)} mm")
                    else:
                        print("  - 直径范围: 无（全部为 None）")
                except Exception as e_diag:
                    print(f"生成无常规方案原因汇总失败: {e_diag}")
                if special_fallback_plan:
                    QMessageBox.information(self, "Notice", "No suitable regular plan was found. Only fallback plans will be displayed.")
                else:
                    QMessageBox.warning(self, "No suitable plan", "No suitable plan was found, including regular and fallback plans.")
                    self.results = []
                    self.current_index = -1
                    self.initial_generation_results = []
                    self.last_recalculation_results = []
                    self.update_plan_list()
                    self.update_ui()
                    self.save_btn.setEnabled(False)
                    self.revert_btn.setEnabled(False)
                    return

            # 局部评分调整（相同外沿点的大直径奖励）
            grouped_results = {}
            for res in regular_plans:
                op_tuple = tuple(res['outer_point'])
                grouped_results.setdefault(op_tuple, []).append(res)

            local_bonus_weight = 0.2
            epsilon = 1e-6
            for outer_point, group in grouped_results.items():
                if len(group) <= 1:
                    continue
                diameters = [res.get('safe_even_diameter') for res in group if res.get('safe_even_diameter') is not None]
                if not diameters:
                    continue
                min_diam_group = min(diameters)
                max_diam_group = max(diameters)
                if max_diam_group - min_diam_group > epsilon:
                    for res in group:
                        current_diam = res.get('safe_even_diameter')
                        if current_diam is not None:
                            bonus_factor = (current_diam - min_diam_group) / (max_diam_group - min_diam_group + epsilon)
                            bonus_score = max(0, min(1, bonus_factor))
                            original_score = res.get('final_score', 0)
                            score_adjustment = bonus_score * local_bonus_weight
                            res['final_score'] = original_score + score_adjustment
                            if 'scores' not in res:
                                res['scores'] = {}
                            res['scores']['local_diameter_bonus'] = score_adjustment

            # 调整后排序
            regular_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)

            # 组合最终结果（Angular-geometry）
            final_results_to_show = copy.deepcopy(regular_plans)
            if special_fallback_plan:
                final_results_to_show.append(special_fallback_plan)

            # 构建Horizontal-position结果集
            horizontal_regular_plans = copy.deepcopy(regular_plans)
            for plan in final_results_to_show:
                plan['coverage_method'] = 'angle'
            for plan in horizontal_regular_plans:
                plan['coverage_method'] = 'horizontal'
                horizontal_coverage = plan.get('coverage_rate_horizontal', 0)
                plan['is_valid'] = horizontal_coverage >= COVERAGE_THRESHOLD
            horizontal_regular_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)
            horizontal_fallback = None
            if special_fallback_plan:
                horizontal_fallback = copy.deepcopy(special_fallback_plan)
                horizontal_fallback['coverage_method'] = 'horizontal'
                horizontal_coverage = horizontal_fallback.get('coverage_rate_horizontal', 0)
                horizontal_fallback['is_valid'] = horizontal_coverage >= COVERAGE_THRESHOLD
                horizontal_fallback['need_cover'] = horizontal_coverage < COVERAGE_THRESHOLD
            horizontal_results = horizontal_regular_plans
            if horizontal_fallback:
                horizontal_results.append(horizontal_fallback)
            combined_results = final_results_to_show + horizontal_results

            # 保存合并后的完整结果
            self.initial_generation_results = copy.deepcopy(combined_results)

            # 数据处理耗时
            data_process_end = time.time()
            print(f"数据处理时间: {data_process_end - data_process_start:.4f}秒")

            # 更新列表与UI
            self.results = combined_results
            self.update_plan_list()

            # 更新进度：90%
            self.progress_bar.setValue(90)
            self.progress_bar.setFormat("Updating the interface...")
            QApplication.processEvents()

            if self.results and len(self.results) > 0:
                self.current_index = 0
                self.plan_list.setCurrentRow(0)
                self.update_ui()
                self.save_btn.setEnabled(True)
                self.revert_btn.setEnabled(False)

                angle_valid_count = sum(1 for r in self.results if self._check_plan_validity(r) and r.get('coverage_method') == 'angle' and not r.get('is_special_fallback', False))
                horizontal_valid_count = sum(1 for r in self.results if r.get('is_valid', True) and r.get('coverage_method') == 'horizontal' and not r.get('is_special_fallback', False))
                fallback_present = special_fallback_plan is not None
                final_message = f"Processing completed — valid angular-geometry plans: {angle_valid_count}; valid horizontal-position plans: {horizontal_valid_count}"
                if fallback_present:
                    final_message += "; fallback plan available"
                self.statusBar().showMessage(final_message)

                self.progress_bar.setValue(100)
                self.progress_bar.setFormat("Processing completed")
                QApplication.processEvents()

                import threading
                def hide_progress_bar():
                    import time as _t
                    _t.sleep(2)
                    try:
                        self.progress_bar.setVisible(False)
                    except Exception:
                        pass
                threading.Thread(target=hide_progress_bar, daemon=True).start()
            else:
                self.current_index = -1
        except Exception as e:
            self.statusBar().showMessage(f"Error processing case: {str(e)}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Processing error", f"Error processing case: {str(e)}")
            self.current_index = -1
            self.results = []
            self.plan_list.clear()
            self.image_label.clear()
            self.details_label.clear()
            self.save_btn.setEnabled(False)
            self.revert_btn.setEnabled(False)
            self.progress_bar.setVisible(False)
        finally:
            try:
                if hasattr(self, 'core_thread'):
                    self.core_thread.quit()
                    self.core_thread.wait()
            except Exception:
                pass
            self.generate_btn.setEnabled(True)

    def _on_batch_progress(self, value, text):
        try:
            v = max(0, min(100, int(value)))
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(v)
            self.progress_bar.setFormat(text or f"Processing: {v}%")
            QApplication.processEvents()
        except Exception:
            pass

    def _on_batch_error(self, message):
        try:
            self.statusBar().showMessage(f"Batch-processing error: {message}")
        except Exception:
            pass

    def _on_batch_file_finished(self, file_name, results_or_best, processed_image_width):
        try:
            self.current_file = file_name
            # 兼容处理：既支持传入单个结果，也支持传入结果列表
            if isinstance(results_or_best, list):
                self.results = results_or_best
            elif isinstance(results_or_best, dict):
                self.results = [results_or_best]
            else:
                self.results = []
            self.current_index = 0
            if processed_image_width:
                self.current_image_width = processed_image_width
            # 确保每个结果包含覆盖方法标识，默认归为Angular-geometry，便于列表逻辑分组
            try:
                for r in self.results:
                    if isinstance(r, dict) and 'coverage_method' not in r:
                        r['coverage_method'] = 'angle'
            except Exception:
                pass
            # RefreshRanked Plans（该方法会生成最终展示列表并覆盖 self.results）
            self.update_plan_list()
            # 在展示列表中Select评分最高的方案
            if self.results:
                try:
                    best_idx = max(range(len(self.results)), key=lambda i: self.results[i].get('final_score', 0))
                except Exception:
                    best_idx = 0
                # 仅保留评分最高的方案到列表中（Batch Process只显示保存的方案）
                best_plan = self.results[best_idx]
                self.results = [best_plan]
                self.current_index = 0
            # 使用统一的更新入口Refresh图像与详情
            self.update_ui()
            # 在批量模式下强制处理事件，确保图像与详情及时Refresh
            try:
                from PyQt5.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                pass
            # 启用保存按钮，与单文件流程一致
            try:
                self.save_btn.setEnabled(True)
                self.revert_btn.setEnabled(False)
            except Exception:
                pass
            # Save Current Plan JSON
            self.save_current_plan()
        except Exception as e:
            try:
                self.statusBar().showMessage(f"Error updating the interface or saving the plan: {e}")
            except Exception:
                pass

    def _on_batch_done(self, success, skip):
        try:
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Batch processing completed")
            QApplication.processEvents()
            self.statusBar().showMessage(f"Batch complete: succeeded {success}; skipped {skip}")
            try:
                from planning_core import _log
                _log("Batch Processing Complete")
            except Exception:
                pass
            import threading
            def _hide():
                import time as _t
                _t.sleep(2)
                try:
                    self.progress_bar.setVisible(False)
                except Exception:
                    pass
            threading.Thread(target=_hide, daemon=True).start()
        finally:
            try:
                if hasattr(self, 'batch_thread'):
                    self.batch_thread.quit()
                    self.batch_thread.wait()
            except Exception:
                pass

    def update_plan_list(self):
        """更新Ranked Plans"""
        self.plan_list.clear()
        print(f"DEBUG: update_plan_list called with {len(self.results)} results initially.")  # DEBUG

        # === 分离Angular-geometry和Horizontal-position plans ===
        angle_plans = [r for r in self.results if r.get('coverage_method') == 'angle']
        horizontal_plans = [r for r in self.results if r.get('coverage_method') == 'horizontal']

        print(f"DEBUG: 分离后: Angular-geometry {len(angle_plans)} 个, Horizontal-position {len(horizontal_plans)} 个")  # DEBUG

        # === 处理Angular-geometry plans ===
        # 分离备选方案和常规方案
        angle_special_fallback_plan = None
        angle_regular_plans_temp = []
        for result in angle_plans:
            if result.get('is_special_fallback', False):
                angle_special_fallback_plan = result
                print("DEBUG: Found angle special fallback plan.")  # DEBUG
            else:
                angle_regular_plans_temp.append(result)

        # 按照类型分类常规方案
        angle_valid_plans = []
        angle_invalid_plans = []
        for result in angle_regular_plans_temp:
            if result.get('is_valid', False):
                angle_valid_plans.append(result)
            else:
                angle_invalid_plans.append(result)

        # 对各组常规方案按评分排序
        angle_valid_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        angle_invalid_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)

        # 将有效方案和无效方案组合
        all_angle_regular_plans = angle_valid_plans + angle_invalid_plans

        # --- 添加评分过滤逻辑 (仅对常规方案) ---
        filtered_angle_regular_plans = []
        remaining_slots = 5  # 最多显示5个常规方案

        if all_angle_regular_plans:
            # 添加第一个常规方案
            filtered_angle_regular_plans.append(all_angle_regular_plans[0])
            remaining_slots -= 1

            # 继续添加差异足够大的其他常规方案
            for i in range(1, len(all_angle_regular_plans)):
                if remaining_slots <= 0:
                    break

                current_score = all_angle_regular_plans[i].get('final_score', 0)
                # 与最后添加的常规方案比较
                last_added_score = filtered_angle_regular_plans[-1].get('final_score', 0)

                # 只有评分差异较大才添加
                if last_added_score - current_score >= 0.01:
                    filtered_angle_regular_plans.append(all_angle_regular_plans[i])
                    remaining_slots -= 1
                else:
                    print(f"Angular-geometry常规方案 {i + 1} (Score: {current_score:.4f}) 因与前一方案评分过近 (<0.01) 而被过滤")

        # --- 组合最终显示的Angular-geometry plans列表 ---
        final_angle_results = filtered_angle_regular_plans  # 先放过滤后的常规方案
        if angle_special_fallback_plan:
            final_angle_results.append(angle_special_fallback_plan)  # 最后添加备选方案

        # === 处理Horizontal-position plans ===
        # 分离备选方案和常规方案
        horizontal_special_fallback_plan = None
        horizontal_regular_plans_temp = []
        for result in horizontal_plans:
            if result.get('is_special_fallback', False):
                horizontal_special_fallback_plan = result
                print("DEBUG: Found horizontal special fallback plan.")  # DEBUG
            else:
                horizontal_regular_plans_temp.append(result)

        # === 修改：直接对所有Horizontal-position常规方案进行多级排序 ===
        horizontal_regular_plans_temp.sort(
            key=lambda x: (x.get('is_valid', False), x.get('coverage_rate_horizontal', 0), x.get('final_score', 0)),
            reverse=True  # is_valid=True优先, coverage高优先, score高优先
        )
        print("DEBUG: Sorted horizontal regular plans by (is_valid, coverage_horizontal, score).")

        # --- 添加评分过滤逻辑 (应用于排序后的列表) ---
        filtered_horizontal_regular_plans = []
        remaining_slots = 5  # 最多显示5个常规方案

        if horizontal_regular_plans_temp:
            # 添加第一个方案 (排序后的最佳方案)
            filtered_horizontal_regular_plans.append(horizontal_regular_plans_temp[0])
            remaining_slots -= 1

            # 继续添加差异足够大的其他常规方案
            for i in range(1, len(horizontal_regular_plans_temp)):
                if remaining_slots <= 0:
                    break

                current_plan = horizontal_regular_plans_temp[i]
                last_added_plan = filtered_horizontal_regular_plans[-1]

                # 比较评分 (仍然基于原始评分进行过滤)
                current_score = current_plan.get('final_score', 0)
                last_added_score = last_added_plan.get('final_score', 0)

                # 只有评分差异较大才添加
                if last_added_score - current_score >= 0.01:
                    filtered_horizontal_regular_plans.append(current_plan)
                    remaining_slots -= 1
                else:
                    print(
                        f"Horizontal-position常规方案 (Index {i}, Score: {current_score:.4f}) 因与前一方案评分过近 (<0.01) 而被过滤")

        # --- 组合最终显示的Horizontal-position plans列表 ---
        final_horizontal_results = filtered_horizontal_regular_plans  # 先放过滤后的常规方案
        if horizontal_special_fallback_plan:
            final_horizontal_results.append(horizontal_special_fallback_plan)  # 最后添加备选方案

        # === 合并两种方法的最终结果 ===
        final_results_to_display = final_angle_results + final_horizontal_results

        # 如果最终列表为空，可能是过滤后没有常规方案且没有备选方案
        if not final_results_to_display:
            print("警告：No plans are available for display")
            # 可以Select显示一条消息，或者不显示任何内容
            # 这里不尝试重新计算，避免无限循环
            self.results = []  # 清空结果
            return

        # --- 更新最终结果变量 ---
        self.results = final_results_to_display  # 更新 self.results 以匹配列表显示
        print(f"DEBUG: self.results updated. Count: {len(self.results)}")  # DEBUG

        # === 显示Ranked Plans ===
        print("DEBUG: Starting to add items to plan_list...")  # DEBUG

        # 添加Angular-geometry plans
        if final_angle_results:
            angle_header_item = QListWidgetItem("=== Angular-geometry Pathway ===")
            angle_header_item.setFlags(angle_header_item.flags() & ~Qt.ItemIsSelectable)
            angle_header_item.setBackground(QColor(220, 220, 255))  # 浅蓝色背景
            self.plan_list.addItem(angle_header_item)

            for i, result in enumerate(final_angle_results):
                self._add_plan_to_list(i, result, "Angular-geometry")

        # 添加Horizontal-position plans
        if final_horizontal_results:
            horizontal_header_item = QListWidgetItem("=== Horizontal-position Pathway ===")
            horizontal_header_item.setFlags(horizontal_header_item.flags() & ~Qt.ItemIsSelectable)
            horizontal_header_item.setBackground(QColor(220, 255, 220))  # 浅绿色背景
            self.plan_list.addItem(horizontal_header_item)

            for i, result in enumerate(final_horizontal_results):
                self._add_plan_to_list(i, result, "Horizontal-position")

        print("DEBUG: Finished adding items to plan_list.")  # DEBUG

        # UI处理结束计时
        ui_end_time = time.time()
        ui_duration = ui_end_time - ui_start_time
        print(f"\nUI处理结束时间: {time.strftime('%H:%M:%S', time.localtime(ui_end_time))}")
        print(f"UI总处理耗时: {ui_duration:.3f}秒")
        print(f"=== UI处理结束 ===\n")

    def _add_plan_to_list(self, index, result, method_prefix):
        """添加方案到列表的辅助方法"""
        is_valid = result.get('is_valid', False)
        is_special_fallback = result.get('is_special_fallback', False)
        score = result.get('final_score', 0)

        # 创建列表项
        if is_special_fallback:
            status_text = "[Special fallback]"
            item_prefix = f"{method_prefix} fallback plan"
        elif is_valid:
            status_text = "[Valid]"
            item_prefix = f"{method_prefix} plan {index + 1}"
        else:
            status_text = "[Outside constraints]"
            item_prefix = f"{method_prefix} plan {index + 1}"

        item_text = f"{item_prefix} {status_text}"
        item_text += f"\nScore: {score:.4f}"

        # 添加标准直径信息
        if 'safe_even_diameter' in result and result['safe_even_diameter']:
            item_text += f"\nStandard cup diameter: {result['safe_even_diameter']}"

        # 添加特殊备选方案的Cup bone coverage和备注信息
        if is_special_fallback:
            # 使用适当的Cup bone coverage值
            if method_prefix == "Angular-geometry":
                coverage_rate = result.get('coverage_rate_angle')
            else:
                coverage_rate = result.get('coverage_rate_horizontal')

            if coverage_rate is not None:
                item_text += f"\nAcetabular cup bone coverage: {coverage_rate:.1f}%"

            if result.get('need_cover', False):  # 直接从结果获取是否需要盖子
                item_text += "\nNote: Augmentation is required"

        item = QListWidgetItem(item_text)
        self.plan_list.addItem(item)

        if method_prefix == "Horizontal-position":  # 只针对Horizontal-position plans进行详细打印
            print(f"DEBUG: Horizontal-position plans {index + 1} 详情:")
            print(f"  - coverage_rate_horizontal: {result.get('coverage_rate_horizontal')}")
            print(f"  - circle_to_curve2_distance: {result.get('circle_to_curve2_distance')}")
            print(f"  - is_valid in dict: {result.get('is_valid')}")  # 直接看字典里的 is_valid

            # 可以再用 _check_plan_validity 校验一次，看看结果是否一致
            rechecked_valid = self._check_plan_validity(result)
            print(f"  - rechecked_is_valid by _check_plan_validity: {rechecked_valid}")

    def init_chat_dialog(self):
        return None

    def modify_html_for_webchannel(self, html_content):
        return html_content

    def _on_shortcut_next(self):
        try:
            idx = self.file_combo.currentIndex()
            if idx < self.file_combo.count() - 1:
                self.file_combo.setCurrentIndex(idx + 1)
            else:
                self.statusBar().showMessage("This is the last plan")
        except Exception:
            pass

    def _on_shortcut_prev(self):
        try:
            idx = self.file_combo.currentIndex()
            if idx > 0:
                self.file_combo.setCurrentIndex(idx - 1)
            else:
                self.statusBar().showMessage("This is the first plan")
        except Exception:
            pass

    def on_plan_selected(self, item):
        """当用户Select方案时触发"""
        # 获取选中的物理行号
        selected_row = self.plan_list.row(item)

        # 计算选中行之前的标题行数量
        header_count = 0
        # 检查是否存在Angular-geometry标题行
        angle_header_item = self.plan_list.findItems("=== Angular-geometry Pathway ===", Qt.MatchExactly)
        if angle_header_item and self.plan_list.row(angle_header_item[0]) < selected_row:
            header_count += 1

        # 检查是否存在Horizontal-position标题行
        horizontal_header_item = self.plan_list.findItems("=== Horizontal-position Pathway ===", Qt.MatchExactly)
        if horizontal_header_item and self.plan_list.row(horizontal_header_item[0]) < selected_row:
            header_count += 1

        # 计算在 self.results 中的实际索引
        actual_index = selected_row - header_count

        if 0 <= actual_index < len(self.results):
            if actual_index != self.current_index:
                self.current_index = actual_index
                self.zoom_factor = 1.0  # Reset zoom when selecting a new plan
                # Reset checkboxes to default when selecting a new plan
                # Block signals temporarily to avoid triggering update multiple times
                for checkbox in self.visibility_checkboxes.values():
                    checkbox.blockSignals(True)
                    checkbox.setChecked(True)
                    checkbox.blockSignals(False)
                try:
                    self._sync_display_menu_with_checkboxes()
                except Exception:
                    pass
                self.update_ui()
            # 启用保存按钮
            self.save_btn.setEnabled(True)
            try:
                if hasattr(self, 'action_save'):
                    self.action_save.setEnabled(True)
            except Exception:
                pass
        else:
            # 处理无效索引的情况，例如清除详情
            print(
                f"警告: 点击了无效的行或标题行 (Row: {selected_row}, HeaderCount: {header_count}, ActualIndex: {actual_index})")
            # 可以Select不改变当前Select，或者清除显示
            # self.current_index = -1
            # self.update_ui()
            # self.save_btn.setEnabled(False)
            # 保持当前状态可能更好，避免误Planning清空
            pass

    def update_ui(self):
        """更新UI显示当前选中的方案"""
        # 在RefreshUI时同步Case Selection下拉框显示为Current case名
        try:
            if hasattr(self, 'file_combo') and getattr(self, 'current_file', None):
                idx = self.file_combo.findText(self.current_file)
                self.file_combo.blockSignals(True)
                if idx != -1:
                    if self.file_combo.currentIndex() != idx:
                        self.file_combo.setCurrentIndex(idx)
                self.file_combo.blockSignals(False)
            if hasattr(self, 'file_list') and getattr(self, 'current_file', None):
                items = self.file_list.findItems(self.current_file, Qt.MatchExactly)
                if items:
                    self.file_list.blockSignals(True)
                    self.file_list.setCurrentItem(items[0])
                    self.file_list.scrollToItem(items[0])
                    self.file_list.blockSignals(False)
        except Exception:
            try:
                self.file_combo.blockSignals(False)
            except Exception:
                pass

        if not self.results or self.current_index >= len(self.results):
            return

        # 获取当前方案
        result = self.results[self.current_index]

        # 更新图像显示
        self.update_image()

        # 更新详情显示
        self.update_details()

    def _make_json_safe(self, obj):
        """递归转换数据结构为可 JSON 序列化的格式，处理 numpy 类型、元组等。"""
        try:
            import numpy as _np
        except Exception:
            _np = None

        if isinstance(obj, dict):
            return {str(k): self._make_json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._make_json_safe(x) for x in obj]
        if _np is not None and isinstance(obj, _np.ndarray):
            return obj.tolist()
        if _np is not None and isinstance(obj, _np.generic):
            return obj.item()
        if isinstance(obj, (float, int, str, bool)) or obj is None:
            return obj
        try:
            return str(obj)
        except Exception:
            return None

    def update_image(self):
        """更新图像显示"""
        print("DEBUG IMG: update_image called.")  # DEBUG
        # Reset original pixmap and displayed outer point for the new image
        self.original_pixmap = None
        self.current_outer_point_display = None  # Reset stored outer point

        # 确保核心模块中的全局路径变量已设置，避免可视化过程中因None导致路径拼接报错
        try:
            import planning_core as _core
            # 使用空字符串作为后备，避免 os.path.join(None, ...) 报错
            _core.FOLDER_A = self.folder_a or ""
            _core.FOLDER_B = self.folder_b or ""
            _core.FOLDER_C = self.folder_c or ""
            _core.FOLDER_C4 = self.folder_c4 or ""
            _core.FOLDER_C3 = self.folder_c3 or ""
            _core.FILE_D = self.file_d or ""
        except Exception as _e_set_globals:
            print(f"WARN IMG: Failed to set core global folders before visualize: {_e_set_globals}")

        # 优先使用Saved的PNG（如果存在），确保与保存前视觉一致
        cache_key_png = ('png', self.current_index)
        if cache_key_png in self.image_cache:
            pixmap = self.image_cache[cache_key_png]
            print(f"DEBUG IMG: Loaded PNG from cache for key {cache_key_png}")  # DEBUG
            self.original_pixmap = pixmap
            self._apply_zoom()
            return

        # Get current visibility flags
        visibility_flags = self._get_visibility_flags()

        # 检查是否有缓存的图像 (Consider cache invalidation based on flags?)
        # For now, we regenerate each time flags change via _update_visualization_with_flags
        # This check might be less useful now unless caching includes flags.
        cache_key = (self.current_index, tuple(sorted(visibility_flags.items())))  # Complex key includes curve3 now
        if cache_key in self.image_cache:
            pixmap = self.image_cache[cache_key]
            print(f"DEBUG IMG: Loaded image from cache for key {cache_key}")  # DEBUG
            self.original_pixmap = pixmap
            self._apply_zoom()
            return

        # else:
        if self.current_index < 0:  # No plan selected
            print("DEBUG IMG: No plan selected, clearing image label.")  # DEBUG
            self.image_label.setText("Select a case and Crowe class")
            self.original_pixmap = None
            self._apply_zoom()
            return

        # 从当前方案渲染图像
        result = self.results[self.current_index]
        print(f"DEBUG IMG: Processing plan index {self.current_index}")  # DEBUG
        # Store the outer point used for this visualization
        self.current_outer_point_display = result.get('outer_point')

        try:
            # 使用原程序中的visualize_results函数生成图像
            from planning_core import visualize_results, read_points_from_txt, FOLDER_A, FOLDER_B, FOLDER_C, \
                FOLDER_C4, FILE_D

            # 构建所需文件路径
            original_img_path = os.path.join(self.folder_a, f'{self.current_file}.png')
            txt_path = os.path.join(self.folder_c, f'{self.current_file}.txt')
            print(f"DEBUG IMG: Original Img Path: {original_img_path}")  # DEBUG
            print(f"DEBUG IMG: TXT Path: {txt_path}")  # DEBUG

            # 读取坐标文件（可能不存在）
            points = read_points_from_txt(txt_path)

            # 获取方案参数（统一获取，支持无TXT回退）
            center_point = result.get('center_point')
            outer_point = result.get('outer_point')
            line6_angle = result.get('line6_angle_rad')
            line7_angle = result.get('line7_angle_rad')
            line1_eq = result.get('line1_eq')
            line4_eq = result.get('line4_eq')  # May be None
            # Use standard diameter if available, otherwise calculated pixel diameter
            circle_diameter = result.get('circle_diameter')
            standard_diameter = result.get('safe_even_diameter')
            scale = result.get('scale_factor', 1.0)
            if standard_diameter is not None and scale > 0:
                display_diameter = standard_diameter / scale
                print(
                    f"DEBUG IMG: Using standard diameter {standard_diameter} -> pixel diameter {display_diameter:.2f}")  # DEBUG
            else:
                display_diameter = circle_diameter
                print(f"DEBUG IMG: Using calculated pixel diameter {display_diameter:.2f}")  # DEBUG

            try:
                curve2_filename = self.current_file.replace('.png', '') + '_bks.png'
                curve2_img_path = os.path.join(self.folder_c4, curve2_filename)
                cache = getattr(self, 'curve_cache', {})
                image_cache = getattr(self, 'image_cache', None)
                radius_check = display_diameter / 2.0 if display_diameter else 0
                min_dist_curve2 = None
                if center_point is not None and radius_check > 0 and curve2_img_path:
                    min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(
                        center_point, radius_check, curve2_img_path, cache, None, image_cache)
                    if (min_dist_curve2 is None or min_dist_curve2 < 1.0) and scale and scale > 0:
                        min_pixel_diameter = MIN_SAFE_DIAMETER / scale
                        step = 2.0 / scale
                        while (min_dist_curve2 is None or min_dist_curve2 < 1.0) and display_diameter - step >= min_pixel_diameter:
                            display_diameter -= step
                            radius_check = display_diameter / 2.0
                            min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(
                                center_point, radius_check, curve2_img_path, cache, None, image_cache)
                if min_dist_curve2 is not None:
                    result['circle_to_curve2_distance'] = min_dist_curve2
                    result['circle_to_curve2_distance_actual'] = min_dist_curve2 * scale
            except Exception:
                pass

            is_special_fallback = result.get('is_special_fallback', False)
            print(f"DEBUG IMG: Calling visualize_results with:")  # DEBUG
            print(f"  center_point: {center_point}")  # DEBUG
            print(f"  outer_point: {outer_point}")  # DEBUG
            print(f"  line6_angle: {line6_angle}")  # DEBUG
            print(f"  line7_angle: {line7_angle}")  # DEBUG
            print(f"  circle_diameter: {display_diameter}")  # DEBUG
            print(f"  is_special_fallback: {is_special_fallback}")  # DEBUG

            # 计算 line1_points：优先使用TXT点，否则根据 line1_eq 和图像尺寸推算
            if points and len(points) >= 2:
                line1_points = points[:2]
            else:
                # 无TXT文件或内容不足，使用 line1_eq 构造两点
                if not line1_eq or len(line1_eq) < 3:
                    print("ERROR IMG: Missing line1_eq; cannot render overlays without TXT.")
                    self.image_label.setText("The plan lacks required geometric parameters and cannot be rendered")
                    self.original_pixmap = None
                    self._apply_zoom()
                    return
                try:
                    # 获取图像尺寸
                    try:
                        from PIL import Image as _PILImage
                        with _PILImage.open(original_img_path) as _im:
                            img_width, img_height = _im.size
                    except Exception as e_img:
                        print(f"WARN IMG: Could not read image size: {e_img}. Using fallback 1024x1024.")
                        img_width, img_height = 1024, 1024

                    a1, b1, c1 = line1_eq
                    if abs(b1) > 1e-8:
                        # y = (-a*x - c) / b，取左右边界两点
                        x0, x1 = 0, max(1, img_width - 1)
                        y0 = (-a1 * x0 - c1) / b1
                        y1 = (-a1 * x1 - c1) / b1
                        line1_points = [(x0, y0), (x1, y1)]
                    else:
                        # 垂直线：x = -c/a，取上下边界两点
                        x_const = -c1 / (a1 if abs(a1) > 1e-8 else 1.0)
                        y0, y1 = 0, max(1, img_height - 1)
                        line1_points = [(x_const, y0), (x_const, y1)]
                except Exception as e_lp:
                    print(f"ERROR IMG: Failed to construct line1_points from line1_eq: {e_lp}")
                    self.image_label.setText("The inter-teardrop line could not be constructed for rendering")
                    self.original_pixmap = None
                    self._apply_zoom()
                    return

            # 检查是否有保存的曲线数据
            saved_curve_data = result.get('saved_curve_data')
            print(f"DEBUG UPDATE_IMAGE: saved_curve_data = {saved_curve_data}")
            if saved_curve_data:
                print(f"DEBUG UPDATE_IMAGE: 曲线数据键: {list(saved_curve_data.keys())}")
                for curve_name, points in saved_curve_data.items():
                    if isinstance(points, list):
                        print(f"DEBUG UPDATE_IMAGE: {curve_name}: {len(points)} 个点")
            else:
                print(f"DEBUG UPDATE_IMAGE: 没有找到保存的曲线数据")

            # 判断当前方案类型，决定是否固定半圆绘制范围
            fixed_semicircle_range = None
            saved_plan_header = self.plan_list.findItems("=== Saved Plan ===", Qt.MatchExactly)
            if saved_plan_header:
                # 如果存在Saved方案标题，说明当前显示的是Saved的方案
                # 使用保存方案中的实际几何参数来计算正确的半圆范围
                try:
                    if (line6_angle is not None and outer_point is not None and
                        center_point is not None and len(outer_point) >= 2 and len(center_point) >= 2):

                        # 确保line6_angle是弧度值
                        line6_angle_rad = line6_angle if isinstance(line6_angle, (int, float)) else 0

                        # 计算线6的方向向量
                        line6_vector_x = math.cos(line6_angle_rad)
                        line6_vector_y = math.sin(line6_angle_rad)

                        # 计算线6法向量（指向其中一个半圆），旋转+90度: (dx, dy) -> (-dy, dx)
                        perp_dx = -line6_vector_y
                        perp_dy = line6_vector_x

                        # 计算中心点到外沿点的向量
                        outer_vec_x = float(outer_point[0]) - float(center_point[0])
                        outer_vec_y = float(outer_point[1]) - float(center_point[1])

                        # 计算点积，判断外沿点在法向量的哪一侧
                        dot_product = outer_vec_x * perp_dx + outer_vec_y * perp_dy

                        if dot_product >= 0:  # 外沿点在法向量指向的一侧，绘制0-180度
                            fixed_semicircle_range = (0, math.pi)
                        else:  # 外沿点在法向量的反方向一侧，绘制180-360度
                            fixed_semicircle_range = (math.pi, 2 * math.pi)

                        print(f"DEBUG UPDATE_IMAGE: Saved方案，计算得到半圆范围: {fixed_semicircle_range}, dot_product: {dot_product}")
                    else:
                        print(f"DEBUG UPDATE_IMAGE: Saved方案，但缺少必要参数，使用默认逻辑")
                except Exception as e:
                    print(f"DEBUG UPDATE_IMAGE: 计算fixed_semicircle_range时出错: {e}，使用默认逻辑")
                    fixed_semicircle_range = None

            # 生成可视化结果（不显示窗口），传递flags和保存的曲线数据
            result_img = visualize_results(
                original_img_path, line1_points, outer_point, center_point,
                line6_angle, line7_angle, line1_eq, line4_eq,
                circle_diameter=display_diameter,
                scale=scale,
                ui_mode=True,
                visibility_flags=visibility_flags,
                is_special_fallback=is_special_fallback,
                show_highest_point=visibility_flags.get('highest_point', False),
                show_lowest_point=visibility_flags.get('lowest_point', False),
                saved_curve_data=saved_curve_data,
                fixed_semicircle_range=fixed_semicircle_range
            )

            if result_img is None:
                print("ERROR IMG: visualize_results returned None!")  # DEBUG
                raise ValueError("visualize_results failed to generate image.")

            print(
                f"DEBUG IMG: visualize_results returned image of shape {result_img.shape}, dtype {result_img.dtype}")  # DEBUG

            # 移除界面层对线6端点和连线的叠加绘制，避免与核心渲染重复

            height, width, channel = result_img.shape
            bytes_per_line = 3 * width
            result_img_rgb = cv2.cvtColor(result_img, cv2.COLOR_BGR2RGB)

            q_img = QImage(result_img_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(q_img)
            print("DEBUG IMG: QPixmap created successfully.")  # DEBUG

            # 保存到缓存 (Consider using cache_key)
            # self.image_cache[cache_key] = pixmap
        except Exception as e:
            self.statusBar().showMessage(f"Error rendering the plan: {str(e)}")
            print(f"ERROR IMG: Exception during image generation/conversion: {str(e)}")  # DEBUG
            import traceback
            traceback.print_exc()  # Print full traceback to console
            self.image_label.setText(f"Error rendering the plan: {str(e)}")
            self.original_pixmap = None  # Ensure no pixmap is stored
            self._apply_zoom()  # Clear the label if needed
            return

        # Store the original pixmap and apply zoom
        self.original_pixmap = pixmap
        print("DEBUG IMG: Stored original pixmap.")  # DEBUG
        self._apply_zoom()

    def _apply_zoom(self):
        """Applies the current zoom factor to the original pixmap and updates the label."""
        try:
            if not self.original_pixmap or self.original_pixmap.isNull():
                self.image_label.clear()
                self.image_label.setText("No radiograph is available, or the radiograph could not be loaded")
                return

            base_w = int(self.original_pixmap.width())
            base_h = int(self.original_pixmap.height())
            if base_w <= 0 or base_h <= 0:
                self.image_label.clear()
                self.image_label.setText("No radiograph is available, or the radiograph could not be loaded")
                return

            try:
                z = float(getattr(self, "zoom_factor", 1.0))
            except Exception:
                z = 1.0
            z = max(ZOOM_MIN, min(z, ZOOM_MAX))

            max_dim = 12000
            z_limit = min(max_dim / float(base_w), max_dim / float(base_h))
            if z > z_limit:
                z = max(ZOOM_MIN, min(z_limit, ZOOM_MAX))
            self.zoom_factor = z

            new_width = max(1, int(base_w * z))
            new_height = max(1, int(base_h * z))

            scaled_pixmap = self.original_pixmap.scaled(
                new_width, new_height, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
        except Exception:
            try:
                self.image_label.clear()
                self.image_label.setText("Zoom failed")
            except Exception:
                pass

    def update_details(self):
        """更新详情显示"""
        if not self.results or self.current_index >= len(self.results):
            return

        result = self.results[self.current_index]
        is_valid = result.get('is_valid', False)
        scale = result.get('scale_factor', 1.0)
        is_fallback = result.get('is_fallback', False)
        coverage_method = result.get('coverage_method', 'angle')  # 默认为Angular-geometry

        # 准备详情文本
        status_text = ""
        if is_fallback:
            status_text = "[Fallback plan]"
        elif is_valid:
            status_text = "[Valid]"
        else:
            status_text = "[Outside constraints]"

        # 显示方案编号与使用的Cup bone coverage方法
        method_text = "Angular-geometry" if coverage_method == "angle" else "Horizontal-position"
        details = f"<h2>{method_text} plan {self.current_index + 1} {status_text}</h2>"
        details += f"<p><b>Crowe class:</b> {_crowe_label(self.current_level)}</p>"

        details += f"<p><b>Score:</b> {result.get('final_score', 0):.4f}</p>"
        details += f"<p><b>Lateral acetabular edge:</b> ({result.get('outer_point', (0, 0))[0]:.1f}, {result.get('outer_point', (0, 0))[1]:.1f})</p>"

        # --- 计算和添加新信息 ---
        line6_angle_rad = result.get('line6_angle_rad', 0)
        line7_angle_rad = result.get('line7_angle_rad', 0)
        line1_eq = result.get('line1_eq')

        # 1. 计算线6与线7夹角
        angle67_rad = (line7_angle_rad - line6_angle_rad + math.pi) % (2 * math.pi) - math.pi
        angle67_deg_abs = abs(math.degrees(angle67_rad))
        details += f"<p><b>Cup-orientation/coverage-boundary angle:</b> {angle67_deg_abs:.1f}°</p>"

        # 2. 显示两种Cup bone coverage，并突出显示当前方法使用的Cup bone coverage
        coverage_angle = result.get('coverage_rate_angle', 0)
        coverage_horizontal = result.get('coverage_rate_horizontal', 0)

        if coverage_method == "angle":
            details += f"<p><b style='color:blue;'>Cup bone coverage (angular geometry):</b> {coverage_angle:.1f}% <b>(active pathway)</b></p>"
            details += f"<p><b>Cup bone coverage (horizontal position):</b> {coverage_horizontal:.1f}%</p>"
        else:
            details += f"<p><b>Cup bone coverage (angular geometry):</b> {coverage_angle:.1f}%</p>"
            details += f"<p><b style='color:green;'>Cup bone coverage (horizontal position):</b> {coverage_horizontal:.1f}% <b>(active pathway)</b></p>"

        # need_cover 基于当前方法的Cup bone coverage判断
        if coverage_method == "angle":
            need_cover = coverage_angle < COVERAGE_THRESHOLD
        else:
            need_cover = coverage_horizontal < COVERAGE_THRESHOLD

        if need_cover:
            details += f"<p style='color:red;'><b>Note:</b> Augmentation is required</p>"

        # 3. 计算外展角
        abduction_angle_deg = 0
        if line1_eq:
            a1, b1, c1 = line1_eq
            line1_angle_rad = math.atan2(-a1, b1)
            angle_diff_rad = line6_angle_rad - line1_angle_rad
            norm_angle_diff_rad = (angle_diff_rad + math.pi) % (2 * math.pi) - math.pi
            abduction_angle_deg = abs(math.degrees(norm_angle_diff_rad))
            # Display the acute angle between unoriented lines; keep stored axis angles unchanged.
            abduction_angle_deg = min(abduction_angle_deg, 180.0 - abduction_angle_deg)
        details += f"<p><b>Radiographic cup inclination:</b> {abduction_angle_deg:.1f}°</p>"

        # 原有角度信息
        details += f"<p><b>Cup-orientation axis angle (horizontal reference):</b> {result.get('line6_angle_deg', 0):.1f}°</p>"
        details += f"<p><b>Coverage-boundary angle (horizontal reference):</b> {result.get('line7_angle_deg', 0):.1f}°</p>"

        # 直径信息
        circle_diameter = result.get('circle_diameter', 0)
        details += f"<p><b>Cup diameter (pixels):</b> {circle_diameter:.2f}</p>"
        actual_diameter = circle_diameter * scale
        safe_even_diameter = result.get('safe_even_diameter')
        if safe_even_diameter is not None:
            details += f"<p><b>Calibrated cup diameter:</b> {actual_diameter:.2f}mm → <b>Standard cup diameter:</b> {safe_even_diameter}mm</p>"
        else:
            details += f"<p><b>Calibrated cup diameter:</b> {actual_diameter:.2f}mm (No safe standard diameter)</p>"

        # 距离信息
        dist_line1 = result.get('distance_to_line1', 0)
        details += f"<p><b>Cup centre–inter-teardrop distance:</b> {dist_line1:.2f} px ({dist_line1 * scale:.2f}mm)</p>"
        dist_line4 = result.get('distance_to_line4', 0)
        details += f"<p><b>Cup centre–Köhler distance:</b> {dist_line4:.2f} px ({dist_line4 * scale:.2f}mm)</p>"
        dist_line2 = result.get('distance_to_line2', 0)
        details += f"<p><b>Cup centre–superior iliac line distance:</b> {dist_line2:.2f} px ({dist_line2 * scale:.2f}mm)</p>"
        dist_line3 = result.get('distance_to_line3', 0)
        details += f"<p><b>Cup centre–ischial line distance:</b> {dist_line3:.2f} px ({dist_line3 * scale:.2f}mm)</p>"
        dist_line8 = result.get('distance_to_line8', 0)
        details += f"<p><b>Cup centre–iliac–ischial midpoint line distance:</b> {dist_line8:.2f} px ({dist_line8 * scale:.2f}mm)</p>"

        # 圆到曲线2和曲线3的距离
        if 'circle_to_curve2_distance' in result and result['circle_to_curve2_distance'] is not None:
            dist_pixel_c2 = result['circle_to_curve2_distance']
            dist_actual_c2 = dist_pixel_c2 * scale
            details += f"<p><b>Minimum cup-to-superior-obturator-boundary distance:</b> {dist_pixel_c2:.2f} px, {dist_actual_c2:.2f}mm</p>"
        else:
            details += "<p><b>Minimum cup-to-superior-obturator-boundary distance:</b> Not calculated</p>"

        if 'circle_to_curve3_distance' in result and result['circle_to_curve3_distance'] is not None:
            dist_pixel_c3 = result['circle_to_curve3_distance']
            dist_actual_c3 = dist_pixel_c3 * scale
            details += f"<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> {dist_pixel_c3:.2f} px, {dist_actual_c3:.2f}mm</p>"  # 新增
        else:
            details += "<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> Not calculated</p>"  # 新增

        # 设置富文本
        self.details_label.setText(details)

    def save_current_plan(self):
        """保存当前选中的方案"""
        if not self.results or self.current_index >= len(self.results):
            return

        result = self.results[self.current_index]
        self.save_btn.setEnabled(False)
        self.statusBar().showMessage("Saving plan (JSON)...")

        try:
            # 按需求：JSON 文件名与原图 PNG 同名（不带“方案”编号）
            file_name = f"{self.current_file}"
            save_dir = self._get_save_folder()
            if not save_dir:
                self.statusBar().showMessage("No output folder is configured; the plan cannot be saved")
                return
            try:
                os.makedirs(save_dir, exist_ok=True)
            except Exception:
                pass
            # 直接从文件夹读取曲线数据（与visualize_results中的逻辑一致）
            curve_data = {}
            base_filename = f"{self.current_file}.png"

            # 读取曲线1数据
            curve1_filename = base_filename.replace('.png', '_kjwy.png')
            curve1_img_path = os.path.join(self.folder_b, curve1_filename)
            try:
                from planning_core import read_image_with_pil
                curve1_img = read_image_with_pil(curve1_img_path)
                if curve1_img is not None:
                    curve1_points = np.where(curve1_img == 1)
                    if len(curve1_points[0]) == 0:
                        curve1_points = np.where(curve1_img > 0)
                    if len(curve1_points[0]) > 0:
                        # 转换为(x, y)格式的点列表
                        curve1_points_list = [(int(x), int(y)) for y, x in zip(curve1_points[0], curve1_points[1])]
                        curve_data['curve1_points'] = curve1_points_list
                        print(f"从文件读取曲线1数据: {len(curve1_points_list)} 个点")
            except Exception as e:
                print(f"读取曲线1数据失败: {str(e)}")

            # 读取曲线2数据
            curve2_filename = base_filename.replace('.png', '_bks.png')
            curve2_img_path = os.path.join(self.folder_c4, curve2_filename)
            try:
                curve2_img = read_image_with_pil(curve2_img_path)
                if curve2_img is not None:
                    curve2_points = np.where(curve2_img == 1)
                    if len(curve2_points[0]) == 0:
                        curve2_points = np.where(curve2_img > 0)
                    if len(curve2_points[0]) > 0:
                        # 转换为(x, y)格式的点列表
                        curve2_points_list = [(int(x), int(y)) for y, x in zip(curve2_points[0], curve2_points[1])]
                        curve_data['curve2_points'] = curve2_points_list
                        print(f"从文件读取曲线2数据: {len(curve2_points_list)} 个点")
            except Exception as e:
                print(f"读取曲线2数据失败: {str(e)}")

            # 读取曲线3数据
            curve3_filename = base_filename.replace('.png', '_bkx.png')
            curve3_img_path = os.path.join(self.folder_c3, curve3_filename)
            try:
                curve3_img = read_image_with_pil(curve3_img_path)
                if curve3_img is not None:
                    curve3_points = np.where(curve3_img == 1)
                    if len(curve3_points[0]) == 0:
                        curve3_points = np.where(curve3_img > 0)
                    if len(curve3_points[0]) > 0:
                        # 转换为(x, y)格式的点列表
                        curve3_points_list = [(int(x), int(y)) for y, x in zip(curve3_points[0], curve3_points[1])]
                        curve_data['curve3_points'] = curve3_points_list
                        print(f"从文件读取曲线3数据: {len(curve3_points_list)} 个点")
            except Exception as e:
                print(f"读取曲线3数据失败: {str(e)}")

            # 将曲线数据添加到结果中
            result_with_curves = copy.deepcopy(result)
            result_with_curves['saved_curve_data'] = curve_data
            # 记录当前Crowe Class到结果中，方便导出与复现
            result_with_curves['level'] = self.current_level

            center_point_ep = result_with_curves.get('center_point')
            angle_ep = result_with_curves.get('line6_angle_rad')
            radius_ep = self.get_standard_radius_for_result(result_with_curves)
            if center_point_ep is not None and angle_ep is not None and radius_ep and radius_ep > 0:
                dx_ep = radius_ep * math.cos(angle_ep)
                dy_ep = radius_ep * math.sin(angle_ep)
                p1_ep = [center_point_ep[0] + dx_ep, center_point_ep[1] + dy_ep]
                p2_ep = [center_point_ep[0] - dx_ep, center_point_ep[1] - dy_ep]
                result_with_curves['line6_endpoints'] = [p1_ep, p2_ep]

            # 更新当前方案结果中的曲线数据
            self.results[self.current_index]['saved_curve_data'] = curve_data
            # 同步更新当前方案的Crowe Class
            self.results[self.current_index]['level'] = self.current_level
            if 'line6_endpoints' in result_with_curves:
                self.results[self.current_index]['line6_endpoints'] = result_with_curves['line6_endpoints']

            # 仅保存JSON（不保存txt和png）
            json_path = os.path.join(save_dir, file_name + ".json")
            with open(json_path, 'w', encoding='utf-8') as jf:
                safe_result = self._make_json_safe(result_with_curves)
                json.dump(safe_result, jf, ensure_ascii=False, indent=2)
            self.statusBar().showMessage(f"Plan saved to: {json_path}")

            # Refresh图像显示以使用新的曲线数据
            self.update_image()
        except Exception as e:
            self.statusBar().showMessage(f"Error saving the plan: {str(e)}")
        finally:
            self.save_btn.setEnabled(True)  # 启用保存按钮



    # 已移除 save_all_plans（不再支持保存所有方案）

    def try_load_saved_plans_for_current_file(self):
        """尝试加载Current case的Saved方案（单一文件：原图同名.json）"""
        if not self.current_file:
            return
        save_dir = self._get_save_folder()
        candidates = []
        if save_dir:
            candidates.append(os.path.join(save_dir, f"{self.current_file}.json"))
        folder_a = getattr(self, 'folder_a', '')
        if folder_a and folder_a != save_dir:
            candidates.append(os.path.join(folder_a, f"{self.current_file}.json"))

        jf_path = None
        for p in candidates:
            if p and os.path.exists(p):
                jf_path = p
                break
        if not jf_path:
            return

        try:
            with open(jf_path, 'r', encoding='utf-8') as jf:
                result = json.load(jf)

            # 调试输出：检查加载的数据
            print(f"DEBUG LOAD: 加载方案文件: {jf_path}")
            print(f"DEBUG LOAD: 方案数据键: {list(result.keys())}")
            if 'saved_curve_data' in result:
                curve_data = result['saved_curve_data']
                print(f"DEBUG LOAD: 找到保存的曲线数据")
                print(f"DEBUG LOAD: 曲线数据键: {list(curve_data.keys())}")
                for curve_name, points in curve_data.items():
                    if isinstance(points, list):
                        print(f"DEBUG LOAD: {curve_name}: {len(points)} 个点")
                    else:
                        print(f"DEBUG LOAD: {curve_name}: {points}")
            else:
                print(f"DEBUG LOAD: 未找到saved_curve_data字段")

            # 插入：回填交互依赖，确保导入方案可拖拽
            saved_curve_data = result.get('saved_curve_data', {})
            try:
                curve1_pts = saved_curve_data.get('curve1_points')
                if isinstance(curve1_pts, list) and len(curve1_pts) > 0:
                    self.curve1_points = [(int(p[0]), int(p[1])) for p in curve1_pts]
                    print(f"IMPORT: 使用 JSON 中的曲线1点，共 {len(self.curve1_points)} 个")
                else:
                    base_filename = f"{self.current_file}.png"
                    curve1_filename = base_filename.replace('.png', '_kjwy.png')
                    curve1_img_path = os.path.join(self.folder_b, curve1_filename)
                    try:
                        from planning_core import read_image_with_pil
                        curve1_img = read_image_with_pil(curve1_img_path)
                        if curve1_img is not None:
                            pts = np.where(curve1_img == 1)
                            if len(pts[0]) == 0:
                                pts = np.where(curve1_img > 0)
                            if len(pts[0]) > 0:
                                self.curve1_points = [(int(x), int(y)) for y, x in zip(pts[0], pts[1])]
                                print(f"IMPORT: 从文件读取曲线1点，共 {len(self.curve1_points)} 个")
                            else:
                                self.curve1_points = []
                        else:
                            self.curve1_points = []
                    except Exception as e:
                        print(f"IMPORT: 读取曲线1数据失败: {e}")
                        self.curve1_points = []
            except Exception as e:
                print(f"IMPORT: 回填曲线1点异常: {e}")
                self.curve1_points = []

            try:
                orig_img_path = os.path.join(self.folder_a, f"{self.current_file}.png")
                if os.path.exists(orig_img_path):
                    with Image.open(orig_img_path) as im:
                        self.current_image_width = im.size[0]
                        print(f"IMPORT: 设置 current_image_width = {self.current_image_width}")
                else:
                    print(f"IMPORT: 原图不存在，无法设置 current_image_width: {orig_img_path}")
            except Exception as e:
                print(f"IMPORT: 设置 current_image_width 失败: {e}")

        except Exception as e:
            print(f"读取方案文件失败 {jf_path}: {e}")
            return

        # 更新结果与列表（仅一个Saved方案）
        self.results = [result]
        self.plan_list.clear()
        header_item = QListWidgetItem("=== Saved Plan ===")
        header_item.setFlags(header_item.flags() & ~Qt.ItemIsSelectable)
        header_item.setBackground(QColor(255, 240, 200))  # 浅橙色背景
        self.plan_list.addItem(header_item)
        self._add_plan_to_list(0, result, "Saved")

        # Select并显示该方案
        self.current_index = 0
        self.update_ui()
        # 启用保存按钮
        self.save_btn.setEnabled(True)
        self.statusBar().showMessage("The previously saved plan has been loaded")

    def _check_plan_validity(self, result):
        """检查方案是否满足条件（Cup bone coverage>=80%且不与曲线2相交）"""
        try:
            # 获取必要的数据
            center_point = result.get('center_point')
            radius = self.get_standard_radius_for_result(result)  # 直接使用UI类中的方法
            line6_angle_rad = result.get('line6_angle_rad')
            line7_angle_rad = result.get('line7_angle_rad')
            coverage_method = result.get('coverage_method', 'angle')  # 默认使用Angular-geometry

            if None in (center_point, radius, line6_angle_rad, line7_angle_rad):
                return False

            # 根据Cup bone coverage方法判断
            if coverage_method == 'angle':
                # Angular-geometryCup bone coverage计算
                angle67_rad = (line7_angle_rad - line6_angle_rad + math.pi) % (2 * math.pi) - math.pi
                angle67_deg_abs = abs(math.degrees(angle67_rad))
                coverage_rate = ((180.0 - angle67_deg_abs) / 180.0) * 100.0 if angle67_deg_abs <= 180 else 0
            else:
                # Horizontal-positionCup bone coverage计算
                outer_point = result.get('outer_point')
                if outer_point is None:
                    return False
                active_image_width = self.current_image_width  # Use stored image width
                if active_image_width <= 0:
                    print(
                        "Warning: PlanVisualizationUI._check_plan_validity using invalid image_width for horizontal coverage.")
                coverage_rate = calculate_coverage_horizontal(outer_point, center_point, radius, line6_angle_rad,
                                                              active_image_width)  # Pass active_image_width

            # 检查到曲线2的距离
            min_dist_curve2 = result.get('circle_to_curve2_distance')

            # 约束条件检查：Cup bone coverage>=80%，曲线2/3距离≥2.0 px（如有）
            is_coverage_valid = coverage_rate >= COVERAGE_THRESHOLD
            is_curve2_valid = min_dist_curve2 is None or min_dist_curve2 >= 2.0
            min_dist_curve3 = result.get('circle_to_curve3_distance')
            is_curve3_valid = min_dist_curve3 is None or min_dist_curve3 >= 2.0

            return is_coverage_valid and is_curve2_valid and is_curve3_valid
        except Exception as e:
            print(f"Error checking plan validity: {e}")
            return False

    # 添加get_standard_radius_for_result方法到PlanVisualizationUI类
    def get_standard_radius_for_result(self, result):
        """获取方案的标准半径."""
        try:
            # 首先尝试从 safe_even_diameter 获取
            safe_even_diameter = result.get('safe_even_diameter')
            scale = result.get('scale_factor', 1.0)
            if safe_even_diameter is not None and scale > 0:
                # Convert safe standard diameter (actual units) back to pixels
                pixel_diameter = safe_even_diameter / scale
                return pixel_diameter / 2.0

            # 其次尝试从 circle_diameter 获取
            circle_diameter = result.get('circle_diameter')
            if circle_diameter is not None:
                return circle_diameter / 2.0

            # 最后尝试从中心点和外沿点计算
            center_point = result.get('center_point')
            outer_point = result.get('outer_point')
            if center_point is not None and outer_point is not None:
                # 计算欧氏距离作为近似半径
                dx = center_point[0] - outer_point[0]
                dy = center_point[1] - outer_point[1]
                return math.sqrt(dx * dx + dy * dy)

            # 如果都没有，返回默认值
            return 25.0  # 默认半径
        except Exception as e:
            print(f"计算标准半径时出错: {e}")
            return 25.0  # 出错时的默认值

    def _update_details_temporarily(self, temp_center_point, constraints_met=True):
        """使用临时中心点实时更新详情面板"""
        if self.current_index < 0 or self.current_index >= len(self.results):
            return

        result = self.results[self.current_index]
        original_outer_point = result.get('outer_point')
        line1_eq = result.get('line1_eq')
        line6_angle_rad = result.get('line6_angle_rad')
        scale = result.get('scale_factor', 1.0)
        radius = self.get_standard_radius_for_result(result)
        curve2_filename = self.current_file.replace('.png', '') + '_bks.png'
        curve2_img_path = os.path.join(self.folder_c4, curve2_filename)

        if not all([original_outer_point, line1_eq, line6_angle_rad is not None, radius > 0]):
            # Cannot calculate temporary details if essential original data is missing
            return

        drag_status_text = ""
        if self.ui.dragging_semicircle and not constraints_met:
            drag_status_text = " <span style='color: red;'><b>(Invalid drag position)</b></span>"

        details = f"<h2>Plan {self.current_index + 1} (Drag preview){drag_status_text}</h2>"  # Indicate preview and validity
        details += f"<p><b>Crowe class:</b> {_crowe_label(self.current_level)}</p>"
        # Add fixed info
        details += f"<p><b>Score:</b> (Not calculated during dragging)</p>"
        details += f"<p><b>Lateral acetabular edge:</b> ({original_outer_point[0]:.1f}, {original_outer_point[1]:.1f}) (fixed)</p>"
        details += f"<p><b>Cup centre:</b> ({temp_center_point[0]:.1f}, {temp_center_point[1]:.1f}) (temporary)</p>"

        # --- Recalculate values based on temp_center_point ---
        # Coverage & Line 7 Angle
        try:
            vec_co_x = original_outer_point[0] - temp_center_point[0]
            vec_co_y = original_outer_point[1] - temp_center_point[1]
            temp_line7_angle_rad = math.atan2(vec_co_y, vec_co_x)
            temp_line7_angle_rad = adjust_negative_angle(temp_line7_angle_rad)
            temp_line7_angle_deg = math.degrees(temp_line7_angle_rad)

            # 计算角度Cup bone coverage (方法1)
            angle67_rad = (temp_line7_angle_rad - line6_angle_rad + math.pi) % (2 * math.pi) - math.pi
            angle67_deg_abs = abs(math.degrees(angle67_rad))
            coverage_angle = calculate_coverage_angle(line6_angle_rad, temp_line7_angle_rad)  # 使用导入的函数

            # 计算水平Cup bone coverage (方法2)
            active_image_width = self.current_image_width  # Use stored image width
            if active_image_width <= 0:
                print(
                    "Warning: DragHandler._update_details_temporarily using invalid image_width for horizontal coverage.")
            coverage_horizontal = calculate_coverage_horizontal(original_outer_point, temp_center_point, radius,
                                                                line6_angle_rad, active_image_width)  # 使用导入的函数

            details += f"<p><b>Cup-orientation/coverage-boundary angle:</b> {angle67_deg_abs:.1f}°</p>"
            # details += f"<p><b>Acetabular cup bone coverage:</b> {coverage_rate:.1f}%</p>"
            details += f"<p><b>Cup bone coverage (angular geometry):</b> {coverage_angle:.1f}%</p>"
            details += f"<p><b>Cup bone coverage (horizontal position):</b> {coverage_horizontal:.1f}%</p>"
            details += f"<p><b>Coverage-boundary angle (horizontal reference):</b> {temp_line7_angle_deg:.1f}° (temporary)</p>"
        except Exception as e:
            print(f"Error calculating coverage: {e}")  # 更具体的错误信息
            details += "<p><b>Acetabular cup bone coverage:</b> Calculation error</p>"
            details += "<p><b>Coverage-boundary angle (horizontal reference):</b> Calculation error</p>"

        # Abduction Angle (Line 6 vs Line 1)
        try:
            a1, b1, c1 = line1_eq
            line1_angle_rad = math.atan2(-a1, b1)
            angle_diff_rad = line6_angle_rad - line1_angle_rad
            norm_angle_diff_rad = (angle_diff_rad + math.pi) % (2 * math.pi) - math.pi
            abduction_angle_deg = abs(math.degrees(norm_angle_diff_rad))
            # Display the acute angle between unoriented lines; keep stored axis angles unchanged.
            abduction_angle_deg = min(abduction_angle_deg, 180.0 - abduction_angle_deg)
            details += f"<p><b>Radiographic cup inclination:</b> {abduction_angle_deg:.1f}° (fixed)</p>"
        except Exception:
            details += "<p><b>Radiographic cup inclination:</b> Calculation error</p>"

        details += f"<p><b>Cup-orientation axis angle (horizontal reference):</b> {result.get('line6_angle_deg', 0):.1f}° (fixed)</p>"

        # Diameter (fixed during drag)
        safe_even_diameter = result.get('safe_even_diameter')
        pixel_diameter = radius * 2.0
        actual_diameter = pixel_diameter * scale
        details += f"<p><b>Cup diameter (pixels):</b> {pixel_diameter:.2f}</p>"
        if safe_even_diameter is not None:
            details += f"<p><b>Calibrated cup diameter:</b> {actual_diameter:.2f}mm → <b>Standard cup diameter:</b> {safe_even_diameter}mm</p>"
        else:
            details += f"<p><b>Calibrated cup diameter:</b> {actual_diameter:.2f}mm (No safe standard diameter)</p>"

        # Distance to Curve 2
        try:
            min_dist_curve2 = calculate_min_distance_circle_to_curve_thread_safe(
                temp_center_point, radius, curve2_img_path, self.curve_cache, None, self.image_cache)
            if min_dist_curve2 is not None:
                dist_actual_curve2 = min_dist_curve2 * scale
                color = "red" if min_dist_curve2 < 1.0 else "black"  # Highlight invalid distance (less than 1.0)
                details += f"<p style='color:{color};'><b style='color:black;'>Minimum cup-to-superior-obturator-boundary distance:</b> {min_dist_curve2:.2f} px, {dist_actual_curve2:.2f}mm</p>"
            else:
                details += "<p><b>Minimum cup-to-superior-obturator-boundary distance:</b> Not calculated or boundary unavailable</p>"
        except Exception:
            details += "<p><b>Minimum cup-to-superior-obturator-boundary distance:</b> Calculation error</p>"

        # Distance to Curve 3 (新增)
        try:
            if self.ui.folder_c3:  # Check if C3 folder is selected
                curve3_filename = self.ui.current_file.replace('.png', '') + '_bkx.png'
                curve3_img_path = os.path.join(self.ui.folder_c3, curve3_filename)
                min_dist_curve3 = calculate_min_distance_circle_to_curve_thread_safe(
                    temp_center_point, radius, curve3_img_path, self.curve_cache, None, self.image_cache)
                if min_dist_curve3 is not None:
                    dist_actual_curve3 = min_dist_curve3 * scale
                    details += f"<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> {min_dist_curve3:.2f} px, {dist_actual_curve3:.2f}mm</p>"
                else:
                    details += "<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> Not calculated or boundary unavailable</p>"
            else:
                details += "<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> (folder not selected)</p>"
        except Exception:
            details += "<p><b>Minimum cup-to-inferior-obturator-boundary distance:</b> Calculation error</p>"

        # Distances to fixed lines (using temp_center_point)
        try:
            # Need to recalculate line equations 2, 3, 4, 8 if they weren't stored originally
            # Or just display original values? For temporary, maybe just show line 1 distance?
            if line1_eq:
                dist_line1 = calculate_distance_point_to_line(temp_center_point, line1_eq)
                details += f"<p><b>Cup centre–inter-teardrop distance:</b> {dist_line1:.2f} px ({dist_line1 * scale:.2f}mm)</p>"
            # Add other distances if easily calculable or needed for preview
            # details += f"<p><b>Cup centre–Köhler distance:</b> ... </p>"
            # details += f"<p><b>Cup centre–superior iliac line distance:</b> ... </p>"
            # details += f"<p><b>Cup centre–ischial line distance:</b> ... </p>"
            # details += f"<p><b>Cup centre–iliac–ischial midpoint line distance:</b> ... </p>"
        except Exception:
            details += "<p><b>Distance to the fixed reference line:</b> Calculation error</p>"

        self.details_label.setText(details)

    def _find_white_line_curve_intersection(self, line_eq, curve_points):
        """查找白色虚线和曲线1的交点"""
        if not line_eq or not curve_points:
            return None

        a, b, c = line_eq
        closest_point = None
        min_distance = float('inf')

        # 遍历曲线1上的所有点，找到离直线最近的点
        for point in curve_points:
            dist = abs(a * point[0] + b * point[1] + c) / math.sqrt(a ** 2 + b ** 2)
            if dist < min_distance:
                min_distance = dist
                closest_point = point

        # 如果距离小于阈值，认为是交点
        if min_distance < 2.0:  # 2 px内认为是交点
            return closest_point
        return None

    def _update_temp_line5(self, curve_point):
        """更新临时线5方程和交点，用于拖拽外沿点或线5时的可视化"""
        if not curve_point:
            return

        current_result = self.results[self.current_index]
        line1_eq = current_result.get('line1_eq')

        # 计算临时线5方程 (平行于线1，过临时外沿点)
        if line1_eq:
            a1, b1, _ = line1_eq
            temp_c5 = -a1 * curve_point[0] - b1 * curve_point[1]
            self.temp_line5_eq = (a1, b1, temp_c5)

            # 查找与曲线1的交点
            self.temp_line5_intersection = self._find_white_line_curve_intersection(self.temp_line5_eq,
                                                                                    self.curve1_points)

            # 更新临时可视化
            self._update_temporary_visualization(None)

    def _get_visibility_flags(self):
        """Helper to get current visibility flags from checkboxes."""
        flags = {key: checkbox.isChecked() for key, checkbox in self.visibility_checkboxes.items()}
        if 'line6' in flags and 'half_circle' in flags:
            combined = flags['line6'] or flags['half_circle']
            flags['line6'] = combined
            flags['half_circle'] = combined
        return flags

    def _update_visualization_with_flags(self):
        """Slot to update visualization when visibility flags change."""
        if self.current_index >= 0:
            self.update_image()  # Just re-render the image with current flags

    def _on_visibility_checkbox_changed(self, key, checked):
        try:
            if key in ('line6', 'half_circle'):
                for k in ('line6', 'half_circle'):
                    cb = self.visibility_checkboxes.get(k)
                    if cb is not None:
                        cb.blockSignals(True)
                        cb.setChecked(checked)
                        cb.blockSignals(False)
                self._sync_display_menu_with_checkboxes()
            self._update_visualization_with_flags()
        except Exception:
            pass

    def _init_menubar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        action_select_folder = QAction("Select source-radiograph folder...", self)
        action_select_folder.triggered.connect(lambda: self.select_folder('a'))
        file_menu.addAction(action_select_folder)

        action_refresh = QAction("Refresh Case List", self)
        action_refresh.triggered.connect(self.refresh_file_list)
        file_menu.addAction(action_refresh)

        self.file_menu_folder_action = QAction(f"Current source-radiograph folder: {getattr(self, 'folder_a', '')}", self)
        self.file_menu_folder_action.setEnabled(False)
        file_menu.addAction(self.file_menu_folder_action)

        level_menu = menu_bar.addMenu("Crowe Class")
        level_widget_action = QWidgetAction(self)
        self.level_combo_menu = QComboBox()
        try:
            self.level_combo_menu.addItems([f"Crowe {c}" for c in ("I", "II", "III", "IV")])
        except Exception:
            for c in ("I", "II", "III", "IV"):
                self.level_combo_menu.addItem(f"Crowe {c}")
        self.level_combo_menu.currentIndexChanged.connect(self._on_level_menu_changed)
        level_widget_action.setDefaultWidget(self.level_combo_menu)
        level_menu.addAction(level_widget_action)

        ops_menu = menu_bar.addMenu("Planning")
        self.action_generate = QAction("Generate Preoperative Plans", self)
        self.action_generate.triggered.connect(self.process_file)
        self.action_generate.setEnabled(False)
        ops_menu.addAction(self.action_generate)

        self.action_save = QAction("Save Current Plan", self)
        self.action_save.triggered.connect(self.save_current_plan)
        self.action_save.setEnabled(False)
        ops_menu.addAction(self.action_save)

        self.action_revert = QAction("Restore Initial Plan", self)
        self.action_revert.triggered.connect(self.revert_to_initial_generation)
        self.action_revert.setEnabled(False)
        ops_menu.addAction(self.action_revert)

        self.action_batch = QAction("Batch Process", self)
        self.action_batch.triggered.connect(self.batch_process_all_files)
        ops_menu.addAction(self.action_batch)

        display_menu = menu_bar.addMenu("Display")
        self.display_actions = {}
        cup_act = QAction("Acetabular Cup", self)
        cup_checked = False
        try:
            cb6 = self.visibility_checkboxes.get('line6')
            cbhc = self.visibility_checkboxes.get('half_circle')
            cup_checked = (cb6.isChecked() if cb6 else False) or (cbhc.isChecked() if cbhc else False)
        except Exception:
            pass
        cup_act.setCheckable(True)
        cup_act.setChecked(cup_checked)
        cup_act.triggered.connect(lambda checked: self._on_display_action_toggled('cup', checked))
        display_menu.addAction(cup_act)
        self.display_actions['cup'] = cup_act

        for key, checkbox in self.visibility_checkboxes.items():
            if key in ('line6', 'half_circle'):
                continue
            act = QAction(checkbox.text(), self)
            act.setCheckable(True)
            act.setChecked(checkbox.isChecked())
            def make_slot(k):
                return lambda checked: self._on_display_action_toggled(k, checked)
            act.triggered.connect(make_slot(key))
            display_menu.addAction(act)
            self.display_actions[key] = act

    def _on_display_action_toggled(self, key, checked):
        try:
            if key == 'cup':
                for k in ('line6', 'half_circle'):
                    cb = self.visibility_checkboxes.get(k)
                    if cb is not None:
                        cb.blockSignals(True)
                        cb.setChecked(checked)
                        cb.blockSignals(False)
            else:
                cb = self.visibility_checkboxes.get(key)
                if cb is not None:
                    cb.blockSignals(True)
                    cb.setChecked(checked)
                    cb.blockSignals(False)
            self._update_visualization_with_flags()
        except Exception:
            pass

    def _sync_display_menu_with_checkboxes(self):
        try:
            for key, cb in self.visibility_checkboxes.items():
                act = self.display_actions.get(key)
                if act is not None:
                    act.blockSignals(True)
                    act.setChecked(cb.isChecked())
                    act.blockSignals(False)
            cup_act = self.display_actions.get('cup')
            if cup_act is not None:
                cb6 = self.visibility_checkboxes.get('line6')
                cbhc = self.visibility_checkboxes.get('half_circle')
                v = (cb6.isChecked() if cb6 else False) or (cbhc.isChecked() if cbhc else False)
                cup_act.blockSignals(True)
                cup_act.setChecked(v)
                cup_act.blockSignals(False)
        except Exception:
            pass

    def eventFilter(self, source, event):
        """Handle events for the image label (mouse interaction)."""
        # --- Drag Handling ---
        # Check if the event source is the scroll area's viewport
        if source == self.scroll_area.viewport():
            if event.type() in [QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.MouseButtonRelease]:
                # Delegate drag events to the DragHandler
                # Pass self.image_label as the intended target for DragHandler logic
                if self.drag_handler.handle_event(self.image_label, event):
                    return True  # Event handled by DragHandler

        # --- Zoom Handling (Still check for viewport as source) ---
        if source == self.scroll_area.viewport() and event.type() == QEvent.Wheel:
            try:
                if event.angleDelta().y() > 0:
                    self.zoom_factor = float(getattr(self, "zoom_factor", 1.0)) * 1.2
                else:
                    self.zoom_factor = float(getattr(self, "zoom_factor", 1.0)) / 1.2
                self.zoom_factor = max(ZOOM_MIN, min(self.zoom_factor, ZOOM_MAX))
                self._apply_zoom()
            except Exception:
                pass
            return True

        # --- Default processing for other events ---
        return super().eventFilter(source, event)

    def revert_to_initial_generation(self):
        """恢复到最近一次点击"Generate Preoperative Plans"后的状态"""
        if not self.initial_generation_results:
            self.statusBar().showMessage("No initial generated state is available to restore")
            return

        print("正在回退到初始生成状态...")
        try:
            self.results = copy.deepcopy(self.initial_generation_results)
            self.image_cache = {}  # Clear cache

            if self.results:
                self.current_index = 0
            else:
                self.current_index = -1

            self.update_plan_list()  # Refresh list

            if self.current_index >= 0:
                self.plan_list.setCurrentRow(self.current_index)
                self.update_ui()  # Refresh image and details
            else:
                # Clear UI if no results after revert (shouldn't happen if initial had results)
                self.plan_list.clear()
                self.image_label.clear()
                self.details_label.clear()
                self.image_label.setText("Select a case and Crowe class")

            self.revert_btn.setEnabled(False)  # Disable revert button after reverting
            self.statusBar().showMessage("The initial generated state has been restored")
        except Exception as e:
            self.statusBar().showMessage(f"Error while restoring: {str(e)}")
            print(f"Error during revert: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Restore error", f"Error while restoring the initial generated state: {str(e)}")
            # Attempt to keep UI consistent even on error
            self.results = []
            self.current_index = -1
            self.plan_list.clear()
            self.image_label.clear()
            self.details_label.clear()
            self.image_label.setText("Restore failed. Please generate the plans again.")
            self.revert_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            # 已移除保存所有方案按钮

    def select_plan_by_results_index(self, target_results_index):
        """Selects the plan in the QListWidget that corresponds to the given index in self.results.
           This method accounts for non-selectable header items in the QListWidget.
        """
        if not (0 <= target_results_index < len(self.results)):
            print(
                f"select_plan_by_results_index: target_results_index {target_results_index} is out of bounds for self.results (len {len(self.results)})")
            self.plan_list.clearSelection()
            # self.current_index = -1 # current_index should already be set or be -1 if no results
            # self.update_ui() # Avoid calling update_ui if selection is invalid, let caller handle
            return

        # self.current_index = target_results_index # The caller should have set self.current_index already

        selectable_item_counter = 0
        target_list_widget_row = -1

        for i in range(self.plan_list.count()):
            item = self.plan_list.item(i)
            if item.flags() & Qt.ItemIsSelectable:  # Check if the item is selectable
                if selectable_item_counter == target_results_index:
                    target_list_widget_row = i
                    break
                selectable_item_counter += 1

        if target_list_widget_row != -1:
            self.plan_list.setCurrentRow(
                target_list_widget_row)  # This should also trigger on_plan_selected if selection changes
            print(
                f"select_plan_by_results_index: Set QListWidget row {target_list_widget_row} for results index {target_results_index}")
            # If on_plan_selected doesn't trigger update_ui reliably on programmatic selection, call it directly.
            # However, setCurrentRow should ideally trigger the itemSelectionChanged signal.
            # Let's assume for now current_index has been set correctly by the caller, and on_plan_selected will handle UI update.
            # If direct update is needed: self.update_ui_for_current_selection()
        else:
            print(
                f"select_plan_by_results_index: Could not find QListWidget item for results index {target_results_index}. Selectable items found: {selectable_item_counter}")
            self.plan_list.clearSelection()
            # self.update_ui() # Avoid update if no valid item found

    def update_plan_list(self):
        """更新Ranked Plans"""
        self.plan_list.clear()
        print(f"DEBUG: update_plan_list called with {len(self.results)} results initially.")  # DEBUG

        # === 分离Angular-geometry和Horizontal-position plans ===
        angle_plans = [r for r in self.results if r.get('coverage_method') == 'angle']
        horizontal_plans = [r for r in self.results if r.get('coverage_method') == 'horizontal']

        print(f"DEBUG: 分离后: Angular-geometry {len(angle_plans)} 个, Horizontal-position {len(horizontal_plans)} 个")  # DEBUG

        # === 处理Angular-geometry plans ===
        # 分离备选方案和常规方案
        angle_special_fallback_plan = None
        angle_regular_plans_temp = []
        for result in angle_plans:
            if result.get('is_special_fallback', False):
                angle_special_fallback_plan = result
                print("DEBUG: Found angle special fallback plan.")  # DEBUG
            else:
                angle_regular_plans_temp.append(result)

        # 按照类型分类常规方案
        angle_valid_plans = []
        angle_invalid_plans = []
        for result in angle_regular_plans_temp:
            if result.get('is_valid', False):
                angle_valid_plans.append(result)
            else:
                angle_invalid_plans.append(result)

        # 对各组常规方案按评分排序
        angle_valid_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        angle_invalid_plans.sort(key=lambda x: x.get('final_score', 0), reverse=True)

        # 将有效方案和无效方案组合
        all_angle_regular_plans = angle_valid_plans + angle_invalid_plans

        # --- 添加评分过滤逻辑 (仅对常规方案) ---
        filtered_angle_regular_plans = []
        remaining_slots = 5  # 最多显示5个常规方案

        if all_angle_regular_plans:
            # 添加第一个常规方案
            filtered_angle_regular_plans.append(all_angle_regular_plans[0])
            remaining_slots -= 1

            # 继续添加差异足够大的其他常规方案
            for i in range(1, len(all_angle_regular_plans)):
                if remaining_slots <= 0:
                    break

                current_score = all_angle_regular_plans[i].get('final_score', 0)
                # 与最后添加的常规方案比较
                last_added_score = filtered_angle_regular_plans[-1].get('final_score', 0)

                # 只有评分差异较大才添加
                if last_added_score - current_score >= 0.01:
                    filtered_angle_regular_plans.append(all_angle_regular_plans[i])
                    remaining_slots -= 1
                else:
                    print(f"Angular-geometry常规方案 {i + 1} (Score: {current_score:.4f}) 因与前一方案评分过近 (<0.01) 而被过滤")

        # --- 组合最终显示的Angular-geometry plans列表 ---
        final_angle_results = filtered_angle_regular_plans  # 先放过滤后的常规方案
        if angle_special_fallback_plan:
            final_angle_results.append(angle_special_fallback_plan)  # 最后添加备选方案

        # === 处理Horizontal-position plans ===
        # 分离备选方案和常规方案
        horizontal_special_fallback_plan = None
        horizontal_regular_plans_temp = []
        for result in horizontal_plans:
            if result.get('is_special_fallback', False):
                horizontal_special_fallback_plan = result
                print("DEBUG: Found horizontal special fallback plan.")  # DEBUG
            else:
                horizontal_regular_plans_temp.append(result)

        # === 修改：直接对所有Horizontal-position常规方案进行多级排序 ===
        horizontal_regular_plans_temp.sort(
            key=lambda x: (x.get('is_valid', False), x.get('coverage_rate_horizontal', 0), x.get('final_score', 0)),
            reverse=True  # is_valid=True优先, coverage高优先, score高优先
        )
        print("DEBUG: Sorted horizontal regular plans by (is_valid, coverage_horizontal, score).")

        # --- 添加评分过滤逻辑 (应用于排序后的列表) ---
        filtered_horizontal_regular_plans = []
        remaining_slots = 5  # 最多显示5个常规方案

        if horizontal_regular_plans_temp:
            # 添加第一个方案 (排序后的最佳方案)
            filtered_horizontal_regular_plans.append(horizontal_regular_plans_temp[0])
            remaining_slots -= 1

            # 继续添加差异足够大的其他常规方案
            for i in range(1, len(horizontal_regular_plans_temp)):
                if remaining_slots <= 0:
                    break

                current_plan = horizontal_regular_plans_temp[i]
                last_added_plan = filtered_horizontal_regular_plans[-1]

                # 比较评分 (仍然基于原始评分进行过滤)
                current_score = current_plan.get('final_score', 0)
                last_added_score = last_added_plan.get('final_score', 0)

                # 只有评分差异较大才添加
                if last_added_score - current_score >= 0.01:
                    filtered_horizontal_regular_plans.append(current_plan)
                    remaining_slots -= 1
                else:
                    print(
                        f"Horizontal-position常规方案 (Index {i}, Score: {current_score:.4f}) 因与前一方案评分过近 (<0.01) 而被过滤")

        # --- 组合最终显示的Horizontal-position plans列表 ---
        final_horizontal_results = filtered_horizontal_regular_plans  # 先放过滤后的常规方案
        if horizontal_special_fallback_plan:
            final_horizontal_results.append(horizontal_special_fallback_plan)  # 最后添加备选方案

        # === 合并两种方法的最终结果 ===
        final_results_to_display = final_angle_results + final_horizontal_results

        # 如果最终列表为空，可能是过滤后没有常规方案且没有备选方案
        if not final_results_to_display:
            print("警告：No plans are available for display")
            # 可以Select显示一条消息，或者不显示任何内容
            # 这里不尝试重新计算，避免无限循环
            self.results = []  # 清空结果
            return

        # --- 更新最终结果变量 ---
        self.results = final_results_to_display  # 更新 self.results 以匹配列表显示
        print(f"DEBUG: self.results updated. Count: {len(self.results)}")  # DEBUG

        # === 显示Ranked Plans ===
        print("DEBUG: Starting to add items to plan_list...")  # DEBUG

        # 添加Angular-geometry plans
        if final_angle_results:
            angle_header_item = QListWidgetItem("=== Angular-geometry Pathway ===")
            angle_header_item.setFlags(angle_header_item.flags() & ~Qt.ItemIsSelectable)
            angle_header_item.setBackground(QColor(220, 220, 255))  # 浅蓝色背景
            self.plan_list.addItem(angle_header_item)

            for i, result in enumerate(final_angle_results):
                self._add_plan_to_list(i, result, "Angular-geometry")

        # 添加Horizontal-position plans
        if final_horizontal_results:
            horizontal_header_item = QListWidgetItem("=== Horizontal-position Pathway ===")
            horizontal_header_item.setFlags(horizontal_header_item.flags() & ~Qt.ItemIsSelectable)
            horizontal_header_item.setBackground(QColor(220, 255, 220))  # 浅绿色背景
            self.plan_list.addItem(horizontal_header_item)

            for i, result in enumerate(final_horizontal_results):
                self._add_plan_to_list(i, result, "Horizontal-position")

        print("DEBUG: Finished adding items to plan_list.")  # DEBUG

    def _add_plan_to_list(self, index, result, method_prefix):
        """添加方案到列表的辅助方法"""
        is_valid = result.get('is_valid', False)
        is_special_fallback = result.get('is_special_fallback', False)
        score = result.get('final_score', 0)

        # 创建列表项
        if is_special_fallback:
            status_text = "[Special fallback]"
            item_prefix = f"{method_prefix} fallback plan"
        elif is_valid:
            status_text = "[Valid]"
            item_prefix = f"{method_prefix} plan {index + 1}"
        else:
            status_text = "[Outside constraints]"
            item_prefix = f"{method_prefix} plan {index + 1}"

        item_text = f"{item_prefix} {status_text}"
        item_text += f"\nScore: {score:.4f}"

        # 添加标准直径信息
        if 'safe_even_diameter' in result and result['safe_even_diameter']:
            item_text += f"\nStandard cup diameter: {result['safe_even_diameter']}"

        # 添加特殊备选方案的Cup bone coverage和备注信息
        if is_special_fallback:
            # 使用适当的Cup bone coverage值
            if method_prefix == "Angular-geometry":
                coverage_rate = result.get('coverage_rate_angle')
            else:
                coverage_rate = result.get('coverage_rate_horizontal')

            if coverage_rate is not None:
                item_text += f"\nAcetabular cup bone coverage: {coverage_rate:.1f}%"

            if result.get('need_cover', False):  # 直接从结果获取是否需要盖子
                item_text += "\nNote: Augmentation is required"

        item = QListWidgetItem(item_text)
        self.plan_list.addItem(item)

        if method_prefix == "Horizontal-position":  # 只针对Horizontal-position plans进行详细打印
            print(f"DEBUG: Horizontal-position plans {index + 1} 详情:")
            print(f"  - coverage_rate_horizontal: {result.get('coverage_rate_horizontal')}")
            print(f"  - circle_to_curve2_distance: {result.get('circle_to_curve2_distance')}")
            print(f"  - is_valid in dict: {result.get('is_valid')}")  # 直接看字典里的 is_valid

            # 可以再用 _check_plan_validity 校验一次，看看结果是否一致
            rechecked_valid = self._check_plan_validity(result)
            print(f"  - rechecked_is_valid by _check_plan_validity: {rechecked_valid}")

    def check_gpu_support(self):
        """检测GPU支持情况"""
        try:
            # 优先使用PyTorch检测CUDA支持
            import torch
            if torch.cuda.is_available():
                cuda_devices = torch.cuda.device_count()
                # 获取GPU信息
                try:
                    import subprocess
                    result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        gpu_info = result.stdout.strip().split('\n')[0]
                        gpu_name, gpu_memory = gpu_info.split(', ')
                        return True, f"CUDA device detected: {gpu_name} ({gpu_memory} MB)"
                    else:
                        return True, f"{cuda_devices} CUDA device(s) detected"
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    return True, f"{cuda_devices} CUDA device(s) detected"
            else:
                # 备用方案：使用OpenCV检测
                try:
                    import cv2
                    cuda_devices = cv2.cuda.getCudaEnabledDeviceCount()
                    if cuda_devices > 0:
                        return True, f"{cuda_devices} CUDA device(s) detected (OpenCV)"
                    else:
                        return False, "No CUDA device detected"
                except ImportError:
                    return False, "Neither PyTorch nor OpenCV detected CUDA support"
        except ImportError:
            return False, "PyTorch is not installed"
        except Exception as e:
            return False, f"GPU detection failed: {str(e)}"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PlanVisualizationUI()
    window.show()
    sys.exit(app.exec_())
