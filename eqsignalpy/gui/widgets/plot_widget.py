"""
Matplotlib 嵌入控件

支持缩放/平移/保存，自适应深色/浅色主题。
"""

import matplotlib
matplotlib.use('QtAgg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget

from eqsignalpy.gui.styles import get_mpl_colors

# 配置中文字体
plt.rcParams['font.sans-serif'] = ['Hiragino Sans GB', 'Heiti TC', 'Songti SC', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


class PlotCanvas(FigureCanvasQTAgg):
    """Matplotlib 画布"""

    def __init__(self, parent=None, width=8, height=5, dpi=100, dark=False):
        self._dark = dark
        colors = get_mpl_colors(dark)
        self.fig = Figure(figsize=(width, height), dpi=dpi,
                          facecolor=colors['bg'])
        self.ax = self.fig.add_subplot(111)
        self._apply_style(self.ax, colors)
        self.fig.tight_layout(pad=2.0)
        super().__init__(self.fig)
        self.setParent(parent)

    def _apply_style(self, ax, colors):
        ax.set_facecolor(colors['axes_bg'])
        ax.tick_params(colors=colors['fg'], labelsize=10)
        ax.xaxis.label.set_color(colors['fg'])
        ax.yaxis.label.set_color(colors['fg'])
        ax.title.set_color(colors['fg'])
        for spine in ax.spines.values():
            spine.set_color(colors['grid'])
        ax.grid(True, alpha=0.3, color=colors['grid'])

    def clear(self):
        self.ax.clear()
        colors = get_mpl_colors(self._dark)
        self._apply_style(self.ax, colors)

    def refresh(self):
        self.fig.tight_layout(pad=2.0)
        self.draw()

    def set_dark(self, dark: bool):
        self._dark = dark
        colors = get_mpl_colors(dark)
        self.fig.set_facecolor(colors['bg'])
        self._apply_style(self.ax, colors)
        self.refresh()


class PlotWidget(QWidget):
    """带工具栏的 Matplotlib 绘图控件"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self.canvas = PlotCanvas(self, dark=dark)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    @property
    def ax(self):
        return self.canvas.ax

    @property
    def fig(self):
        return self.canvas.fig

    def clear(self):
        self.canvas.clear()

    def refresh(self):
        self.canvas.refresh()

    def set_dark(self, dark: bool):
        self.canvas.set_dark(dark)
