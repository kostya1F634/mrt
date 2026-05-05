import sys
import math
import platform
import logging
import statistics
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QSizePolicy)
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QDialog, QCheckBox, QDialogButtonBox
from PyQt6.QtWidgets import QGroupBox, QGridLayout, QProgressBar, QAbstractButton
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QCursor

# ==========================================
# НАСТРОЙКА ЛОГИРОВАНИЯ В ТЕРМИНАЛ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

RAZER_GREEN = "#44d62c"
BG_COLOR = "#1a1a1a"
MIN_FILTER_SPAN_X = 20.0
MAX_FILTER_ABS_ANGLE = 35.0
MAX_FILTER_RMSE_RATIO = 0.08
FILTER_WINDOW_POINTS = 16

# ==========================================
# МАТЕМАТИКА
# ==========================================
def calculate_regression(path):
    if len(path) < 2:
        return 0.0, 0.0, 0.0

    mean_x = sum(p[0] for p in path) / len(path)
    mean_y = sum(p[1] for p in path) / len(path)

    sxx = sum((p[0] - mean_x) ** 2 for p in path)
    syy = sum((p[1] - mean_y) ** 2 for p in path)
    sxy = sum((p[0] - mean_x) * (p[1] - mean_y) for p in path)

    if sxx == 0 and syy == 0:
        return 0.0, 0.0, mean_y

    # Главная ось облака точек: минимизирует перпендикулярное расстояние до линии.
    angle_degrees = 0.5 * math.degrees(math.atan2(2 * sxy, sxx - syy))
    if angle_degrees > 90:
        angle_degrees -= 180
    elif angle_degrees < -90:
        angle_degrees += 180

    angle_radians = math.radians(angle_degrees)
    if abs(math.cos(angle_radians)) < 1e-12:
        return angle_degrees, float("inf"), mean_x

    m = math.tan(angle_radians)
    b = mean_y - m * mean_x
    
    return angle_degrees, m, b


def calculate_path_quality(path):
    if len(path) < 2:
        return {
            "accepted": False,
            "reason": "Слишком мало точек для расчета.",
            "angle": 0.0,
            "m": 0.0,
            "b": 0.0,
            "rmse_ratio": 1.0,
        }

    angle, m, b = calculate_regression(path)
    min_x = min(p[0] for p in path)
    max_x = max(p[0] for p in path)
    min_y = min(p[1] for p in path)
    max_y = max(p[1] for p in path)
    span_x = max_x - min_x
    span_y = max_y - min_y
    span = max(math.hypot(span_x, span_y), 1.0)

    if math.isinf(m):
        residuals = [abs(p[0] - b) for p in path]
    else:
        residual_scale = math.sqrt(m * m + 1)
        residuals = [abs(m * p[0] - p[1] + b) / residual_scale for p in path]

    rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    rmse_ratio = rmse / span

    accepted = True
    reason = "Траектория принята."
    if span_x < MIN_FILTER_SPAN_X:
        accepted = False
        reason = "Недостаточно горизонтального движения."
    elif abs(angle) > MAX_FILTER_ABS_ANGLE:
        accepted = False
        reason = "Траектория слишком вертикальная."
    elif rmse_ratio > MAX_FILTER_RMSE_RATIO:
        accepted = False
        reason = "Траектория слишком дугообразная или неровная."

    return {
        "accepted": accepted,
        "reason": reason,
        "angle": angle,
        "m": m,
        "b": b,
        "rmse_ratio": rmse_ratio,
    }


def normalize_motion_angle(dx, dy):
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180
    return angle


def should_accept_motion_delta(path, dx, dy):
    if dx == 0 and dy == 0:
        return False

    if abs(normalize_motion_angle(dx, dy)) > MAX_FILTER_ABS_ANGLE:
        return False

    if len(path) < 3:
        return True

    last_x, last_y = path[-1]
    candidate = (last_x + dx, last_y + dy)
    window = (path + [candidate])[-FILTER_WINDOW_POINTS:]
    quality = calculate_path_quality(window)
    return quality["accepted"] or quality["reason"] == "Недостаточно горизонтального движения."


def apply_motion_delta(path, dx, dy, filter_enabled):
    if not path:
        path = [(0, 0)]

    if dx == 0 and dy == 0:
        return path, False

    if filter_enabled and not should_accept_motion_delta(path, dx, dy):
        return path, False

    last_x, last_y = path[-1]
    return path + [(last_x + dx, last_y + dy)], True


def calculate_path_length(path):
    return sum(
        math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
        for i in range(1, len(path))
    )


def quality_score_from_meta(meta, path):
    length = calculate_path_length(path)
    if length < 50:
        return 25, "Коротко"

    rmse_penalty = min(meta.get("rmse_ratio", 1.0) / MAX_FILTER_RMSE_RATIO, 2.0) * 35
    rejected_penalty = min(meta.get("rejected_ratio", 0.0), 0.5) * 80
    score = max(0, min(100, round(100 - rmse_penalty - rejected_penalty)))

    if score >= 85:
        label = "Отлично"
    elif score >= 65:
        label = "Хорошо"
    elif score >= 45:
        label = "Шумно"
    else:
        label = "Повторить"

    return score, label


def summarize_series(samples):
    if not samples:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "spread": 0.0,
            "stability": 0,
        }

    angles = [sample["angle"] for sample in samples]
    spread = statistics.pstdev(angles) if len(angles) > 1 else 0.0
    stability = max(0, min(100, round(100 - spread * 20)))
    return {
        "count": len(samples),
        "mean": statistics.fmean(angles),
        "median": statistics.median(angles),
        "spread": spread,
        "stability": stability,
    }

# ==========================================
# ПОТОК ЧТЕНИЯ МЫШИ (Фоновый)
# ==========================================
class MouseListenerThread(QThread):
    statusSignal = pyqtSignal(str, str)
    recordingStartSignal = pyqtSignal()
    recordingStopSignal = pyqtSignal(float, float, float, list, dict)
    leftClickSignal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.os_type = platform.system()
        self.recording = False
        self.filter_enabled = False
        self.path =[]
        self.cur_x = 0.0
        self.cur_y = 0.0
        self.frame_dx = 0.0
        self.frame_dy = 0.0
        self.accepted_delta_count = 0
        self.rejected_delta_count = 0
        logging.info(f"Инициализация слушателя мыши для ОС: {self.os_type}")

    def run(self):
        if self.os_type == "Linux":
            self._run_linux()
        elif self.os_type == "Windows":
            self._run_windows()
        else:
            msg = f"ОС {self.os_type} не поддерживается"
            logging.error(msg)
            self.statusSignal.emit(msg, "#ff0000")

    def _run_linux(self):
        logging.info("Запуск модуля для Linux (evdev)")
        try:
            import evdev
        except ImportError:
            logging.error("Библиотека evdev не установлена.")
            self.statusSignal.emit("Установите evdev: pip install evdev", "#ff0000")
            return

        mouse = None
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                caps = device.capabilities()
                if evdev.ecodes.EV_REL in caps and evdev.ecodes.EV_KEY in caps:
                    if evdev.ecodes.REL_X in caps[evdev.ecodes.EV_REL] and evdev.ecodes.BTN_LEFT in caps[evdev.ecodes.EV_KEY]:
                        mouse = device
                        logging.info(f"Найдено подходящее устройство: {device.name} ({path})")
                        break
            except PermissionError:
                pass

        if not mouse:
            logging.error("Не удалось подключиться к мыши из-за нехватки прав или отсутствия устройства.")
            self.statusSignal.emit("Нет прав!\nСделайте: sudo usermod -aG input $USER\nИ перезайдите в систему.", "#ff0000")
            return

        logging.info(f"Успешно подключено к мыши: {mouse.name}")
        self.statusSignal.emit(f"Подключено: {mouse.name}\nЖмите ЛКМ для начала.", "#aaaaaa")

        try:
            for event in mouse.read_loop():
                if event.type == evdev.ecodes.EV_KEY:
                    if event.code == evdev.ecodes.BTN_LEFT and event.value == 1:
                        self.leftClickSignal.emit()
                    elif event.code == evdev.ecodes.BTN_RIGHT and event.value == 1:
                        self.stop_recording()

                elif event.type == evdev.ecodes.EV_REL and self.recording:
                    if event.code == evdev.ecodes.REL_X:
                        self.frame_dx += event.value
                    elif event.code == evdev.ecodes.REL_Y:
                        self.frame_dy -= event.value
                        
                elif event.type == evdev.ecodes.EV_SYN and self.recording:
                    self.add_motion_delta(self.frame_dx, self.frame_dy)
                    self.frame_dx = 0.0
                    self.frame_dy = 0.0
        except Exception as e:
            logging.error(f"Ошибка при чтении устройства: {e}")

    def _run_windows(self):
        logging.info("Запуск модуля для Windows (pynput)")
        try:
            from pynput import mouse
        except ImportError:
            logging.error("Библиотека pynput не установлена.")
            self.statusSignal.emit("Установите pynput: pip install pynput", "#ff0000")
            return

        self.statusSignal.emit("Готово. Жмите ЛКМ для старта.", "#aaaaaa")
        self.last_abs_x = None
        self.last_abs_y = None

        def on_click(x, y, button, pressed):
            if button == mouse.Button.left and pressed:
                self.last_abs_x, self.last_abs_y = x, y
                self.leftClickSignal.emit()
            elif button == mouse.Button.right and pressed:
                self.stop_recording()

        def on_move(x, y):
            if self.recording:
                if self.last_abs_x is not None and self.last_abs_y is not None:
                    dx = x - self.last_abs_x
                    dy = y - self.last_abs_y
                    if dx != 0 or dy != 0:
                        self.add_motion_delta(dx, -dy)
                self.last_abs_x, self.last_abs_y = x, y

        logging.info("Слушатель Windows запущен.")
        with mouse.Listener(on_move=on_move, on_click=on_click) as listener:
            listener.join()

    def start_recording(self):
        self.recording = True
        self.path =[(0, 0)]
        self.cur_x = 0
        self.cur_y = 0
        self.frame_dx = 0
        self.frame_dy = 0
        self.accepted_delta_count = 0
        self.rejected_delta_count = 0
        logging.info("Начата запись движения мыши...")
        self.recordingStartSignal.emit()

    def add_motion_delta(self, dx, dy):
        if dx == 0 and dy == 0:
            return

        self.path, accepted = apply_motion_delta(self.path, dx, dy, self.filter_enabled)
        if accepted:
            self.cur_x, self.cur_y = self.path[-1]
            self.accepted_delta_count += 1
        else:
            self.rejected_delta_count += 1

    def stop_recording(self):
        if self.recording:
            self.recording = False
            logging.info(f"Запись остановлена. Собрано точек: {len(self.path)}")
            measured_angle, m, b = calculate_regression(self.path)
            total_delta_count = self.accepted_delta_count + self.rejected_delta_count
            rejected_ratio = self.rejected_delta_count / total_delta_count if total_delta_count else 0.0
            quality = calculate_path_quality(self.path)
            sample_meta = {
                "accepted_delta_count": self.accepted_delta_count,
                "rejected_delta_count": self.rejected_delta_count,
                "rejected_ratio": rejected_ratio,
                "rmse_ratio": quality["rmse_ratio"],
            }
            logging.info(f"Результаты расчетов: Отклонение={measured_angle:.3f}°, m={m:.5f}, b={b:.2f}")
            self.recordingStopSignal.emit(measured_angle, m, b, self.path, sample_meta)


# ==========================================
# ВИДЖЕТ ОТРИСОВКИ (Холст)
# ==========================================
class PlotWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 200)
        
        # Явно разрешаем виджету растягиваться по обеим осям до бесконечности
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.path =[]
        self.m = 0
        self.b = 0
        self.is_recording = False

    def update_result(self, path, m, b):
        self.path = path
        self.m = m
        self.b = b
        self.is_recording = False
        self.update()

    def set_recording(self):
        self.is_recording = True
        self.path =[]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Фон холста
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        # Отрисовка центральных осей
        cx, cy = self.width() / 2, self.height() / 2
        pen_grid = QPen(QColor("#333333"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        painter.drawLine(0, int(cy), self.width(), int(cy))
        painter.drawLine(int(cx), 0, int(cx), self.height())

        if not self.path or self.is_recording:
            return

        # Ищем масштаб
        min_x = min(p[0] for p in self.path)
        max_x = max(p[0] for p in self.path)
        min_y = min(p[1] for p in self.path)
        max_y = max(p[1] for p in self.path)

        w_range = max(abs(max_x - min_x), 1)
        h_range = max(abs(max_y - min_y), 1)
        
        scale = min((self.width() * 0.8) / w_range, (self.height() * 0.8) / h_range)
        offset_x = (max_x + min_x) / 2
        offset_y = (max_y + min_y) / 2

        def screen_coords(x, y):
            sx = cx + (x - offset_x) * scale
            sy = cy - (y - offset_y) * scale 
            return QPointF(sx, sy)

        # Отрисовка траектории
        pen_path = QPen(QColor("white"), 2)
        painter.setPen(pen_path)
        for i in range(1, len(self.path)):
            p1 = screen_coords(*self.path[i-1])
            p2 = screen_coords(*self.path[i])
            painter.drawLine(p1, p2)

        # Отрисовка идеальной линии тренда
        if math.isinf(self.m):
            p1 = screen_coords(self.b, min_y)
            p2 = screen_coords(self.b, max_y)
        else:
            line_y1 = self.m * min_x + self.b
            line_y2 = self.m * max_x + self.b
            p1 = screen_coords(min_x, line_y1)
            p2 = screen_coords(max_x, line_y2)
        
        pen_line = QPen(QColor(RAZER_GREEN), 3)
        painter.setPen(pen_line)
        painter.drawLine(p1, p2)

# ==========================================
# ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ
# ==========================================
class SettingsDialog(QDialog):
    def __init__(self, filter_enabled, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.setStyleSheet(f"background-color: {BG_COLOR}; color: white;")

        layout = QVBoxLayout(self)
        self.filter_checkbox = QCheckBox("Фильтровать неровные участки")
        self.filter_checkbox.setChecked(filter_enabled)
        self.filter_checkbox.setStyleSheet(f"QCheckBox::indicator:checked {{ background-color: {RAZER_GREEN}; }}")
        layout.addWidget(self.filter_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def is_filter_enabled(self):
        return self.filter_checkbox.isChecked()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mouse Rotation Calibrator")
        self.setMinimumSize(980, 620)
        self.resize(1100, 720)         
        self.filter_enabled = False
        self.samples = []
        self.last_sample = None
        self.series_collapsed = False
        
        self.setStyleSheet(f"background-color: {BG_COLOR}; color: white;")
        logging.info("GUI инициализировано.")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # УДАЛЕНА СТРОКА: layout.setAlignment(Qt.AlignmentFlag.AlignCenter) 
        # Теперь макет будет занимать всю ширину, а тексты центрируем самими виджетами QLabel.

        # Заголовок
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("КАЛИБРОВКА СЕНСОРА")
        self.lbl_title.setFont(QFont("Arial", 22, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(f"color: {RAZER_GREEN};")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.lbl_title, stretch=1)

        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setFixedSize(42, 42)
        self.btn_settings.setToolTip("Настройки")
        self.btn_settings.setStyleSheet(
            f"QPushButton {{ color: {RAZER_GREEN}; border: 1px solid #333333; font-size: 22px; }}"
            f"QPushButton:hover {{ border-color: {RAZER_GREEN}; }}"
        )
        self.btn_settings.clicked.connect(self.open_settings)
        header_layout.addWidget(self.btn_settings)
        layout.addLayout(header_layout)

        self.lbl_instr = QLabel("ЛКМ — Начать | ПКМ — Завершить | F11 — Во весь экран")
        self.lbl_instr.setFont(QFont("Arial", 12))
        self.lbl_instr.setStyleSheet("color: gray;")
        self.lbl_instr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_instr)

        center_group = QGroupBox("Текущий замер")
        center_group.setStyleSheet("QGroupBox { border: 1px solid #333333; margin-top: 12px; padding: 8px; }")
        center_layout = QVBoxLayout(center_group)

        # Холст для рисования
        self.canvas = PlotWidget()
        center_layout.addWidget(self.canvas, stretch=1)

        # Значение угла
        self.lbl_angle_title = QLabel("УГОЛ ОТКЛОНЕНИЯ")
        self.lbl_angle_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.lbl_angle_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.lbl_angle_title)

        self.lbl_angle_val = QLabel("0.00°")
        self.lbl_angle_val.setFont(QFont("Arial", 40, QFont.Weight.Bold))
        self.lbl_angle_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.lbl_angle_val)

        quality_layout = QGridLayout()
        self.quality_bar = QProgressBar()
        self.quality_bar.setRange(0, 100)
        self.quality_bar.setValue(0)
        self.quality_bar.setTextVisible(False)
        self.quality_bar.setStyleSheet(
            f"QProgressBar {{ border: 1px solid #333333; background: #111111; height: 10px; }}"
            f"QProgressBar::chunk {{ background-color: {RAZER_GREEN}; }}"
        )
        self.lbl_quality = QLabel("Качество: нет замера")
        self.lbl_quality.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quality_layout.addWidget(self.quality_bar, 0, 0)
        quality_layout.addWidget(self.lbl_quality, 0, 1)
        center_layout.addLayout(quality_layout)
        layout.addWidget(center_group, stretch=1)

        self.series_group = QGroupBox()
        self.series_group.setStyleSheet("QGroupBox { border: 1px solid #333333; margin-top: 12px; padding: 8px; }")
        series_outer_layout = QVBoxLayout(self.series_group)
        series_header_layout = QHBoxLayout()
        series_title = QLabel("Серия замеров")
        series_title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.btn_toggle_series = QPushButton("Свернуть")
        self.btn_toggle_series.setFixedWidth(100)
        self.btn_toggle_series.clicked.connect(self.toggle_series_panel)
        series_header_layout.addWidget(series_title)
        series_header_layout.addStretch(1)
        series_header_layout.addWidget(self.btn_toggle_series)
        series_outer_layout.addLayout(series_header_layout)

        self.series_body = QWidget()
        series_body_layout = QHBoxLayout(self.series_body)
        series_metrics_layout = QGridLayout()
        self.lbl_series_count = QLabel("0")
        self.lbl_series_mean = QLabel("—")
        self.lbl_series_median = QLabel("—")
        self.lbl_series_spread = QLabel("—")
        self.lbl_series_stability = QLabel("—")
        self.lbl_recent_samples = QLabel("Добавьте минимум 3 замера.")
        self.lbl_recent_samples.setStyleSheet("color: gray;")
        self.lbl_recent_samples.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.lbl_series_count.setToolTip("Сколько замеров уже добавлено в серию. Чем больше замеров, тем надежнее итог.")
        self.lbl_series_mean.setToolTip(
            "Средний угол по всем замерам. Удобен для общей оценки, но чувствителен к случайным плохим замерам."
        )
        self.lbl_series_median.setToolTip(
            "Медианный угол. Обычно надежнее среднего, если один из замеров получился случайно дерганым."
        )
        self.lbl_series_spread.setToolTip(
            "Разброс углов в серии. Маленькое значение значит стабильные повторяемые движения; большое — техника нестабильна."
        )
        self.lbl_series_stability.setToolTip(
            "Оценка повторяемости серии. Ближе к 100% — замеры похожи друг на друга; низкое значение — серию лучше повторить."
        )
        self.lbl_recent_samples.setToolTip("Последние замеры серии: номер, угол и качество одиночного замера.")
        self.btn_add_sample = QPushButton("Добавить в серию")
        self.btn_add_sample.setEnabled(False)
        self.btn_add_sample.clicked.connect(self.add_last_sample_to_series)
        self.btn_add_sample.setStyleSheet(f"color: {RAZER_GREEN}; border: 1px solid #333333; padding: 6px;")
        metric_count = QLabel("Замеров")
        metric_mean = QLabel("Среднее")
        metric_median = QLabel("Медиана")
        metric_spread = QLabel("Разброс")
        metric_stability = QLabel("Стабильность")
        metric_count.setToolTip(self.lbl_series_count.toolTip())
        metric_mean.setToolTip(self.lbl_series_mean.toolTip())
        metric_median.setToolTip(self.lbl_series_median.toolTip())
        metric_spread.setToolTip(self.lbl_series_spread.toolTip())
        metric_stability.setToolTip(self.lbl_series_stability.toolTip())
        for metric_label in [metric_count, metric_mean, metric_median, metric_spread, metric_stability]:
            metric_label.setStyleSheet("color: gray;")
        series_metrics_layout.setColumnStretch(0, 0)
        series_metrics_layout.setColumnStretch(1, 0)
        series_metrics_layout.addWidget(metric_count, 0, 0)
        series_metrics_layout.addWidget(self.lbl_series_count, 0, 1)
        series_metrics_layout.addWidget(metric_mean, 1, 0)
        series_metrics_layout.addWidget(self.lbl_series_mean, 1, 1)
        series_metrics_layout.addWidget(metric_median, 2, 0)
        series_metrics_layout.addWidget(self.lbl_series_median, 2, 1)
        series_metrics_layout.addWidget(metric_spread, 3, 0)
        series_metrics_layout.addWidget(self.lbl_series_spread, 3, 1)
        series_metrics_layout.addWidget(metric_stability, 4, 0)
        series_metrics_layout.addWidget(self.lbl_series_stability, 4, 1)
        for value_label in [
            self.lbl_series_count,
            self.lbl_series_mean,
            self.lbl_series_median,
            self.lbl_series_spread,
            self.lbl_series_stability,
        ]:
            value_label.setStyleSheet(f"color: {RAZER_GREEN}; font-weight: bold;")
        self.lbl_recent_samples.setMinimumWidth(260)
        self.lbl_recent_samples.setMaximumHeight(86)
        self.lbl_recent_samples.setWordWrap(False)
        recent_group = QGroupBox("Показания")
        recent_group.setStyleSheet("QGroupBox { border: 0; color: gray; margin-top: 8px; }")
        recent_layout = QVBoxLayout(recent_group)
        recent_layout.setContentsMargins(0, 8, 0, 0)
        recent_layout.addWidget(self.lbl_recent_samples)
        self.btn_remove_last = QPushButton("Удалить последний")
        self.btn_clear_series = QPushButton("Очистить серию")
        self.btn_remove_last.clicked.connect(self.remove_last_sample)
        self.btn_clear_series.clicked.connect(self.clear_series)
        actions_layout = QHBoxLayout()
        actions_layout.addWidget(self.btn_add_sample)
        actions_layout.addWidget(self.btn_remove_last)
        actions_layout.addWidget(self.btn_clear_series)
        series_metrics_layout.addLayout(actions_layout, 5, 0, 1, 2)
        series_body_layout.addLayout(series_metrics_layout, stretch=0)
        series_body_layout.addWidget(recent_group, stretch=1)
        series_outer_layout.addWidget(self.series_body)
        layout.addWidget(self.series_group)

        self.lbl_status = QLabel("Инициализация...")
        self.lbl_status.setFont(QFont("Arial", 12))
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

        # Запуск фонового потока
        self.listener = MouseListenerThread()
        self.listener.filter_enabled = self.filter_enabled
        self.listener.statusSignal.connect(self.update_status)
        self.listener.leftClickSignal.connect(self.on_global_left_click)
        self.listener.recordingStartSignal.connect(self.on_recording_start)
        self.listener.recordingStopSignal.connect(self.on_recording_stop)
        self.listener.start()

    def update_status(self, msg, color):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color: {color};")

    def on_global_left_click(self):
        widget = QApplication.widgetAt(QCursor.pos())
        if self.is_interactive_widget(widget):
            return

        self.listener.start_recording()

    def is_interactive_widget(self, widget):
        while widget is not None:
            if isinstance(widget, (QAbstractButton, QDialog, QProgressBar)):
                return True
            widget = widget.parentWidget()
        return False

    def on_recording_start(self):
        self.update_status("🔴 Идет запись... Водите мышью влево-вправо.", RAZER_GREEN)
        self.lbl_angle_val.setText("---")
        self.lbl_angle_val.setStyleSheet("color: white;")
        self.lbl_quality.setText("Качество: идет запись")
        self.quality_bar.setValue(0)
        self.btn_add_sample.setEnabled(False)
        self.canvas.set_recording()

    def on_recording_stop(self, angle, m, b, path, meta):
        self.lbl_angle_val.setText(f"{angle:.2f}°")
        self.lbl_angle_val.setStyleSheet(f"color: {RAZER_GREEN};")
        score, quality_label = quality_score_from_meta(meta, path)
        self.quality_bar.setValue(score)
        self.lbl_quality.setText(
            f"Качество: {quality_label} · выбросы {meta['rejected_delta_count']} · шум {meta['rmse_ratio'] * 100:.1f}%"
        )
        self.last_sample = {
            "angle": angle,
            "quality_score": score,
            "quality_label": quality_label,
        }
        self.btn_add_sample.setEnabled(score >= 45)
        self.update_status("✅ Замер готов. Проверьте качество и добавьте в серию.", "white")
        self.canvas.update_result(path, m, b)

    def add_last_sample_to_series(self):
        if not self.last_sample:
            return

        self.samples.append(dict(self.last_sample))
        self.update_series_stats()
        self.btn_add_sample.setEnabled(False)
        self.update_status("Замер добавлен в серию.", RAZER_GREEN)

    def remove_last_sample(self):
        if self.samples:
            self.samples.pop()
            self.update_series_stats()
            self.update_status("Последний замер удален.", "white")

    def clear_series(self):
        self.samples.clear()
        self.update_series_stats()
        self.update_status("Серия очищена.", "white")

    def toggle_series_panel(self):
        self.series_collapsed = not self.series_collapsed
        self.series_body.setVisible(not self.series_collapsed)
        self.btn_toggle_series.setText("Развернуть" if self.series_collapsed else "Свернуть")

    def update_series_stats(self):
        summary = summarize_series(self.samples)
        self.lbl_series_count.setText(str(summary["count"]))
        if not self.samples:
            self.lbl_series_mean.setText("—")
            self.lbl_series_median.setText("—")
            self.lbl_series_spread.setText("—")
            self.lbl_series_stability.setText("—")
            self.lbl_recent_samples.setText("Добавьте минимум 3 замера.")
            return

        self.lbl_series_mean.setText(f"{summary['mean']:.2f}°")
        self.lbl_series_median.setText(f"{summary['median']:.2f}°")
        self.lbl_series_spread.setText(f"±{summary['spread']:.2f}°")
        self.lbl_series_stability.setText(f"{summary['stability']}%")
        recent = []
        for index, sample in list(enumerate(self.samples, start=1))[-5:][::-1]:
            recent.append(f"#{index}  {sample['angle']:.2f}°  {sample['quality_label']}")
        self.lbl_recent_samples.setText("\n".join(recent))

    def open_settings(self):
        dialog = SettingsDialog(self.filter_enabled, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.filter_enabled = dialog.is_filter_enabled()
            self.listener.filter_enabled = self.filter_enabled
            if self.filter_enabled:
                self.update_status("Фильтр неровных участков включен.", RAZER_GREEN)
            else:
                self.update_status("Фильтр неровных участков выключен.", "white")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                logging.info("Выход из полноэкранного режима")
                self.showNormal()
            else:
                logging.info("Переход в полноэкранный режим")
                self.showFullScreen()
        super().keyPressEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    logging.info("Приложение запущено.")
    sys.exit(app.exec())
