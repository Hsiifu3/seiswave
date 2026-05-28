"""参数卡片组件

可复用的参数卡片，支持：
- TypeCard：地震动类型选择（下拉菜单）
- ParamCard(title, params)：通用参数组（可折叠）
- NFPExtraCard：NFP 专属参数（断层类型、脉冲参数显示）
- ProgressCard：进度条 + 状态文本
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QLabel, QProgressBar, QPushButton, QSizePolicy,
    QFrame, QGridLayout,
)
from PySide6.QtCore import Signal, Qt


class TypeCard(QGroupBox):
    """地震动类型选择卡片"""

    type_changed = Signal(int)

    def __init__(self, labels=None, parent=None):
        super().__init__("地震动类型", parent)
        self._labels = labels or []
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)
        layout.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        layout.setVerticalSpacing(6)

        self._combo = QComboBox()
        if self._labels:
            self._combo.addItems(self._labels)
        self._combo.currentIndexChanged.connect(self.type_changed.emit)
        layout.addRow("类型:", self._combo)

    def current_index(self):
        return self._combo.currentIndex()

    def current_text(self):
        return self._combo.currentText()

    def set_index(self, idx):
        self._combo.setCurrentIndex(idx)

    @property
    def combo(self):
        return self._combo


class ParamCard(QGroupBox):
    """通用参数组卡片（可折叠）

    用法：
        card = ParamCard("生成参数")
        card.add_row("时间步长:", spin_box)
    """

    toggled = Signal(bool)  # 展开/折叠状态

    def __init__(self, title="参数", collapsed=False, parent=None):
        super().__init__(title, parent)
        self._collapsed = collapsed
        self._rows: list[tuple[str, QWidget]] = []
        self._setup_ui()

    def _setup_ui(self):
        self._content = QWidget()
        self._form = QFormLayout(self._content)
        self._form.setLabelAlignment(Qt.AlignRight)
        self._form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self._form.setVerticalSpacing(6)
        self._form.setHorizontalSpacing(8)

        # 折叠按钮
        self._toggle_btn = QPushButton("▼")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; "
            "font-size: 10px; color: #2196F3; }"
        )
        self._toggle_btn.clicked.connect(self._on_toggle)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._content)

        if self._collapsed:
            self._content.setVisible(False)
            self._toggle_btn.setText("▶")

    def _on_toggle(self):
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._toggle_btn.setText("▶" if self._collapsed else "▼")
        self.toggled.emit(not self._collapsed)
        # 通知布局更新
        if self.parentWidget():
            self.parentWidget().adjustSize()

    def add_row(self, label: str, widget: QWidget):
        """添加一行参数"""
        self._rows.append((label, widget))
        self._form.addRow(label, widget)

    def set_collapsed(self, collapsed: bool):
        if collapsed != self._collapsed:
            self._on_toggle()

    @property
    def toggle_btn(self):
        return self._toggle_btn

    @property
    def is_collapsed(self):
        return self._collapsed


class NFPExtraCard(QGroupBox):
    """NFP 专属参数卡片

    显示：断层类型、脉冲参数（Tp, A, φ）、Baker 置信度进度条
    """

    def __init__(self, parent=None):
        super().__init__("近场脉冲参数", parent)
        self.setProperty("accent", True)
        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 断层类型
        fault_row = QHBoxLayout()
        fault_row.addWidget(QLabel("断层类型:"))
        self._fault_label = QLabel("--")
        self._fault_label.setStyleSheet("font-weight: bold;")
        fault_row.addWidget(self._fault_label)
        fault_row.addStretch()
        layout.addLayout(fault_row)

        # 脉冲参数网格
        grid = QGridLayout()
        grid.setSpacing(4)
        self._lbl_tp = QLabel("--")
        self._lbl_a = QLabel("--")
        self._lbl_phi = QLabel("--")
        self._lbl_t0 = QLabel("--")

        for lbl in (self._lbl_tp, self._lbl_a, self._lbl_phi, self._lbl_t0):
            lbl.setStyleSheet("font-family: monospace; font-size: 12px;")

        grid.addWidget(QLabel("Tp (s):"), 0, 0)
        grid.addWidget(self._lbl_tp, 0, 1)
        grid.addWidget(QLabel("A (cm/s):"), 0, 2)
        grid.addWidget(self._lbl_a, 0, 3)
        grid.addWidget(QLabel("φ (rad):"), 1, 0)
        grid.addWidget(self._lbl_phi, 1, 1)
        grid.addWidget(QLabel("t₀ (s):"), 1, 2)
        grid.addWidget(self._lbl_t0, 1, 3)
        layout.addLayout(grid)

        # Baker 置信度
        baker_frame = QFrame()
        baker_frame.setFrameShape(QFrame.StyledPanel)
        baker_layout = QVBoxLayout(baker_frame)
        baker_layout.setContentsMargins(4, 4, 4, 4)
        baker_layout.setSpacing(2)

        baker_header = QHBoxLayout()
        baker_header.addWidget(QLabel("Baker 识别置信度"))
        self._baker_conf_label = QLabel("0.000")
        self._baker_conf_label.setStyleSheet(
            "font-family: monospace; font-size: 12px; font-weight: bold;"
        )
        baker_header.addWidget(self._baker_conf_label)
        baker_layout.addLayout(baker_header)

        self._baker_bar = QProgressBar()
        self._baker_bar.setRange(0, 1000)
        self._baker_bar.setValue(0)
        self._baker_bar.setProperty("accent", True)
        baker_layout.addWidget(self._baker_bar)

        self._baker_detail = QLabel("")
        self._baker_detail.setWordWrap(True)
        self._baker_detail.setStyleSheet("font-size: 11px; color: #888;")
        baker_layout.addWidget(self._baker_detail)

        layout.addWidget(baker_frame)
        layout.addStretch()

    def set_pulse_params(self, params):
        """设置脉冲参数

        params 为 PulseParameters 对象或 dict，包含 Tp, A, phi, t0
        """
        if params is None:
            self._lbl_tp.setText("--")
            self._lbl_a.setText("--")
            self._lbl_phi.setText("--")
            self._lbl_t0.setText("--")
            return
        # 兼容 dict 和 object 两种访问方式
        def _get(key, default=0):
            if hasattr(params, key):
                return getattr(params, key, default)
            if hasattr(params, 'get'):
                return params.get(key, default)
            return default
        self._lbl_tp.setText(f"{_get('Tp'):.2f}")
        self._lbl_a.setText(f"{_get('A'):.1f}")
        self._lbl_phi.setText(f"{_get('phi', _get('φ')):.3f}")
        self._lbl_t0.setText(f"{_get('t0'):.2f}")

    def set_baker_metrics(self, metrics):
        """设置 Baker 识别结果

        metrics 为 dict，包含 confidence, pulse_period, pulse_amplitude, energy_ratio, has_pulse
        """
        if not metrics:
            self._baker_bar.setValue(0)
            self._baker_conf_label.setText("0.000")
            self._baker_detail.setText("")
            return
        conf = metrics.get("confidence", 0.0)
        self._baker_bar.setValue(int(conf * 1000))
        self._baker_conf_label.setText(f"{conf:.3f}")
        detail = (
            f"含脉冲: {metrics.get('has_pulse', False)} | "
            f"估计 Tp={metrics.get('pulse_period', 0):.2f}s | "
            f"PGV={metrics.get('pulse_amplitude', 0):.1f}cm/s | "
            f"能量比={metrics.get('energy_ratio', 0):.3f}"
        )
        self._baker_detail.setText(detail)

    def set_fault_type(self, fault: str):
        self._fault_label.setText(fault)


class ProgressCard(QGroupBox):
    """进度条 + 状态文本卡片"""

    def __init__(self, parent=None):
        super().__init__("迭代进度", parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        self._status = QLabel("等待生成...")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._info = QLabel("")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("font-size: 11px; color: #666;")
        layout.addWidget(self._info)
        layout.addStretch()

    def set_progress(self, pct: int, text: str = ""):
        self._bar.setValue(pct)
        if text:
            self._status.setText(text)

    def set_info(self, lines: list[str]):
        self._info.setText("\n".join(lines))

    def set_status(self, text: str):
        self._status.setText(text)

    def reset(self):
        self._bar.setValue(0)
        self._status.setText("等待生成...")
        self._info.setText("")

    @property
    def bar(self):
        return self._bar

    @property
    def status_label(self):
        return self._status

    @property
    def info_label(self):
        return self._info
