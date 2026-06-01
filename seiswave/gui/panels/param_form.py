"""参数输入面板"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QDoubleSpinBox, QSpinBox, QComboBox, QPushButton,
    QLabel,
)
from PySide6.QtCore import Qt, Signal

GM_TYPE_LABELS = ["一般人工波", "远场 FF", "近场无脉冲 NF", "近场脉冲 NFP"]
GM_TYPE_CODES = {"一般人工波": None, "远场 FF": "FF",
                 "近场无脉冲 NF": "NF", "近场脉冲 NFP": "NFP"}


class ParamFormWidget(QWidget):
    """参数输入面板：所有 SpinBox/ComboBox 的创建、取值、显隐控制"""

    run_clicked = Signal()
    type_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # ── 地震动类型选择 ──
        type_group = QGroupBox("地震动类型")
        type_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 6px; }")
        type_form = QFormLayout(type_group)
        type_form.setLabelAlignment(Qt.AlignRight)
        type_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        type_form.setVerticalSpacing(6)
        self._type_combo = QComboBox()
        self._type_combo.addItems(GM_TYPE_LABELS)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_form.addRow("类型:", self._type_combo)
        layout.addWidget(type_group)

        # ── 目标谱（仅一般人工波需要）──
        target_group = QGroupBox("目标谱")
        target_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 6px; }")
        target_form = QFormLayout(target_group)
        target_form.setLabelAlignment(Qt.AlignRight)
        target_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        target_form.setVerticalSpacing(6)
        self._target_combo = QComboBox()
        self._target_combo.addItems(["当前规范谱"])
        self._target_combo.setEnabled(False)
        target_form.addRow("目标谱来源:", self._target_combo)
        # 目标谱信息标签
        self._target_info_label = QLabel("尚未设置")
        self._target_info_label.setWordWrap(True)
        target_form.addRow("当前谱:", self._target_info_label)
        layout.addWidget(target_group)

        # ── 特殊地震动参数（FF/NF/NFP）──
        self._special_group = QGroupBox("震源参数")
        self._special_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 6px; }")
        special_form = QFormLayout(self._special_group)
        special_form.setLabelAlignment(Qt.AlignRight)
        special_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        special_form.setVerticalSpacing(6)

        self._mw_spin = QDoubleSpinBox()
        self._mw_spin.setRange(5.0, 9.5)
        self._mw_spin.setSingleStep(0.1)
        self._mw_spin.setValue(7.0)
        self._mw_spin.setDecimals(1)
        self._mw_spin.setFixedWidth(120)
        special_form.addRow("矩震级 Mw:", self._mw_spin)

        self._r_spin = QDoubleSpinBox()
        self._r_spin.setRange(0.1, 300.0)
        self._r_spin.setSingleStep(1.0)
        self._r_spin.setValue(10.0)
        self._r_spin.setDecimals(1)
        self._r_spin.setFixedWidth(120)
        special_form.addRow("断层距 R (km):", self._r_spin)

        self._vs30_spin = QDoubleSpinBox()
        self._vs30_spin.setRange(100.0, 2000.0)
        self._vs30_spin.setSingleStep(50.0)
        self._vs30_spin.setValue(760.0)
        self._vs30_spin.setDecimals(0)
        self._vs30_spin.setFixedWidth(120)
        special_form.addRow("Vs30 (m/s):", self._vs30_spin)

        self._fault_combo = QComboBox()
        self._fault_combo.addItems(["strike_slip", "normal", "reverse"])
        special_form.addRow("断层类型:", self._fault_combo)

        self._special_group.setVisible(False)
        layout.addWidget(self._special_group)

        # ── 通用生成参数 ──
        gen_group = QGroupBox("生成参数")
        gen_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 6px; }")
        gen_form = QFormLayout(gen_group)
        gen_form.setLabelAlignment(Qt.AlignRight)
        gen_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        gen_form.setVerticalSpacing(6)

        # 新增：持时控制（自动计算 n = round(持时 / dt)）
        self._dur_spin = QDoubleSpinBox()
        self._dur_spin.setRange(10.0, 300.0)
        self._dur_spin.setSingleStep(5.0)
        self._dur_spin.setValue(40.0)
        self._dur_spin.setDecimals(1)
        self._dur_spin.setFixedWidth(120)
        self._dur_spin.valueChanged.connect(self._on_duration_changed)
        gen_form.addRow("持时 (s):", self._dur_spin)

        self._npts_spin = QSpinBox()
        self._npts_spin.setRange(256, 65536)
        self._npts_spin.setSingleStep(1024)
        self._npts_spin.setValue(2000)
        self._npts_spin.setFixedWidth(120)
        self._npts_spin.setReadOnly(True)
        self._npts_spin.setToolTip("由持时和 Δt 自动计算")
        gen_form.addRow("数据点数:", self._npts_spin)

        self._dt_spin = QDoubleSpinBox()
        self._dt_spin.setRange(0.001, 0.1)
        self._dt_spin.setSingleStep(0.005)
        self._dt_spin.setValue(0.02)
        self._dt_spin.setDecimals(3)
        self._dt_spin.setFixedWidth(120)
        self._dt_spin.valueChanged.connect(self._on_dt_changed)
        gen_form.addRow("时间步长 Δt (s):", self._dt_spin)

        self._pga_spin = QDoubleSpinBox()
        self._pga_spin.setRange(0.01, 5.0)
        self._pga_spin.setSingleStep(0.05)
        self._pga_spin.setValue(0.20)
        self._pga_spin.setDecimals(3)
        self._pga_spin.setFixedWidth(120)
        self._pga_spin.setEnabled(False)
        self._pga_spin.setToolTip("由当前目标谱自动确定")
        gen_form.addRow("目标 PGA (g):", self._pga_spin)

        self._zeta_spin = QDoubleSpinBox()
        self._zeta_spin.setRange(0.01, 0.30)
        self._zeta_spin.setSingleStep(0.01)
        self._zeta_spin.setValue(0.05)
        self._zeta_spin.setDecimals(2)
        self._zeta_spin.setFixedWidth(120)
        gen_form.addRow("阻尼比 ζ:", self._zeta_spin)

        layout.addWidget(gen_group)

        # ── 迭代控制 ──
        iter_group = QGroupBox("迭代控制")
        iter_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 6px; }")
        iter_form = QFormLayout(iter_group)
        iter_form.setLabelAlignment(Qt.AlignRight)
        iter_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        iter_form.setVerticalSpacing(6)

        # 新增：算法选择（频域法更快）
        self._algo_combo = QComboBox()
        self._algo_combo.addItems(["时域法", "频域法"])
        self._algo_combo.setToolTip("时域法：基于小波叠加迭代，稳定性好；频域法：基于频域修正，速度更快")
        iter_form.addRow("匹配算法:", self._algo_combo)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.01, 0.20)
        self._tol_spin.setSingleStep(0.01)
        self._tol_spin.setValue(0.05)
        self._tol_spin.setDecimals(2)
        self._tol_spin.setFixedWidth(120)
        iter_form.addRow("收敛容限:", self._tol_spin)

        self._maxiter_spin = QSpinBox()
        self._maxiter_spin.setRange(1, 200)
        self._maxiter_spin.setSingleStep(1)
        self._maxiter_spin.setValue(1)
        self._maxiter_spin.setFixedWidth(120)
        iter_form.addRow("最大迭代次数:", self._maxiter_spin)

        self._trials_spin = QSpinBox()
        self._trials_spin.setRange(1, 10)
        self._trials_spin.setSingleStep(1)
        self._trials_spin.setValue(1)
        self._trials_spin.setFixedWidth(120)
        iter_form.addRow("Trial 数量:", self._trials_spin)

        layout.addWidget(iter_group)

        # ── 执行按钮 ──
        self._run_btn = QPushButton("生成人工波")
        self._run_btn.clicked.connect(self.run_clicked.emit)
        layout.addWidget(self._run_btn)

        layout.addStretch()

    # ── 类型切换 ──

    def _on_type_changed(self, index):
        label = GM_TYPE_LABELS[index]
        is_general = (label == "一般人工波")
        is_nfp = (label == "近场脉冲 NFP")

        self._special_group.setVisible(not is_general)
        self._target_combo.setEnabled(is_general)

        # 调整 dt 默认值
        if is_general or label == "远场 FF":
            self._dt_spin.setValue(0.02)
        else:
            self._dt_spin.setValue(0.01)

        # 断层类型仅 NFP 可用
        self._fault_combo.setEnabled(is_nfp)
        self._fault_combo.setToolTip(
            "仅近场脉冲 NFP 需要指定断层类型" if not is_nfp else ""
        )

        self._pga_spin.setEnabled(False)
        self._pga_spin.setToolTip("由当前目标谱自动确定")
        self._run_btn.setText(f"生成 {label}")
        self.type_changed.emit(index)

    def _on_duration_changed(self, value):
        """持时改变时自动计算 n = round(持时 / dt)"""
        dt = self._dt_spin.value()
        if dt > 0:
            n = int(round(value / dt))
            # 约束到合理范围
            n = max(256, min(65536, n))
            self._npts_spin.setValue(n)

    def _on_dt_changed(self, value):
        """dt 改变时保持持时不变，重新计算 n"""
        duration = self._dur_spin.value()
        if value > 0:
            n = int(round(duration / value))
            n = max(256, min(65536, n))
            self._npts_spin.setValue(n)

    # ── 公共方法 ──

    def get_params(self):
        """返回当前参数字典"""
        # 算法映射：时域法=1，频域法=0
        fm_map = {"时域法": 1, "频域法": 0}
        fm = fm_map.get(self._algo_combo.currentText(), 1)
        return {
            'type_label': self._type_combo.currentText(),
            'type_code': GM_TYPE_CODES[self._type_combo.currentText()],
            'Mw': self._mw_spin.value(),
            'R': self._r_spin.value(),
            'Vs30': self._vs30_spin.value(),
            'fault_type': self._fault_combo.currentText(),
            'n': self._npts_spin.value(),
            'dt': self._dt_spin.value(),
            'pga': self._pga_spin.value(),
            'zeta': self._zeta_spin.value(),
            'tol': self._tol_spin.value(),
            'max_iter': self._maxiter_spin.value(),
            'n_trials': self._trials_spin.value(),
            'fm': fm,
            'duration': self._dur_spin.value(),
        }

    def set_type(self, index):
        """切换地震动类型（会触发 UI 更新）"""
        self._type_combo.setCurrentIndex(index)

    def set_target_pga(self, pga: float):
        """同步显示由目标谱确定的 PGA。"""
        self._pga_spin.setValue(float(pga))

    def set_target_info(self, text: str):
        """更新目标谱信息标签"""
        self._target_info_label.setText(text)

    def set_code_spectrum_set(self, is_set: bool):
        """标记规范谱是否已设置，控制生成按钮提示"""
        self._code_spectrum_set = is_set
        if not is_set:
            self._target_info_label.setText("尚未设置")
        else:
            # 如果已有文本则保留
            if getattr(self, '_target_info_label', None) and self._target_info_label.text() == "尚未设置":
                self._target_info_label.setText("已设置")

    def reset_defaults(self):
        """重置为默认值"""
        self._type_combo.setCurrentIndex(0)
        self._mw_spin.setValue(7.0)
        self._r_spin.setValue(10.0)
        self._vs30_spin.setValue(760.0)
        self._fault_combo.setCurrentIndex(0)
        self._dur_spin.setValue(40.0)
        self._dt_spin.setValue(0.02)
        # 持时 40s / dt 0.02 = 2000
        self._npts_spin.setValue(2000)
        self._pga_spin.setValue(0.20)
        self._zeta_spin.setValue(0.05)
        self._tol_spin.setValue(0.05)
        self._maxiter_spin.setValue(1)
        self._trials_spin.setValue(1)
        self._algo_combo.setCurrentIndex(0)
        self._target_info_label.setText("尚未设置")
