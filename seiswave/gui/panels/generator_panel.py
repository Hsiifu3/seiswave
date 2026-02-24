"""
人工波生成面板

目标谱选择、参数设置、多 trial 自动取最优、迭代进度实时显示、收敛谱对比。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QFormLayout, QPushButton, QComboBox,
    QMessageBox, QSplitter, QSizePolicy, QProgressBar,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import WaveGenerator, Spectra
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot
from seiswave.gui.widgets.plot_widget import PlotWidget
from seiswave.gui.workers import MultiTrialGeneratorWorker
from seiswave.gui.styles import get_mpl_colors


class GeneratorPanel(QWidget):
    """人工波生成面板（多 trial + 实时进度 + 收敛谱对比）"""

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
        param_widget.setMinimumWidth(290)
        param_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # 目标谱
        target_group = QGroupBox("目标谱")
        target_form = QFormLayout(target_group)
        target_form.setLabelAlignment(Qt.AlignRight)
        target_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self._target_combo = QComboBox()
        self._target_combo.addItems(["当前规范谱"])
        self._target_combo.setEnabled(False)
        target_form.addRow("目标谱来源:", self._target_combo)
        param_layout.addWidget(target_group)
        # 生成参数
        gen_group = QGroupBox("生成参数")
        gen_form = QFormLayout(gen_group)
        gen_form.setLabelAlignment(Qt.AlignRight)
        gen_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._npts_spin = QSpinBox()
        self._npts_spin.setRange(1024, 32768)
        self._npts_spin.setSingleStep(1024)
        self._npts_spin.setValue(4096)
        self._npts_spin.setFixedWidth(120)
        gen_form.addRow("数据点数:", self._npts_spin)

        self._dt_spin = QDoubleSpinBox()
        self._dt_spin.setRange(0.001, 0.1)
        self._dt_spin.setSingleStep(0.005)
        self._dt_spin.setValue(0.02)
        self._dt_spin.setDecimals(3)
        self._dt_spin.setFixedWidth(120)
        gen_form.addRow("时间步长 Δt (s):", self._dt_spin)

        self._pga_spin = QDoubleSpinBox()
        self._pga_spin.setRange(0.01, 5.0)
        self._pga_spin.setSingleStep(0.05)
        self._pga_spin.setValue(0.20)
        self._pga_spin.setDecimals(3)
        self._pga_spin.setFixedWidth(120)
        gen_form.addRow("目标 PGA (g):", self._pga_spin)

        self._zeta_spin = QDoubleSpinBox()
        self._zeta_spin.setRange(0.01, 0.30)
        self._zeta_spin.setSingleStep(0.01)
        self._zeta_spin.setValue(0.05)
        self._zeta_spin.setDecimals(2)
        self._zeta_spin.setFixedWidth(120)
        gen_form.addRow("阻尼比 ζ:", self._zeta_spin)

        param_layout.addWidget(gen_group)

        # 迭代控制
        iter_group = QGroupBox("迭代控制")
        iter_form = QFormLayout(iter_group)
        iter_form.setLabelAlignment(Qt.AlignRight)
        iter_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.01, 0.20)
        self._tol_spin.setSingleStep(0.01)
        self._tol_spin.setValue(0.05)
        self._tol_spin.setDecimals(2)
        self._tol_spin.setFixedWidth(120)
        iter_form.addRow("收敛容限:", self._tol_spin)

        self._maxiter_spin = QSpinBox()
        self._maxiter_spin.setRange(10, 200)
        self._maxiter_spin.setSingleStep(10)
        self._maxiter_spin.setValue(50)
        self._maxiter_spin.setFixedWidth(120)
        iter_form.addRow("最大迭代次数:", self._maxiter_spin)

        self._trials_spin = QSpinBox()
        self._trials_spin.setRange(1, 10)
        self._trials_spin.setSingleStep(1)
        self._trials_spin.setValue(3)
        self._trials_spin.setFixedWidth(120)
        iter_form.addRow("Trial 数量:", self._trials_spin)

        param_layout.addWidget(iter_group)
        # 执行按钮
        self._run_btn = QPushButton("生成人工波")
        self._run_btn.clicked.connect(self._run_generation)
        param_layout.addWidget(self._run_btn)

        # 实时进度区
        progress_group = QGroupBox("迭代进度")
        progress_layout = QVBoxLayout(progress_group)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)
        self._progress_label = QLabel("等待生成...")
        self._progress_label.setWordWrap(True)
        progress_layout.addWidget(self._progress_label)
        param_layout.addWidget(progress_group)

        # 结果信息
        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        param_layout.addWidget(self._info_label)

        param_layout.addStretch()
        layout.addWidget(param_widget)

        # 右侧绘图区（上下分割）
        right_splitter = QSplitter(Qt.Vertical)

        self._spec_plot = SpectrumPlot(dark=self._dark, log_x=False,
                                       show_toolbar=False)
        right_splitter.addWidget(self._spec_plot)

        self._time_plot = PlotWidget(dark=self._dark, show_toolbar=False)
        right_splitter.addWidget(self._time_plot)

        right_splitter.setSizes([400, 300])
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        layout.addWidget(right_splitter, 1)
    def set_code_spectrum(self, periods, sa):
        """设置规范谱作为目标谱"""
        self._code_periods = periods
        self._code_sa = sa
        self._spec_plot.clear()
        self._spec_plot.plot_code_spectrum(periods, sa, label="目标谱")
        self._spec_plot.ax.set_title("目标反应谱", fontsize=11)
        self._spec_plot.refresh()

    def _run_generation(self):
        """执行多 trial 人工波生成"""
        if self._code_sa is None:
            QMessageBox.warning(self, "警告", "请先设置目标谱（在规范谱面板中设置）")
            return

        self._run_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_label.setText("正在生成...")
        self._info_label.setText("")

        self._worker = MultiTrialGeneratorWorker(
            self._code_sa, self._code_periods,
            n=self._npts_spin.value(),
            dt=self._dt_spin.value(),
            zeta=self._zeta_spin.value(),
            pga=self._pga_spin.value(),
            tol=self._tol_spin.value(),
            max_iter=self._maxiter_spin.value(),
            n_trials=self._trials_spin.value(),
            parent=self,
        )
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.finished.connect(self._on_generation_done)
        self._worker.signals.error.connect(self._on_generation_error)
        self._worker.start()

    def _on_progress(self, pct, text):
        """实时更新进度条和迭代数值"""
        self._progress_bar.setValue(pct)
        self._progress_label.setText(text)
    def _on_generation_done(self, result):
        """多 trial 完成：result = {'best': EQSignal, 'all_results': [...], 'best_index': int}"""
        self._run_btn.setEnabled(True)
        self._progress_bar.setValue(100)

        best = result['best']
        all_results = result['all_results']
        best_idx = result['best_index']
        self._generated = best

        # 先发射信号
        self.wave_generated.emit(best)

        try:
            colors = get_mpl_colors(self._dark)
            palette = colors['palette']

            # 计算所有 trial 的反应谱和误差
            trial_spectra = []
            trial_errors = []
            for sig in all_results:
                spec = Spectra.compute(sig.acc, sig.dt,
                                       self._code_periods, 0.05)
                fit = WaveGenerator.fit_error(spec.sa, self._code_sa)
                trial_spectra.append(spec.sa)
                trial_errors.append(fit)

            best_fit = trial_errors[best_idx]
            n_trials = len(all_results)

            info_lines = [
                f"最优: Trial {best_idx+1}/{n_trials}",
                f"PGA = {best.pga:.4f} g",
                f"持时 = {best.duration:.2f} s",
                f"最大偏差 = {best_fit['max_error']:.1%}",
                f"均方根偏差 = {best_fit['mean_error']:.1%}",
            ]
            self._info_label.setText("\n".join(info_lines))
            self._progress_label.setText(
                f"完成: {n_trials} trials, 最优 Trial {best_idx+1}")

            # 绘制反应谱对比（目标谱 + 各 trial + 最优高亮）
            self._spec_plot.clear()
            self._spec_plot.plot_code_spectrum(
                self._code_periods, self._code_sa, label="目标谱")
            for i, sa in enumerate(trial_spectra):
                if i == best_idx:
                    continue
                self._spec_plot.ax.plot(
                    self._code_periods, sa,
                    color=palette[i % len(palette)],
                    linewidth=1.0, alpha=0.4,
                    label=f"Trial {i+1}")
            # 最优 trial 高亮
            self._spec_plot.ax.plot(
                self._code_periods, trial_spectra[best_idx],
                color=colors['primary'], linewidth=2.2,
                label=f"Trial {best_idx+1} (最优)")
            self._spec_plot.ax.legend(fontsize=8, framealpha=0.8)
            self._spec_plot.ax.set_title("反应谱拟合对比", fontsize=11)
            self._spec_plot.refresh()

            # 绘制最优时程曲线
            self._time_plot.clear()
            ax = self._time_plot.ax
            ax.plot(best.time, best.acc,
                    color=colors['primary'], linewidth=0.6)
            ax.set_xlabel("时间 (s)")
            ax.set_ylabel("加速度 (g)")
            ax.set_title(
                f"人工波 Trial {best_idx+1} (PGA={best.pga:.3f}g)",
                fontsize=11)
            self._time_plot.refresh()
        except Exception as e:
            self._info_label.setText(f"结果处理出错: {e}")

    def _on_generation_error(self, err):
        self._info_label.setText(f"生成出错: {err}")
        self._progress_label.setText("生成失败")
        self._run_btn.setEnabled(True)

    def get_generated(self):
        return self._generated

    def set_dark(self, dark: bool):
        self._dark = dark
        self._spec_plot.set_dark(dark)
        self._time_plot.set_dark(dark)
