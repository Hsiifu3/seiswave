"""
规范谱侧边栏

精简版规范谱设置，嵌入左侧 DockWidget。
参数变化实时发射 spectrum_changed 信号。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel,
    QComboBox, QDoubleSpinBox, QCheckBox, QFormLayout, QPushButton,
    QScrollArea, QFileDialog,
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
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # 用 ScrollArea 包裹，防止窗口太小时参数被截断
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 规范选择
        code_group = QGroupBox("规范")
        code_form = QFormLayout(code_group)
        code_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        code_form.setLabelAlignment(Qt.AlignRight)
        self._code_combo = QComboBox()
        self._code_combo.addItems(["GB 50011-2010", "Eurocode 8", "ASCE 7"])
        self._code_combo.setFixedWidth(140)
        code_form.addRow("规范:", self._code_combo)
        layout.addWidget(code_group)

        # GB 50011
        self._gb_group = QGroupBox("GB 50011 参数")
        gb_form = QFormLayout(self._gb_group)
        gb_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        gb_form.setLabelAlignment(Qt.AlignRight)

        self._intensity_combo = QComboBox()
        self._intensity_combo.addItems(["6度", "7度", "7度半", "8度", "8度半", "9度"])
        self._intensity_combo.setFixedWidth(140)
        gb_form.addRow("设防烈度:", self._intensity_combo)

        self._group_combo = QComboBox()
        self._group_combo.addItems(["第一组", "第二组", "第三组"])
        self._group_combo.setFixedWidth(140)
        gb_form.addRow("地震分组:", self._group_combo)

        self._site_combo = QComboBox()
        self._site_combo.addItems(["I₀类", "I₁类", "II类", "III类", "IV类"])
        self._site_combo.setFixedWidth(140)
        gb_form.addRow("场地类别:", self._site_combo)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["多遇地震", "设防地震", "罕遇地震"])
        self._level_combo.setFixedWidth(140)
        gb_form.addRow("地震水准:", self._level_combo)

        layout.addWidget(self._gb_group)

        # EC8
        self._ec8_group = QGroupBox("Eurocode 8 参数")
        ec8_form = QFormLayout(self._ec8_group)
        ec8_form.setLabelAlignment(Qt.AlignRight)
        ec8_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._ec8_ag_spin = QDoubleSpinBox()
        self._ec8_ag_spin.setRange(0.01, 2.0)
        self._ec8_ag_spin.setSingleStep(0.05)
        self._ec8_ag_spin.setValue(0.25)
        self._ec8_ag_spin.setDecimals(2)
        self._ec8_ag_spin.setFixedWidth(100)
        ec8_form.addRow("ag (g):", self._ec8_ag_spin)

        self._ec8_soil_combo = QComboBox()
        self._ec8_soil_combo.addItems(["A", "B", "C", "D", "E"])
        self._ec8_soil_combo.setFixedWidth(100)
        self._ec8_soil_combo.setCurrentIndex(1)
        ec8_form.addRow("场地类别:", self._ec8_soil_combo)

        self._ec8_type_combo = QComboBox()
        self._ec8_type_combo.addItems(["Type 1", "Type 2"])
        self._ec8_type_combo.setFixedWidth(100)
        ec8_form.addRow("谱类型:", self._ec8_type_combo)

        self._ec8_group.setVisible(False)
        layout.addWidget(self._ec8_group)

        # ASCE 7
        self._asce_group = QGroupBox("ASCE 7 参数")
        asce_form = QFormLayout(self._asce_group)
        asce_form.setLabelAlignment(Qt.AlignRight)
        asce_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._asce_sds_spin = QDoubleSpinBox()
        self._asce_sds_spin.setRange(0.01, 3.0)
        self._asce_sds_spin.setSingleStep(0.1)
        self._asce_sds_spin.setValue(1.0)
        self._asce_sds_spin.setDecimals(2)
        self._asce_sds_spin.setFixedWidth(100)
        asce_form.addRow("SDS (g):", self._asce_sds_spin)

        self._asce_sd1_spin = QDoubleSpinBox()
        self._asce_sd1_spin.setRange(0.01, 2.0)
        self._asce_sd1_spin.setSingleStep(0.1)
        self._asce_sd1_spin.setValue(0.5)
        self._asce_sd1_spin.setDecimals(2)
        self._asce_sd1_spin.setFixedWidth(100)
        asce_form.addRow("SD1 (g):", self._asce_sd1_spin)

        self._asce_tl_spin = QDoubleSpinBox()
        self._asce_tl_spin.setRange(4.0, 16.0)
        self._asce_tl_spin.setSingleStep(1.0)
        self._asce_tl_spin.setValue(8.0)
        self._asce_tl_spin.setDecimals(1)
        self._asce_tl_spin.setFixedWidth(100)
        asce_form.addRow("TL (s):", self._asce_tl_spin)

        self._asce_group.setVisible(False)
        layout.addWidget(self._asce_group)

        # 阻尼与隔震
        damp_group = QGroupBox("阻尼与隔震")
        damp_form = QFormLayout(damp_group)
        damp_form.setLabelAlignment(Qt.AlignRight)
        damp_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._zeta_spin = QDoubleSpinBox()
        self._zeta_spin.setRange(0.01, 0.30)
        self._zeta_spin.setSingleStep(0.01)
        self._zeta_spin.setValue(0.05)
        self._zeta_spin.setDecimals(2)
        self._zeta_spin.setFixedWidth(100)
        damp_form.addRow("阻尼比 ζ:", self._zeta_spin)

        self._isolation_check = QCheckBox("隔震结构")
        damp_form.addRow("", self._isolation_check)

        layout.addWidget(damp_group)

        # 计算参数摘要
        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self._info_label)

        # 导出规范谱
        self._export_btn = QPushButton("导出规范谱 CSV")
        self._export_btn.setProperty("secondary", True)
        self._export_btn.clicked.connect(self._export_spectrum)
        layout.addWidget(self._export_btn)

        layout.addStretch()

        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _connect_signals(self):
        self._code_combo.currentIndexChanged.connect(self._on_code_changed)
        self._intensity_combo.currentIndexChanged.connect(self._update_spectrum)
        self._group_combo.currentIndexChanged.connect(self._update_spectrum)
        self._site_combo.currentIndexChanged.connect(self._update_spectrum)
        self._level_combo.currentIndexChanged.connect(self._update_spectrum)
        self._zeta_spin.valueChanged.connect(self._update_spectrum)
        self._isolation_check.stateChanged.connect(self._update_spectrum)
        self._ec8_ag_spin.valueChanged.connect(self._update_spectrum)
        self._ec8_soil_combo.currentIndexChanged.connect(self._update_spectrum)
        self._ec8_type_combo.currentIndexChanged.connect(self._update_spectrum)
        self._asce_sds_spin.valueChanged.connect(self._update_spectrum)
        self._asce_sd1_spin.valueChanged.connect(self._update_spectrum)
        self._asce_tl_spin.valueChanged.connect(self._update_spectrum)

    def _on_code_changed(self, index):
        self._gb_group.setVisible(index == 0)
        self._ec8_group.setVisible(index == 1)
        self._asce_group.setVisible(index == 2)
        self._update_spectrum()

    def _get_gb_params(self):
        intensity_map = {0: 6, 1: 7, 2: 7.5, 3: 8, 4: 8.5, 5: 9}
        site_map = {0: "I0", 1: "I1", 2: "II", 3: "III", 4: "IV"}
        level_map = {0: "frequent", 1: "basic", 2: "rare"}
        return {
            'intensity': intensity_map[self._intensity_combo.currentIndex()],
            'group': self._group_combo.currentIndex() + 1,
            'site_class': site_map[self._site_combo.currentIndex()],
            'level': level_map[self._level_combo.currentIndex()],
            'zeta': self._zeta_spin.value(),
            'isolation': self._isolation_check.isChecked(),
        }

    def _update_spectrum(self, *args):
        code_index = self._code_combo.currentIndex()
        zeta = self._zeta_spin.value()

        try:
            if code_index == 0:
                params = self._get_gb_params()
                code_params = CodeSpectrum.get_params(
                    params['intensity'], params['group'],
                    params['site_class'], params['level'],
                )
                sa = CodeSpectrum.gb50011(
                    self._periods, code_params['Tg'], code_params['alpha_max'],
                    zeta=zeta, isolation=params['isolation'],
                )
                mode = "隔震" if params['isolation'] else "抗震"
                self._info_label.setText(
                    f"Tg = {code_params['Tg']:.2f}s  |  "
                    f"αmax = {code_params['alpha_max']:.3f}\n"
                    f"ζ = {zeta:.2f}  |  {mode}"
                )

            elif code_index == 1:
                ag = self._ec8_ag_spin.value()
                soil = self._ec8_soil_combo.currentText()
                stype = self._ec8_type_combo.currentIndex() + 1
                sa = CodeSpectrum.eurocode8(
                    self._periods, ag, soil_type=soil,
                    spectrum_type=stype, zeta=zeta,
                )
                self._info_label.setText(
                    f"ag = {ag:.2f}g  |  {soil}类  |  Type {stype}\n"
                    f"ζ = {zeta:.2f}"
                )

            elif code_index == 2:
                sds = self._asce_sds_spin.value()
                sd1 = self._asce_sd1_spin.value()
                tl = self._asce_tl_spin.value()
                sa = CodeSpectrum.asce7(self._periods, sds, sd1, tl=tl)
                self._info_label.setText(
                    f"SDS = {sds:.2f}g  |  SD1 = {sd1:.2f}g\n"
                    f"TL = {tl:.1f}s"
                )
            else:
                return

            self._current_sa = sa
            self.spectrum_changed.emit(self._periods, sa)

        except (KeyError, ValueError) as e:
            self._info_label.setText(f"参数错误: {e}")

    def trigger_update(self):
        """外部调用，强制触发一次规范谱计算"""
        self._update_spectrum()

    def get_spectrum(self):
        """获取当前规范谱"""
        return self._periods, self._current_sa

    def get_params(self):
        return self._get_gb_params()

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
