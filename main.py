import sys
import math
import platform
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QSizePolicy)
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QDialog, QCheckBox, QDialogButtonBox
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

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

# ==========================================
# ПОТОК ЧТЕНИЯ МЫШИ (Фоновый)
# ==========================================
class MouseListenerThread(QThread):
    statusSignal = pyqtSignal(str, str)
    recordingStartSignal = pyqtSignal()
    recordingStopSignal = pyqtSignal(float, float, float, list)

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
                        self.start_recording()
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
                self.start_recording()
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
        logging.info("Начата запись движения мыши...")
        self.recordingStartSignal.emit()

    def add_motion_delta(self, dx, dy):
        self.path, accepted = apply_motion_delta(self.path, dx, dy, self.filter_enabled)
        if accepted:
            self.cur_x, self.cur_y = self.path[-1]

    def stop_recording(self):
        if self.recording:
            self.recording = False
            logging.info(f"Запись остановлена. Собрано точек: {len(self.path)}")
            measured_angle, m, b = calculate_regression(self.path)
            logging.info(f"Результаты расчетов: Отклонение={measured_angle:.3f}°, m={m:.5f}, b={b:.2f}")
            self.recordingStopSignal.emit(measured_angle, m, b, self.path)

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
        self.setMinimumSize(700, 500)
        self.resize(800, 600)         
        self.filter_enabled = False
        
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

        # Холст для рисования
        self.canvas = PlotWidget()
        layout.addWidget(self.canvas, stretch=1)

        # Значение угла
        self.lbl_angle_title = QLabel("УГОЛ ОТКЛОНЕНИЯ")
        self.lbl_angle_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.lbl_angle_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_angle_title)

        self.lbl_angle_val = QLabel("0.00°")
        self.lbl_angle_val.setFont(QFont("Arial", 40, QFont.Weight.Bold))
        self.lbl_angle_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_angle_val)

        self.lbl_status = QLabel("Инициализация...")
        self.lbl_status.setFont(QFont("Arial", 12))
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

        # Запуск фонового потока
        self.listener = MouseListenerThread()
        self.listener.filter_enabled = self.filter_enabled
        self.listener.statusSignal.connect(self.update_status)
        self.listener.recordingStartSignal.connect(self.on_recording_start)
        self.listener.recordingStopSignal.connect(self.on_recording_stop)
        self.listener.start()

    def update_status(self, msg, color):
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color: {color};")

    def on_recording_start(self):
        self.update_status("🔴 Идет запись... Водите мышью влево-вправо.", RAZER_GREEN)
        self.lbl_angle_val.setText("---")
        self.lbl_angle_val.setStyleSheet("color: white;")
        self.canvas.set_recording()

    def on_recording_stop(self, angle, m, b, path):
        self.lbl_angle_val.setText(f"{angle:.2f}°")
        self.lbl_angle_val.setStyleSheet(f"color: {RAZER_GREEN};")
        self.update_status("✅ Успешно! Можете повторить (ЛКМ).", "white")
        self.canvas.update_result(path, m, b)

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
