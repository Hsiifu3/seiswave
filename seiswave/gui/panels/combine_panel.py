"""
组合输出面板

天然波 + 人工波汇总、模式选择、谱对比、校核、一键导出。
"""

import os
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QFormLayout, QPushButton, QFileDialog, QCheckBox,
    QLineEdit, QMessageBox, QSplitter, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core.combiner import Combiner
from seiswave.core.selector import SelectionResult
from seiswave.core.peer_db import PeerDatabase
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot
from seiswave.gui.styles import get_mpl_colors


class CombinePanel(QWidget):
    """组合输出面板"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._results = []          # list[SelectionResult]
        self._database = None       # PeerDatabase
        self._generated_waves = []  # list[EQSignal]
        self._code_periods = None
        self._code_sa = None
        self._combiner = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 左侧控制面板
        left = QWidget()
        left.setMinimumWidth(340)
        left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 组合模式
        mode_group = QGroupBox("组合模式")
        mode_form = QFormLayout(mode_group)
        mode_form.setLabelAlignment(Qt.AlignRight)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["7 条模式 (5天然+2人工)", "3 条模式"])
        mode_form.addRow("模式:", self._mode_combo)
        left_layout.addWidget(mode_group)
        # 波形汇总（仅数量统计；详细列表见下方「汇总」面板，避免重复表格）
        table_group = QGroupBox("波形汇总")
        table_layout = QVBoxLayout(table_group)
        self._count_label = QLabel("天然波: 0  人工波: 0  合计: 0")
        table_layout.addWidget(self._count_label)
        left_layout.addWidget(table_group)

        # 输出目录
        dir_group = QGroupBox("输出目录")
        dir_layout = QHBoxLayout(dir_group)
        dir_layout.setSpacing(4)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择输出目录...")
        self._dir_edit.setReadOnly(True)
        dir_layout.addWidget(self._dir_edit, 1)
        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.setProperty("secondary", True)
        self._browse_btn.clicked.connect(self._browse_output)
        dir_layout.addWidget(self._browse_btn)
        left_layout.addWidget(dir_group)

        # 导出选项
        fmt_group = QGroupBox("导出选项")
        fmt_form = QFormLayout(fmt_group)
        fmt_form.setLabelAlignment(Qt.AlignRight)
        self._wave_fmt_combo = QComboBox()
        self._wave_fmt_combo.addItems(["AT2 格式", "TXT 格式", "两种都导出"])
        fmt_form.addRow("波形格式:", self._wave_fmt_combo)
        self._html_check = QCheckBox("生成 HTML 报告")
        self._html_check.setChecked(True)
        fmt_form.addRow(self._html_check)
        left_layout.addWidget(fmt_group)

        # 导出按钮
        self._export_btn = QPushButton("一键导出（波形+报告）")
        self._export_btn.clicked.connect(self._do_export)
        left_layout.addWidget(self._export_btn)

        # 校核按钮
        self._validate_btn = QPushButton("底部剪力校核")
        self._validate_btn.setProperty("secondary", True)
        self._validate_btn.clicked.connect(self._do_validate)
        left_layout.addWidget(self._validate_btn)

        # 校核结果
        self._validate_label = QLabel("")
        self._validate_label.setWordWrap(True)
        left_layout.addWidget(self._validate_label)

        left_layout.addStretch()
        layout.addWidget(left)
        # 右侧谱对比图
        self._spec_plot = SpectrumPlot(dark=self._dark, log_x=False,
                                       show_toolbar=False)
        layout.addWidget(self._spec_plot, 1)

    # ──────────── 外部接口 ────────────

    def set_code_spectrum(self, periods, sa):
        self._code_periods = periods
        self._code_sa = sa
        self._refresh_plot()

    def set_results(self, results, database=None):
        """设置天然波选波结果"""
        self._results = results
        if database:
            self._database = database
        self._refresh_table()
        self._refresh_plot()

    def add_generated_wave(self, signal):
        """添加人工波"""
        self._generated_waves.append(signal)
        self._refresh_table()
        self._refresh_plot()

    def _browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self._dir_edit.setText(dir_path)

    # ──────────── 表格刷新 ────────────

    def _refresh_table(self):
        n_nat = len(self._results)
        n_art = len(self._generated_waves)
        self._count_label.setText(
            f"天然波: {n_nat}  人工波: {n_art}  合计: {n_nat + n_art}")
    # ──────────── 谱对比图 ────────────

    def _refresh_plot(self):
        """刷新平均谱/包络谱 vs 目标谱对比图"""
        self._spec_plot.clear()
        if self._code_periods is None or self._code_sa is None:
            return

        periods = self._code_periods
        colors = get_mpl_colors(self._dark)
        palette = colors['palette']

        # 目标谱 + 包络
        self._spec_plot.plot_code_spectrum(periods, self._code_sa,
                                           label="目标谱")
        self._spec_plot.plot_envelope(periods, self._code_sa)

        # 收集所有 h1 反应谱
        sa_list = []
        labels = []

        # 人工波反应谱
        from seiswave.core import Spectra
        for i, sig in enumerate(self._generated_waves):
            spec = Spectra.compute(sig.acc, sig.dt, periods, 0.05)
            sa_list.append(spec.sa)
            labels.append(sig.name or f"人工波_{i+1}")

        # 绘制各条谱
        for i, (sa, lbl) in enumerate(zip(sa_list, labels)):
            self._spec_plot.ax.plot(
                periods, sa, label=lbl,
                color=palette[i % len(palette)],
                linewidth=1.2, alpha=0.7)

        # 均值谱
        if len(sa_list) > 1:
            mean_sa = np.mean(sa_list, axis=0)
            self._spec_plot.ax.plot(
                periods, mean_sa, label="均值谱",
                color=colors['fg'], linewidth=2.0, linestyle='-.')

        self._spec_plot.ax.legend(fontsize=8, framealpha=0.8,
                                   loc='upper right')
        self._spec_plot.ax.set_title("组合谱对比", fontsize=11)
        self._spec_plot.refresh()

    # ──────────── 校核 ────────────

    def _do_validate(self):
        if self._code_sa is None:
            QMessageBox.warning(self, "警告", "请先设置目标谱")
            return
        if not self._results and not self._generated_waves:
            QMessageBox.warning(self, "警告", "没有可校核的波形")
            return

        combiner = self._build_combiner()
        if combiner is None:
            return

        pga = float(np.max(self._code_sa))
        result = combiner.validate(
            pga, self._code_sa, self._code_periods)

        lines = []
        status = "通过" if result.passed else "不通过"
        lines.append(f"校核结果: {status}")
        lines.append(f"组数: {result.n_groups}/{result.n_required}")
        lines.append(f"平均谱校核: {'通过' if result.mean_check else '不通过'}")
        if result.mean_ratios is not None:
            lines.append(
                f"平均谱最小比值: {float(np.min(result.mean_ratios)):.3f}")
        for name, ratio_range, ok in result.individual_checks:
            tag = "OK" if ok else "NG"
            lines.append(
                f"  {name}: [{ratio_range[0]:.2f}, "
                f"{ratio_range[1]:.2f}] {tag}")
        for msg in result.messages:
            lines.append(f"  {msg}")

        self._validate_label.setText("\n".join(lines))
    # ──────────── 导出 ────────────

    def _build_combiner(self):
        """构建 Combiner 对象"""
        out_dir = self._dir_edit.text()
        combiner = Combiner(output_dir=out_dir if out_dir else None)

        if self._results and self._database:
            for r in self._results:
                combiner.add_natural(r, self._database)

        for i, sig in enumerate(self._generated_waves):
            combiner.add_artificial(h1=sig, index=i)

        return combiner

    def _do_export(self):
        out_dir = self._dir_edit.text()
        if not out_dir:
            QMessageBox.warning(self, "警告", "请先选择输出目录")
            return
        if not self._results and not self._generated_waves:
            QMessageBox.warning(self, "警告", "没有可导出的数据")
            return

        try:
            combiner = self._build_combiner()

            fmt_map = {0: 'at2', 1: 'txt', 2: 'both'}
            fmt = fmt_map[self._wave_fmt_combo.currentIndex()]
            combiner.export(fmt=fmt)

            report_path = None
            if (self._html_check.isChecked()
                    and self._code_sa is not None):
                report_path = combiner.generate_html_report(
                    self._code_sa, self._code_periods)

            self._combiner = combiner

            msg = f"已导出 {len(combiner.groups)} 组地震波到:\n{out_dir}"
            if report_path:
                msg += f"\n报告: {os.path.basename(report_path)}"
            QMessageBox.information(self, "完成", msg)

        except Exception as e:
            QMessageBox.critical(self, "导出错误", str(e))

    def set_dark(self, dark: bool):
        self._dark = dark
        self._spec_plot.set_dark(dark)
