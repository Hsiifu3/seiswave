"""
人工波生成面板

目标谱选择、参数设置、迭代过程可视化。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QFormLayout, QPushButton, QComboBox,
    QMessageBox,
)
from PySide6.QtCore import Signal

from eqsignalpy.core import WaveGenerator, Spectra
from eqsignalpy.gui.widgets.spectrum_plot import SpectrumPlot
from eqsignalpy.gui.widgets.plot_widget import PlotWidget
from eqsignalpy.gui.widgets.progress_dialog import ProgressDialog
from eqsignalpy.gui.workers import GeneratorWorker
from eqsignalpy.gui.styles import get_mpl_colors


class GeneratorPanel(QWidget):
    """人工波生成面板"""

    wave_generated = Signal(object)  # 生成完成信号 (EQSignal)

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._code_periods = None
        self._code_sa = None
        self._generated = None
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 左侧参数面板
        param_widget = QWidget()
        param_widget.setFixedWidth(320)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # 目标谱
        target_group = QGroupBox("目标谱")
        target_form = QFormLayout(target_group)
        self._target_combo = QComboBox()
        self._target_combo.addItems(["当前规范谱", "自定义谱（CSV）"])
        target_form.addRow("目标谱来源:", self._target_combo)
        param_layout.addWidget(target_group)

        # 生成参数
        gen_group = QGroupBox("生成参数")
        gen_form = QFormLayout(gen_group)

        self._npts_spin = QSpinBox()
        self._npts_spin.setRange(1024, 32768)
        self._npts_spin.setSingleStep(1024)
        self._npts_spin.setValue(4096)
        gen_form.addRow("数据点数:", self._npts_spin)

        self._dt_spin = QDoubleSpinBox()
        self._dt_spin.setRange(0.001, 0.1)
        self._dt_spin.setSingleStep(0.005)
        self._dt_spin.setValue(0.02)
        self._dt_spin.setDecimals(3)
        gen_form.addRow("时间步长 Δt (s):", self._dt_spin)

        self._pga_spin = QDoubleSpinBox()
        self._pga_spin.setRange(0.01, 5.0)
        self._pga_spin.setSingleStep(0.05)
        self._pga_spin.setValue(0.20)
        self._pga_spin.setDecimals(3)
        gen_form.addRow("目标 PGA (g):", self._pga_spin)

        self._zeta_spin = QDoubleSpinBox()
        self._zeta_spin.setRange(0.01, 0.30)
        self._zeta_spin.setSingleStep(0.01)
        self._zeta_spin.setValue(0.05)
        self._zeta_spin.setDecimals(2)
        gen_form.addRow("阻尼比 ζ:", self._zeta_spin)

        param_layout.addWidget(gen_group)

        # 迭代参数
        iter_group = QGroupBox("迭代控制")
        iter_form = QFormLayout(iter_group)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.01, 0.20)
        self._tol_spin.setSingleStep(0.01)
        self._tol_spin.setValue(0.05)
        self._tol_spin.setDecimals(2)
        iter_form.addRow("收敛容限:", self._tol_spin)

        self._maxiter_spin = QSpinBox()
        self._maxiter_spin.setRange(10, 200)
        self._maxiter_spin.setSingleStep(10)
        self._maxiter_spin.setValue(50)
        iter_form.addRow("最大迭代次数:", self._maxiter_spin)

        param_layout.addWidget(iter_group)

        # 执行按钮
        self._run_btn = QPushButton("▶ 生成人工波")
        self._run_btn.clicked.connect(self._run_generation)
        param_layout.addWidget(self._run_btn)

        # 结果信息
        self._info_label = QLabel("等待生成...")
        self._info_label.setWordWrap(True)
        param_layout.addWidget(self._info_label)

        param_layout.addStretch()
        layout.addWidget(param_widget)

        # 右侧绘图区（上下分割）
        from PySide6.QtWidgets import QSplitter
        from PySide6.QtCore import Qt
        right_splitter = QSplitter(Qt.Vertical)

        # 反应谱对比图
        self._spec_plot = SpectrumPlot(dark=self._dark)
        right_splitter.addWidget(self._spec_plot)

        # 时程曲线图
        self._time_plot = PlotWidget(dark=self._dark)
        right_splitter.addWidget(self._time_plot)

        right_splitter.setSizes([400, 300])
        layout.addWidget(right_splitter, 1)

    def set_code_spectrum(self, periods, sa):
        """设置规范谱作为目标谱"""
        self._code_periods = periods
        self._code_sa = sa
        # 预览目标谱
        self._spec_plot.clear()
        self._spec_plot.plot_code_spectrum(periods, sa, label="目标谱")
        self._spec_plot.ax.set_title("目标反应谱", fontsize=11)
        self._spec_plot.refresh()

    def _run_generation(self):
        """执行人工波生成"""
        if self._code_sa is None:
            QMessageBox.warning(self, "警告", "请先设置目标谱（在规范谱面板中设置）")
            return

        periods = self._code_periods
        target = self._code_sa

        progress = ProgressDialog("人工波生成中...", self)

        self._worker = GeneratorWorker(
            target, periods,
            n=self._npts_spin.value(),
            dt=self._dt_spin.value(),
            zeta=self._zeta_spin.value(),
            pga=self._pga_spin.value(),
            tol=self._tol_spin.value(),
            max_iter=self._maxiter_spin.value(),
            parent=self,
        )
        self._worker.signals.progress.connect(progress.update_progress)
        self._worker.signals.finished.connect(
            lambda result: self._on_generation_done(result, progress))
        self._worker.signals.error.connect(
            lambda err: self._on_generation_error(err, progress))

        self._worker.start()
        progress.exec()

        if progress.is_cancelled and self._worker:
            self._worker.cancel()

    def _on_generation_done(self, signal, progress):
        self._generated = signal
        progress.set_finished("生成完成")

        # 计算生成波的反应谱
        spec = Spectra.compute(signal.acc, signal.dt, self._code_periods, 0.05)
        fit = WaveGenerator.fit_error(spec.sa, self._code_sa)

        self._info_label.setText(
            f"PGA = {signal.pga:.4f} g\n"
            f"持时 = {signal.duration:.2f} s\n"
            f"最大偏差 = {fit['max_dev']:.1%}\n"
            f"均方根偏差 = {fit['rms_dev']:.1%}"
        )

        # 绘制反应谱对比
        self._spec_plot.clear()
        self._spec_plot.plot_code_spectrum(self._code_periods, self._code_sa, label="目标谱")
        colors = get_mpl_colors(self._dark)
        self._spec_plot.plot_spectrum(self._code_periods, spec.sa,
                                     label="生成波", color=colors['primary'], linewidth=2.0)
        self._spec_plot.ax.set_title("反应谱拟合对比", fontsize=11)
        self._spec_plot.refresh()

        # 绘制时程曲线
        self._time_plot.clear()
        ax = self._time_plot.ax
        ax.plot(signal.time, signal.acc, color=colors['primary'], linewidth=0.6)
        ax.set_xlabel("时间 (s)")
        ax.set_ylabel("加速度 (g)")
        ax.set_title("生成的人工地震波", fontsize=11)
        self._time_plot.refresh()

        self.wave_generated.emit(signal)

    def _on_generation_error(self, err, progress):
        progress.set_finished(f"生成出错: {err}")

    def get_generated(self):
        return self._generated

    def set_dark(self, dark: bool):
        self._dark = dark
        self._spec_plot.set_dark(dark)
        self._time_plot.set_dark(dark)
