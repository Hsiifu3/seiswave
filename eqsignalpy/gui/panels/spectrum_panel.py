"""
规范谱设置面板

GB 50011 规范选择、烈度、设计地震分组、场地类别、阻尼比、隔震开关。
实时预览规范谱曲线。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QDoubleSpinBox, QCheckBox, QFormLayout, QPushButton,
)
from PySide6.QtCore import Signal

from eqsignalpy.core import CodeSpectrum, Spectra
from eqsignalpy.gui.widgets.spectrum_plot import SpectrumPlot


class SpectrumPanel(QWidget):
    """规范谱设置面板"""

    spectrum_changed = Signal(object, object)  # (periods, sa)

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
        self._current_sa = None
        self._setup_ui()
        self._connect_signals()
        self._update_spectrum()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 左侧参数面板
        param_widget = QWidget()
        param_widget.setFixedWidth(320)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # 规范选择
        code_group = QGroupBox("规范选择")
        code_form = QFormLayout(code_group)
        self._code_combo = QComboBox()
        self._code_combo.addItems(["GB 50011-2010"])
        code_form.addRow("规范:", self._code_combo)
        param_layout.addWidget(code_group)

        # 设防参数
        param_group = QGroupBox("设防参数")
        param_form = QFormLayout(param_group)

        self._intensity_combo = QComboBox()
        self._intensity_combo.addItems(["6度", "7度", "7度半", "8度", "8度半", "9度"])
        param_form.addRow("抗震设防烈度:", self._intensity_combo)

        self._group_combo = QComboBox()
        self._group_combo.addItems(["第一组", "第二组", "第三组"])
        param_form.addRow("设计地震分组:", self._group_combo)

        self._site_combo = QComboBox()
        self._site_combo.addItems(["I₀类", "I₁类", "II类", "III类", "IV类"])
        param_form.addRow("场地类别:", self._site_combo)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["多遇地震", "设防地震", "罕遇地震"])
        param_form.addRow("地震水准:", self._level_combo)

        param_layout.addWidget(param_group)

        # 阻尼与隔震
        damp_group = QGroupBox("阻尼与隔震")
        damp_form = QFormLayout(damp_group)

        self._zeta_spin = QDoubleSpinBox()
        self._zeta_spin.setRange(0.01, 0.30)
        self._zeta_spin.setSingleStep(0.01)
        self._zeta_spin.setValue(0.05)
        self._zeta_spin.setDecimals(2)
        damp_form.addRow("阻尼比 ζ:", self._zeta_spin)

        self._isolation_check = QCheckBox("隔震结构")
        damp_form.addRow(self._isolation_check)

        param_layout.addWidget(damp_group)

        # 参数信息显示
        info_group = QGroupBox("计算参数")
        info_layout = QVBoxLayout(info_group)
        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        param_layout.addWidget(info_group)

        param_layout.addStretch()

        # 导出按钮
        self._export_btn = QPushButton("导出规范谱数据")
        self._export_btn.setProperty("secondary", True)
        self._export_btn.clicked.connect(self._export_spectrum)
        param_layout.addWidget(self._export_btn)

        layout.addWidget(param_widget)

        # 右侧绘图区
        self._plot = SpectrumPlot(dark=self._dark)
        layout.addWidget(self._plot, 1)

    def _connect_signals(self):
        self._intensity_combo.currentIndexChanged.connect(self._update_spectrum)
        self._group_combo.currentIndexChanged.connect(self._update_spectrum)
        self._site_combo.currentIndexChanged.connect(self._update_spectrum)
        self._level_combo.currentIndexChanged.connect(self._update_spectrum)
        self._zeta_spin.valueChanged.connect(self._update_spectrum)
        self._isolation_check.stateChanged.connect(self._update_spectrum)

    def _get_params(self):
        """从 UI 获取当前参数"""
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

    def _update_spectrum(self):
        """更新规范谱曲线"""
        params = self._get_params()
        try:
            code_params = CodeSpectrum.get_params(
                params['intensity'], params['group'],
                params['site_class'], params['level'],
            )
            sa = CodeSpectrum.gb50011(
                self._periods, code_params['Tg'], code_params['alpha_max'],
                zeta=params['zeta'], isolation=params['isolation'],
            )
            self._current_sa = sa

            # 更新信息标签
            mode = "隔震谱" if params['isolation'] else "抗震谱"
            self._info_label.setText(
                f"特征周期 Tg = {code_params['Tg']:.2f} s\n"
                f"αmax = {code_params['alpha_max']:.3f}\n"
                f"阻尼比 ζ = {params['zeta']:.2f}\n"
                f"谱类型: {mode}"
            )

            # 更新绘图
            self._plot.clear()
            self._plot.plot_code_spectrum(self._periods, sa, label=f"GB 50011 {mode}")
            self._plot.ax.set_title(
                f"GB 50011 设计反应谱 ({params['intensity']}度, "
                f"第{params['group']}组, {params['site_class']}类场地)",
                fontsize=12,
            )
            self._plot.refresh()

            self.spectrum_changed.emit(self._periods, sa)

        except (KeyError, ValueError) as e:
            self._info_label.setText(f"参数错误: {e}")

    def _export_spectrum(self):
        """导出规范谱数据到 CSV"""
        if self._current_sa is None:
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出规范谱", "code_spectrum.csv", "CSV 文件 (*.csv)",
        )
        if path:
            from eqsignalpy.core import FileIO
            FileIO.write_csv(path, T=self._periods, Sa=self._current_sa)

    def get_spectrum(self):
        """获取当前规范谱数据"""
        return self._periods, self._current_sa

    def get_params(self):
        """获取当前设防参数"""
        return self._get_params()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._plot.set_dark(dark)
        self._update_spectrum()
