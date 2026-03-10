"""
Matplotlib 嵌入控件

支持缩放/平移/保存，自适应深色/浅色主题。
右键菜单替代默认工具栏，保持界面紧凑。

关键修复：
- show_toolbar=False 时，不创建任何 toolbar 实例（无双工具栏）
- 右键菜单操作直接操作 canvas，不依赖隐藏 toolbar
- 中文字体支持
"""

import matplotlib
matplotlib.use('QtAgg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget, QMenu, QFileDialog, QToolButton
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction

from seiswave.gui.styles import get_mpl_colors

# 中文字体配置：中文宋体(Songti SC) + 英文 Times New Roman
plt.rcParams['font.family'] = ['Times New Roman', 'Songti SC']
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

        # 为图标按钮补充可访问标签（相当于 aria-label）
        for action in self.actions():
            text = action.text().replace('&', '').strip()
            if not text:
                continue
            action.setToolTip(text)
            btn = self.widgetForAction(action)
            if isinstance(btn, QToolButton):
                btn.setAccessibleName(text)
                btn.setAccessibleDescription(text)
                btn.setToolTip(text)


class PlotWidget(QWidget):
    """带右键菜单的 Matplotlib 绘图控件

    默认隐藏工具栏，通过右键菜单提供缩放/平移/还原/保存功能。
    可选显示紧凑工具栏（compact_toolbar=True 且 show_toolbar=True）。

    关键：show_toolbar=False 时绝不创建任何 toolbar 实例。
    """

    def __init__(self, parent=None, dark=False, show_toolbar=False,
                 compact_toolbar=True):
        super().__init__(parent)
        self.canvas = PlotCanvas(self, dark=dark)

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

        # 右键菜单（始终可用）
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

    def _ensure_toolbar(self):
        """懒创建临时 toolbar 用于右键菜单操作（不添加到布局）"""
        if self.toolbar is not None:
            return self.toolbar
        if not hasattr(self, '_hidden_toolbar'):
            self._hidden_toolbar = NavigationToolbar2QT(self.canvas)
            self._hidden_toolbar.setVisible(False)
        return self._hidden_toolbar

    def _action_home(self):
        tb = self._ensure_toolbar()
        tb.home()

    def _action_pan(self):
        tb = self._ensure_toolbar()
        tb.pan()

    def _action_zoom(self):
        tb = self._ensure_toolbar()
        tb.zoom()

    def _action_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            self.canvas.fig.savefig(path, dpi=300, bbox_inches='tight')

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
