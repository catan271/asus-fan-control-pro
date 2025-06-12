import asyncio
from copy import deepcopy
import os
import sys
from typing import Callable, Optional, Union
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSlider,
    QPushButton,
    QCheckBox,
    QStackedWidget,
    QLineEdit,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QCloseEvent
import pyqtgraph as pg
from qasync import QEventLoop, asyncClose, asyncSlot
from asus_control import AsusControl
from utils import (
    apply_settings,
    clear_layout,
    load_settings,
    save_settings,
    service_apply_settings,
    unregister,
    cleanup,
)


class DraggablePoint(pg.ScatterPlotItem):
    def __init__(
        self,
        plot: pg.PlotWidget,
        points: list[list[int]],
        on_change: Callable,
        color: Union[QColor, Qt.GlobalColor] = "b",
    ):
        self.on_change = on_change
        self._dragged_index = None
        self.data_points = points  # [[x, y], ...]
        if points:
            x, y = zip(*points)
        else:
            x, y = [], []

        super().__init__(x=x, y=y, size=16, brush=color, symbol="o", pxMode=True)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.line = pg.PlotDataItem(x=x, y=y, pen=pg.mkPen(color, width=2))
        plot.addItem(self)
        plot.addItem(self.line)

    def mouseDragEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            ev.ignore()
            return

        if ev.isStart():
            pts = self.pointsAt(ev.pos())
            if pts.size > 0:
                self._dragged_index = pts[0].index()
                ev.accept()
            else:
                ev.ignore()

        elif ev.isFinish():
            if self._dragged_index is not None:
                self._dragged_index = None
                if self.on_change:
                    self.on_change()

        elif self._dragged_index is not None:
            new_pos = ev.pos()
            x_original = self.data_points[self._dragged_index][0]  # Keep original x
            new_y = max(0, min(100, new_pos.y()))  # Clamp y between 0–100
            self.data_points[self._dragged_index] = [x_original, new_y]
            x, y = zip(*self.data_points)
            self.setData(x=x, y=y)
            self.update_plot()
            ev.accept()
        else:
            ev.ignore()

    def update_plot(self):
        x, y = zip(*self.data_points)
        self.setData(x=x, y=y)
        self.line.setData(x=x, y=y)

    def get_points(self):
        return self.data_points


class FanControlTab(QWidget):
    def __init__(self, value, on_change: Callable):
        super().__init__()
        self.value = value

        def handle_change(value):
            self.value = value
            on_change(value)

        self.on_change = handle_change

        self.layout = QVBoxLayout(self)
        self.radio_off = QRadioButton("Off")
        self.radio_specific = QRadioButton("Specific Value")
        self.radio_curve = QRadioButton("Fan Curve")
        self.radio_off.setChecked(value["mode"] == 0)
        self.radio_specific.setChecked(value["mode"] == 1)
        self.radio_curve.setChecked(value["mode"] == 2)

        self.layout.addWidget(self.radio_off)
        self.layout.addWidget(self.radio_specific)
        self.layout.addWidget(self.radio_curve)

        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)

        # Off
        self.stack.addWidget(QWidget())

        # Specific
        specific_widget = QWidget()
        specific_layout = QVBoxLayout()
        specific_layout.setAlignment(Qt.AlignTop)  # Align top
        specific_widget.setLayout(specific_layout)

        self.specific_value = value["specific_value"]
        self.slider_label = QLabel(f"Fan Speed (%) {self.specific_value}")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setValue(value["specific_value"])
        self.slider.setRange(0, 100)
        self.slider.setPageStep(5)
        self.slider.valueChanged.connect(self.update_specific_value)

        specific_layout.addWidget(self.slider_label)
        specific_layout.addWidget(self.slider)
        self.stack.addWidget(specific_widget)

        # Curve
        curve_widget = QWidget()
        curve_layout = QVBoxLayout(curve_widget)

        input_layout = QHBoxLayout()
        curve_interval_layout = QVBoxLayout()
        self.curve_interval_input = QLineEdit(str(value["curve_interval"]))
        self.curve_interval_input.textChanged.connect(self.update_curve_interval)
        self.curve_interval_input.setPlaceholderText("Interval in milliseconds")
        curve_interval_layout.addWidget(QLabel("Polling interval (ms):"))
        curve_interval_layout.addWidget(self.curve_interval_input)
        moving_average_layout = QVBoxLayout()
        self.moving_average_input = QLineEdit(str(value["moving_average"]))
        self.moving_average_input.textChanged.connect(self.update_moving_average)
        self.moving_average_input.setPlaceholderText("Moving average limit")
        moving_average_layout.addWidget(QLabel("Moving average:"))
        moving_average_layout.addWidget(self.moving_average_input)
        input_layout.addLayout(curve_interval_layout)
        input_layout.addLayout(moving_average_layout)
        curve_layout.addLayout(input_layout)

        chart_layout = QHBoxLayout()

        self.cpu_chart = pg.PlotWidget(title="CPU Temp → Fan Speed")
        self.gpu_chart = pg.PlotWidget(title="GPU Temp → Fan Speed")

        for chart in [self.cpu_chart, self.gpu_chart]:
            chart.setXRange(0, 100, padding=0)
            chart.setYRange(0, 100, padding=0)
            chart.setLimits(xMin=0, xMax=100, yMin=0, yMax=100)
            chart.setMouseEnabled(x=False, y=False)
            chart.showGrid(x=True, y=True)
            chart.setBackground("w")

        self.cpu_scatter = DraggablePoint(
            self.cpu_chart, value["cpu_curve"], self.update_cpu_curve
        )
        self.gpu_scatter = DraggablePoint(
            self.gpu_chart, value["gpu_curve"], self.update_gpu_curve, color="r"
        )

        chart_layout.addWidget(self.cpu_chart)
        chart_layout.addWidget(self.gpu_chart)

        curve_layout.addLayout(chart_layout)

        self.stack.addWidget(curve_widget)
        self.stack.setCurrentIndex(value["mode"])

        self.radio_off.toggled.connect(self.update_mode)
        self.radio_specific.toggled.connect(self.update_mode)
        self.radio_curve.toggled.connect(self.update_mode)

    def update_mode(self):
        if self.radio_off.isChecked():
            i = 0
        elif self.radio_specific.isChecked():
            i = 1
        elif self.radio_curve.isChecked():
            i = 2
        self.stack.setCurrentIndex(i)
        self.on_change({**self.value, "mode": i})

    def update_specific_value(self):
        self.specific_value = self.slider.value()
        self.slider_label.setText(f"Fan Speed (%): {self.specific_value}")
        self.on_change({**self.value, "specific_value": self.specific_value})

    def update_curve_interval(self):
        v = max(int(self.curve_interval_input.text()), 1000)
        self.curve_interval = v
        self.on_change({**self.value, "curve_interval": v})

    def update_moving_average(self):
        v = max(int(self.curve_interval_input.text()), 1000)
        self.moving_average = v
        self.on_change({**self.value, "moving_average": v})

    def update_cpu_curve(self):
        cpu_curve = self.cpu_scatter.get_points()
        self.cpu_curve = cpu_curve
        self.on_change({**self.value, "cpu_curve": cpu_curve})

    def update_gpu_curve(self):
        gpu_curve = self.gpu_scatter.get_points()
        self.gpu_curve = gpu_curve
        self.on_change({**self.value, "gpu_curve": gpu_curve})


class FanControlApp(QWidget):
    def __init__(self, asus: AsusControl):
        super().__init__()
        self.asus = asus
        self.fan_count = asus.fan_count()
        self.old_settings = load_settings(self.fan_count)
        self.settings = deepcopy(self.old_settings)
        self.setWindowTitle("ASUS Fan Control")

        self.main_layout = QVBoxLayout(self)
        self.init_elements()

    def init_elements(self):
        # Top Switches
        switches_layout = QHBoxLayout()
        self.startup_checkbox = QCheckBox("Start with Windows")
        self.startup_checkbox.setChecked(self.settings["start_with_windows"])
        self.startup_checkbox.clicked.connect(self.update_start_with_windows)
        self.sync_checkbox = QCheckBox("Fan Sync")
        self.sync_checkbox.setChecked(self.settings["fan_sync"])
        self.sync_checkbox.clicked.connect(self.update_fan_sync)
        switches_layout.addWidget(self.startup_checkbox)
        switches_layout.addWidget(self.sync_checkbox)
        self.main_layout.addLayout(switches_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.fan_tabs = []
        for i in range(self.fan_count):
            tab = FanControlTab(self.settings["fans"][i], self.update_fan_settings(i))
            self.fan_tabs.append(tab)
        self.update_fan_sync()
        self.main_layout.addWidget(self.tabs)

        # Buttons
        buttons_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel)
        buttons_layout.addWidget(self.save_btn)
        buttons_layout.addWidget(self.apply_btn)
        buttons_layout.addWidget(self.cancel_btn)
        self.main_layout.addLayout(buttons_layout)

    def update_start_with_windows(self):
        self.settings["start_with_windows"] = self.startup_checkbox.isChecked()

    def update_fan_sync(self):
        while self.tabs.count():
            self.tabs.removeTab(0)
        is_checked = self.sync_checkbox.isChecked()
        self.settings["fan_sync"] = is_checked
        for i in range(1 if is_checked else self.fan_count):
            self.tabs.addTab(self.fan_tabs[i], f"Fan {i+1}")

    def update_fan_settings(self, i: int):
        def update(value: dict):
            self.settings["fans"][i] = value

        return update

    def save(self):
        save_settings(self.settings)

    def apply(self):
        unregister()
        apply_settings(self.asus, self.settings)

    def cancel(self):
        self.settings = deepcopy(self.old_settings)
        clear_layout(self.main_layout)
        self.init_elements()


def app():
    asus = AsusControl()
    app = QApplication(sys.argv)
    event_loop = QEventLoop(app)
    asyncio.set_event_loop(event_loop)
    app_close_event = asyncio.Event()

    fan_control = FanControlApp(asus)
    fan_control.resize(1200, 800)
    fan_control.show()
    app.aboutToQuit.connect(app_close_event.set)

    with event_loop:
        try:
            event_loop.run_until_complete(app_close_event.wait())
            asyncio.run(cleanup(asus))
        except KeyboardInterrupt:
            return


async def service():
    asus = AsusControl()
    service_apply_settings(asus)

    while True:
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if not tasks:
            break
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # sys.stdout = open(os.path.join(current_dir, "out.log"), "w")
    # sys.stderr = open(os.path.join(current_dir, "err.log"), "w")

    if "--service" in sys.argv:
        asyncio.run(service())
    else:
        app()
