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
from PySide6.QtCore import QSize

from seiswave.gui.styles import get_mpl_colors

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


class CompactToolbar(NavigationToolbar2QT):
    """精简版 Matplotlib 工具栏，只保留核心按钮，高度紧凑"""

    # 只保留缩放、平移、还原、保存
    toolitems = [t for t in NavigationToolbar2QT.toolitems
                 if t[0] in ('Home', 'Back', 'Forward', 'Pan', 'Zoom', 'Save')]

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        self.setMaximumHeight(28)
        self.setIconSize(QSize(16, 16))
        self.setStyleSheet("QToolBar { spacing: 1px; padding: 0px; }")


class PlotWidget(QWidget):
    """带工具栏的 Matplotlib 绘图控件

    Parameters
    ----------
    show_toolbar : bool
        是否显示工具栏（默认隐藏，右键菜单仍可用）
    compact_toolbar : bool
        使用精简工具栏（仅在 show_toolbar=True 时生效）
    """

    def __init__(self, parent=None, dark=False, show_toolbar=False,
                 compact_toolbar=True):
        super().__init__(parent)
        self.canvas = PlotCanvas(self, dark=dark)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if show_toolbar:
            if compact_toolbar:
                self.toolbar = CompactToolbar(self.canvas, self)
            else:
                self.toolbar = NavigationToolbar2QT(self.canvas, self)
            layout.addWidget(self.toolbar)
        else:
            # 创建隐藏的 toolbar 以保留键盘快捷键支持
            # 不传 parent 避免被自动添加到布局中产生双工具栏
            self.toolbar = NavigationToolbar2QT(self.canvas)
            self.toolbar.setParent(self)
            self.toolbar.hide()

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
