"""中间主区域

- 弹性宽度，最小 500px
- QSplitter 上下分割：
  - 上部：SpectrumPlot（反应谱对比图）
  - 下部：PlotWidget（时程图）
- 上部高度 60%，下部 40%
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QSizePolicy,
)
from PySide6.QtCore import Qt

from seiswave.gui.widgets.spectrum_plot import SpectrumPlot
from seiswave.gui.widgets.plot_widget import PlotWidget


class CenterPanel(QWidget):
    """中间主区域：谱图 + 时程图"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumWidth(440)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._spec_plot = SpectrumPlot(
            dark=self._dark, log_x=False, show_toolbar=False)
        self._time_plot = PlotWidget(
            dark=self._dark, show_toolbar=False)

        self._splitter.addWidget(self._spec_plot)
        self._splitter.addWidget(self._time_plot)

        # 上部 60%，下部 40%
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([360, 240])

        layout.addWidget(self._splitter)
        # 生成前显示占位提示，替代空的 0-1 坐标图
        self._time_plot.show_placeholder("生成人工波后显示加速度时程")

    @property
    def spec_plot(self):
        return self._spec_plot

    @property
    def time_plot(self):
        return self._time_plot

    def set_dark(self, dark: bool):
        self._dark = dark
        self._spec_plot.set_dark(dark)
        self._time_plot.set_dark(dark)
