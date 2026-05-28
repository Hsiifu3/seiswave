"""左栏参数面板

- 宽度 320px，固定，QScrollArea 包裹
- 包含：TypeCard + ParamCard(震源参数) + ParamCard(生成参数) + ParamCard(迭代控制)
- 类型切换时动态显隐卡片
- 默认折叠非关键组
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QSizePolicy, QFormLayout, QGroupBox,
)
from PySide6.QtCore import Qt, Signal

from seiswave.gui.panels.param_form import ParamFormWidget, GM_TYPE_LABELS
from seiswave.gui.panels.progress_widget import ProgressWidget


class LeftPanel(QWidget):
    """左栏：参数输入 + 进度"""

    run_clicked = Signal()
    type_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        # 外层用 QScrollArea 包裹，保证不溢出
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        inner.setMinimumWidth(280)
        inner.setMaximumWidth(320)
        inner.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── 嵌入现有的 ParamFormWidget（向后兼容）──
        self._param_form = ParamFormWidget()
        layout.addWidget(self._param_form, 0)

        # ── 进度组件 ──
        self._progress = ProgressWidget()
        layout.addWidget(self._progress, 0)

        layout.addStretch(1)
        self._scroll.setWidget(inner)

        # 自身布局只放 scroll
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._scroll)

        self.setFixedWidth(320)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # 转发信号
        self._param_form.run_clicked.connect(self.run_clicked.emit)
        self._param_form.type_changed.connect(self.type_changed.emit)

    # ── 属性委托 ──

    @property
    def param_form(self):
        return self._param_form

    @property
    def progress(self):
        return self._progress

    @property
    def type_combo(self):
        return self._param_form._type_combo

    @property
    def special_group(self):
        return self._param_form._special_group

    @property
    def fault_combo(self):
        return self._param_form._fault_combo

    @property
    def dt_spin(self):
        return self._param_form._dt_spin

    @property
    def run_btn(self):
        return self._param_form._run_btn

    def set_type(self, index: int):
        self._param_form.set_type(index)

    def get_params(self):
        return self._param_form.get_params()

    def reset_defaults(self):
        self._param_form.reset_defaults()
