"""
Matplotlib 嵌入控件

支持缩放/平移/保存，自适应深色/浅色主题。
右键菜单替代默认工具栏，保持界面紧凑。
"""

import matplotlib
matplotlib.use('QtAgg')

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget, QMenu
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction

from seiswave.gui.styles import get_mpl_colors


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

    def set_dark(self, dark):
        self._dark = dark
        colors = get_mpl_colors(dark)
        self.fig.set_facecolor(colors['bg'])
        self._apply_style(self.ax, colors)
        self.refresh()


class CompactToolbar(NavigationToolbar2QT):
    """精简版 Matplotlib 工具栏，只保留核心按钮，高度 ≤ 28px"""

    toolitems = [t for t in NavigationToolbar2QT.toolitems
                 if t[0] in ('Home', 'Back', 'Forward', 'Pan', 'Zoom', 'Save')]

    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        self.setMaximumHeight(28)
        self.setIconSize(QSize(16, 16))
        self.setStyleSheet("QToolBar { spacing: 1px; padding: 0px; }")


class PlotWidget(QWidget):
    """带右键菜单的 Matplotlib 绘图控件

    默认隐藏工具栏，通过右键菜单提供缩放/平移/还原/保存功能。
    可选显示紧凑工具栏（compact_toolbar=True 且 show_toolbar=True）。

    不会创建隐藏的第二个 toolbar，避免双工具栏问题。
    """

    def __init__(self, parent=None, dark=False, show_toolbar=False,
                 compact_toolbar=True):
        super().__init__(parent)
        self.canvas = PlotCanvas(self, dark=dark)
        self._toolbar_visible = show_toolbar

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 只在需要时创建工具栏，绝不创建隐藏的 toolbar
        self.toolbar = None
        if show_toolbar:
            if compact_toolbar:
                self.toolbar = CompactToolbar(self.canvas, self)
            else:
                self.toolbar = NavigationToolbar2QT(self.canvas, self)
            layout.addWidget(self.toolbar)

        layout.addWidget(self.canvas)

        # 右键菜单（始终可用，无论工具栏是否显示）
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos):
        """右键菜单：提供缩放/平移/还原/保存"""
        menu = QMenu(self)

        home_action = QAction("还原视图", self)
        home_action.triggered.connect(self._action_home)
        menu.addAction(home_action)

        menu.addSeparator()

        pan_action = QAction("平移模式", self)
        pan_action.triggered.connect(self._action_pan)
        menu.addAction(pan_action)

        zoom_action = QAction("框选缩放", self)
        zoom_action.triggered.connect(self._action_zoom)
        menu.addAction(zoom_action)

        menu.addSeparator()

        save_action = QAction("保存图片...", self)
        save_action.triggered.connect(self._action_save)
        menu.addAction(save_action)

        menu.exec(self.canvas.mapToGlobal(pos))

    def _get_or_create_toolbar(self):
        """懒创建临时 toolbar 用于执行操作（不添加到布局）"""
        if self.toolbar is not None:
            return self.toolbar
        # 创建临时 toolbar 但不显示
        if not hasattr(self, '_hidden_toolbar'):
            self._hidden_toolbar = NavigationToolbar2QT(self.canvas)
            self._hidden_toolbar.setVisible(False)
        return self._hidden_toolbar

    def _action_home(self):
        tb = self._get_or_create_toolbar()
        tb.home()

    def _action_pan(self):
        tb = self._get_or_create_toolbar()
        tb.pan()

    def _action_zoom(self):
        tb = self._get_or_create_toolbar()
        tb.zoom()

    def _action_save(self):
        tb = self._get_or_create_toolbar()
        tb.save_figure()

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

    def set_dark(self, dark):
        self.canvas.set_dark(dark)
