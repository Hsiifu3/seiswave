"""
规范谱侧边栏

精简版规范谱设置，嵌入左侧 DockWidget。
支持 GB 50011 / GB 51408 / 自定义谱 三种模式。
参数变化实时发射 spectrum_changed 信号。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel,
    QComboBox, QDoubleSpinBox, QCheckBox, QFormLayout, QPushButton,
    QScrollArea, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QHBoxLayout, QAbstractItemView,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import CodeSpectrum, Spectra


class SpectrumSidebar(QWidget):
    """规范谱参数侧边栏"""

    spectrum_changed = Signal(object, object)  # (periods, sa)

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
        self._current_sa = None
        self._custom_periods = None
        self._custom_sa = None
        self._setup_ui()
        self._connect_signals()

    # ── UI 构建 ──

    def _setup_ui(self):
        # 侧栏最小宽度，避免下拉框/按钮被 dock 裁切
        self.setMinimumWidth(250)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── 规范选择 ──
        code_group = QGroupBox("规范")
        code_form = QFormLayout(code_group)
        code_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        code_form.setLabelAlignment(Qt.AlignRight)
        self._code_combo = QComboBox()
        self._code_combo.addItems(["GB 50011-2010", "GB/T 51408（隔震）", "自定义谱"])
        self._code_combo.setMinimumWidth(160)
        code_form.addRow("规范:", self._code_combo)
        layout.addWidget(code_group)

        # ── GB 50011 参数 ──
        self._gb_group = QGroupBox("GB 50011 参数")
        gb_form = QFormLayout(self._gb_group)
        gb_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        gb_form.setLabelAlignment(Qt.AlignRight)
        self._intensity_combo = QComboBox()
        self._intensity_combo.addItems(["6度", "7度", "7度半", "8度", "8度半", "9度"])
        self._intensity_combo.setMinimumWidth(140)
        gb_form.addRow("设防烈度:", self._intensity_combo)

        self._group_combo = QComboBox()
        self._group_combo.addItems(["第一组", "第二组", "第三组"])
        self._group_combo.setMinimumWidth(140)
        gb_form.addRow("地震分组:", self._group_combo)

        self._site_combo = QComboBox()
        self._site_combo.addItems(["I₀类", "I₁类", "II类", "III类", "IV类"])
        self._site_combo.setMinimumWidth(140)
        gb_form.addRow("场地类别:", self._site_combo)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["多遇地震", "设防地震", "罕遇地震"])
        self._level_combo.setMinimumWidth(140)
        gb_form.addRow("地震水准:", self._level_combo)

        layout.addWidget(self._gb_group)

        # ── 隔震周期（GB 51408 模式下显示）──
        self._iso_group = QGroupBox("隔震周期")
        iso_form = QFormLayout(self._iso_group)
        iso_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        iso_form.setLabelAlignment(Qt.AlignRight)

        self._t_before_spin = QDoubleSpinBox()
        self._t_before_spin.setRange(0.01, 10.0); self._t_before_spin.setValue(1.0)
        self._t_before_spin.setDecimals(2); self._t_before_spin.setMinimumWidth(100)
        iso_form.addRow("隔震前 T (s):", self._t_before_spin)

        self._t_after_spin = QDoubleSpinBox()
        self._t_after_spin.setRange(0.01, 10.0); self._t_after_spin.setValue(3.0)
        self._t_after_spin.setDecimals(2); self._t_after_spin.setMinimumWidth(100)
        iso_form.addRow("隔震后 T (s):", self._t_after_spin)

        self._iso_group.setVisible(False)
        layout.addWidget(self._iso_group)

        # ── 自定义谱 ──
        self._custom_group = QGroupBox("自定义谱数据")
        custom_layout = QVBoxLayout(self._custom_group)

        self._custom_table = QTableWidget(0, 2)
        self._custom_table.setHorizontalHeaderLabels(["周期 T (s)", "Sa (g)"])
        self._custom_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._custom_table.verticalHeader().setVisible(False)
        self._custom_table.setMaximumHeight(180)
        custom_layout.addWidget(self._custom_table)

        btn_row = QHBoxLayout()
        self._add_row_btn = QPushButton("添加行")
        self._add_row_btn.setProperty("secondary", True)
        self._add_row_btn.clicked.connect(self._add_custom_row)
        self._del_row_btn = QPushButton("删除行")
        self._del_row_btn.setProperty("secondary", True)
        self._del_row_btn.clicked.connect(self._del_custom_row)
        self._csv_btn = QPushButton("导入 CSV")
        self._csv_btn.setProperty("secondary", True)
        self._csv_btn.clicked.connect(self._import_csv)
        btn_row.addWidget(self._add_row_btn)
        btn_row.addWidget(self._del_row_btn)
        btn_row.addWidget(self._csv_btn)
        custom_layout.addLayout(btn_row)

        self._custom_group.setVisible(False)
        layout.addWidget(self._custom_group)
        # ── 阻尼比 ──
        damp_group = QGroupBox("阻尼比")
        damp_form = QFormLayout(damp_group)
        damp_form.setLabelAlignment(Qt.AlignRight)
        damp_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._zeta_spin = QDoubleSpinBox()
        self._zeta_spin.setRange(0.01, 0.30)
        self._zeta_spin.setSingleStep(0.01)
        self._zeta_spin.setValue(0.05)
        self._zeta_spin.setDecimals(2)
        self._zeta_spin.setMinimumWidth(100)
        damp_form.addRow("阻尼比 ζ:", self._zeta_spin)

        layout.addWidget(damp_group)

        # ── 计算参数摘要 ──
        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self._info_label)

        # ── 导出规范谱 ──
        self._export_btn = QPushButton("导出规范谱 CSV")
        self._export_btn.setProperty("secondary", True)
        self._export_btn.clicked.connect(self._export_spectrum)
        layout.addWidget(self._export_btn)

        layout.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── 信号连接 ──

    def _connect_signals(self):
        self._code_combo.currentIndexChanged.connect(self._on_code_changed)
        self._intensity_combo.currentIndexChanged.connect(self._update_spectrum)
        self._group_combo.currentIndexChanged.connect(self._update_spectrum)
        self._site_combo.currentIndexChanged.connect(self._update_spectrum)
        self._level_combo.currentIndexChanged.connect(self._update_spectrum)
        self._zeta_spin.valueChanged.connect(self._update_spectrum)
        self._t_before_spin.valueChanged.connect(self._update_spectrum)
        self._t_after_spin.valueChanged.connect(self._update_spectrum)
        self._custom_table.cellChanged.connect(self._on_custom_table_changed)

    def _on_code_changed(self, index):
        self._gb_group.setVisible(index in (0, 1))
        self._iso_group.setVisible(index == 1)
        self._custom_group.setVisible(index == 2)
        self._update_spectrum()

    # ── GB 参数查表 ──

    _INTENSITY_MAP = {0: 6, 1: 7, 2: 7.5, 3: 8, 4: 8.5, 5: 9}
    _SITE_MAP = {0: "I0", 1: "I1", 2: "II", 3: "III", 4: "IV"}
    _LEVEL_MAP = {0: "frequent", 1: "basic", 2: "rare"}

    def _get_gb_params(self):
        return {
            'intensity': self._INTENSITY_MAP[self._intensity_combo.currentIndex()],
            'group': self._group_combo.currentIndex() + 1,
            'site_class': self._SITE_MAP[self._site_combo.currentIndex()],
            'level': self._LEVEL_MAP[self._level_combo.currentIndex()],
            'zeta': self._zeta_spin.value(),
        }
    # ── 规范谱计算 ──

    def _update_spectrum(self, *args):
        code_index = self._code_combo.currentIndex()
        zeta = self._zeta_spin.value()

        try:
            if code_index == 0:  # GB 50011
                params = self._get_gb_params()
                code_params = CodeSpectrum.get_params(
                    params['intensity'], params['group'],
                    params['site_class'], params['level'],
                )
                sa = CodeSpectrum.gb50011(
                    self._periods, code_params['Tg'], code_params['alpha_max'],
                    zeta=zeta, isolation=False,
                )
                self._info_label.setText(
                    f"Tg = {code_params['Tg']:.2f}s  |  "
                    f"αmax = {code_params['alpha_max']:.3f}\n"
                    f"ζ = {zeta:.2f}  |  抗震谱"
                )

            elif code_index == 1:  # GB/T 51408
                params = self._get_gb_params()
                sa = CodeSpectrum.gb51408(
                    self._periods,
                    params['intensity'], params['group'],
                    params['site_class'], params['level'],
                    zeta=zeta,
                )
                t_before = self._t_before_spin.value()
                t_after = self._t_after_spin.value()
                self._info_label.setText(
                    f"GB/T 51408 隔震谱\n"
                    f"隔震前 T = {t_before:.2f}s  |  "
                    f"隔震后 T = {t_after:.2f}s\n"
                    f"ζ = {zeta:.2f}"
                )

            elif code_index == 2:  # 自定义谱
                sa = self._compute_custom_spectrum()
                if sa is None:
                    self._info_label.setText("请输入自定义谱数据或导入 CSV")
                    return
                self._info_label.setText(
                    f"自定义谱  |  {len(self._custom_periods)} 个控制点\n"
                    f"T: {self._custom_periods[0]:.2f} ~ "
                    f"{self._custom_periods[-1]:.2f}s"
                )
            else:
                return

            self._current_sa = sa
            self.spectrum_changed.emit(self._periods, sa)

        except (KeyError, ValueError) as e:
            self._info_label.setText(f"参数错误: {e}")

    # ── 自定义谱相关 ──

    def _compute_custom_spectrum(self):
        """从表格读取自定义谱数据并插值"""
        rows = self._custom_table.rowCount()
        if rows < 2:
            return None
        t_list, sa_list = [], []
        for r in range(rows):
            t_item = self._custom_table.item(r, 0)
            sa_item = self._custom_table.item(r, 1)
            if t_item is None or sa_item is None:
                continue
            try:
                t_list.append(float(t_item.text()))
                sa_list.append(float(sa_item.text()))
            except ValueError:
                continue
        if len(t_list) < 2:
            return None
        self._custom_periods = np.array(t_list)
        self._custom_sa = np.array(sa_list)
        return CodeSpectrum.from_custom(
            self._custom_periods, self._custom_sa, self._periods
        )
    def _add_custom_row(self):
        row = self._custom_table.rowCount()
        self._custom_table.insertRow(row)
        self._custom_table.setItem(row, 0, QTableWidgetItem("0.0"))
        self._custom_table.setItem(row, 1, QTableWidgetItem("0.0"))

    def _del_custom_row(self):
        row = self._custom_table.currentRow()
        if row >= 0:
            self._custom_table.removeRow(row)
            self._update_spectrum()

    def _on_custom_table_changed(self, row, col):
        self._update_spectrum()

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入自定义谱", "",
            "CSV/TXT 文件 (*.csv *.txt);;所有文件 (*)",
        )
        if not path:
            return
        try:
            t_arr, sa_arr = CodeSpectrum.from_csv(path)
        except Exception as e:
            self._info_label.setText(f"导入失败: {e}")
            return
        self._custom_table.blockSignals(True)
        self._custom_table.setRowCount(len(t_arr))
        for i in range(len(t_arr)):
            self._custom_table.setItem(i, 0, QTableWidgetItem(f"{t_arr[i]:.4f}"))
            self._custom_table.setItem(i, 1, QTableWidgetItem(f"{sa_arr[i]:.6f}"))
        self._custom_table.blockSignals(False)
        self._update_spectrum()

    # ── 公共接口 ──

    def trigger_update(self):
        """外部调用，强制触发一次规范谱计算"""
        self._update_spectrum()

    def get_spectrum(self):
        """获取当前规范谱"""
        return self._periods, self._current_sa

    def get_params(self):
        return self._get_gb_params()

    def get_isolation_periods(self):
        """获取隔震前后周期（仅 GB 51408 模式有效）"""
        if self._code_combo.currentIndex() == 1:
            return self._t_before_spin.value(), self._t_after_spin.value()
        return None, None

    def is_isolation_mode(self):
        """是否为隔震模式"""
        return self._code_combo.currentIndex() == 1

    def _export_spectrum(self):
        if self._current_sa is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出规范谱", "code_spectrum.csv", "CSV 文件 (*.csv)",
        )
        if path:
            from seiswave.core import FileIO
            FileIO.write_csv(path, T=self._periods, Sa=self._current_sa)

    def set_dark(self, dark: bool):
        self._dark = dark
        color = "#999" if dark else "#666"
        self._info_label.setStyleSheet(f"color: {color}; font-size: 12px;")
