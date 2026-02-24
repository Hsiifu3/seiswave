"""
导出与报告面板

组合天然波 + 人工波，导出时程数据、反应谱对比图、选波报告。
"""

import os
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QFormLayout, QPushButton, QFileDialog, QCheckBox,
    QLineEdit, QMessageBox, QTextEdit, QSpinBox,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core.selector import SelectionResult
from seiswave.core.combiner import Combiner
from seiswave.core.peer_db import PeerDatabase
from seiswave.gui.styles import get_mpl_colors


class ResultPanel(QWidget):
    """导出与报告面板"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._results: list[SelectionResult] = []
        self._database: PeerDatabase = None
        self._code_periods = None
        self._code_sa = None
        self._generated_waves = []
        self._combiner = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 左侧导出选项
        param_widget = QWidget()
        param_widget.setFixedWidth(360)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

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
        self._browse_btn.setFixedHeight(self._dir_edit.sizeHint().height())
        self._browse_btn.clicked.connect(self._browse_output)
        dir_layout.addWidget(self._browse_btn)
        param_layout.addWidget(dir_group)

        # 组合设置
        combo_group = QGroupBox("波组合设置")
        combo_form = QFormLayout(combo_group)
        combo_form.setLabelAlignment(Qt.AlignRight)
        combo_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._n_natural_label = QLabel("0")
        combo_form.addRow("已选天然波:", self._n_natural_label)

        self._n_art_spin = QSpinBox()
        self._n_art_spin.setRange(0, 5)
        self._n_art_spin.setValue(2)
        combo_form.addRow("人工波数量:", self._n_art_spin)

        self._total_label = QLabel("共 0 组")
        combo_form.addRow("总计:", self._total_label)

        param_layout.addWidget(combo_group)

        # 导出格式
        fmt_group = QGroupBox("导出选项")
        fmt_form = QFormLayout(fmt_group)
        fmt_form.setLabelAlignment(Qt.AlignRight)

        self._wave_fmt_combo = QComboBox()
        self._wave_fmt_combo.addItems(["AT2 格式", "TXT 格式", "两种都导出"])
        fmt_form.addRow("波形格式:", self._wave_fmt_combo)

        self._export_spec_check = QCheckBox("导出反应谱 CSV")
        self._export_spec_check.setChecked(True)
        fmt_form.addRow(self._export_spec_check)

        self._export_img_check = QCheckBox("导出对比图 PNG")
        self._export_img_check.setChecked(True)
        fmt_form.addRow(self._export_img_check)

        param_layout.addWidget(fmt_group)

        # 导出按钮
        self._export_btn = QPushButton("▶ 组合导出")
        self._export_btn.clicked.connect(self._do_export)
        param_layout.addWidget(self._export_btn)

        # 报告按钮
        self._report_btn = QPushButton("生成选波报告")
        self._report_btn.setProperty("secondary", True)
        self._report_btn.clicked.connect(self._generate_report)
        param_layout.addWidget(self._report_btn)

        param_layout.addStretch()
        layout.addWidget(param_widget)

        # 右侧报告预览
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("报告预览区域...")
        layout.addWidget(self._preview, 1)

    def _browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self._dir_edit.setText(dir_path)

    # ──────────── 外部接口 ────────────

    def set_results(self, results: list, database: PeerDatabase = None):
        """设置选波结果"""
        self._results = results
        if database:
            self._database = database
        self._n_natural_label.setText(str(len(results)))
        self._update_total()

    def set_code_spectrum(self, periods, sa):
        self._code_periods = periods
        self._code_sa = sa

    def add_generated_wave(self, signal):
        self._generated_waves.append(signal)

    def _update_total(self):
        n = len(self._results) + self._n_art_spin.value()
        self._total_label.setText(f"共 {n} 组")

    # ──────────── 导出 ────────────

    def _do_export(self):
        out_dir = self._dir_edit.text()
        if not out_dir:
            QMessageBox.warning(self, "警告", "请先选择输出目录")
            return

        if not self._results and not self._generated_waves:
            QMessageBox.warning(self, "警告", "没有可导出的数据")
            return

        try:
            combiner = Combiner(output_dir=out_dir)

            # 添加天然波
            if self._results and self._database:
                for r in self._results:
                    combiner.add_natural(r, self._database)

            # 添加人工波
            for i, sig in enumerate(self._generated_waves):
                combiner.add_artificial(h1=sig, index=i)

            # 导出波形
            fmt_map = {0: 'at2', 1: 'txt', 2: 'both'}
            fmt = fmt_map[self._wave_fmt_combo.currentIndex()]
            combiner.export(fmt=fmt)

            # 导出反应谱 CSV
            if self._export_spec_check.isChecked() and self._code_sa is not None:
                self._export_spectra_csv(out_dir, combiner)

            # 导出对比图
            if self._export_img_check.isChecked() and self._code_sa is not None:
                self._export_comparison_plot(out_dir, combiner)

            self._combiner = combiner

            # 预览报告
            self._preview.setPlainText(combiner.report_text())

            QMessageBox.information(
                self, "完成",
                f"已导出 {len(combiner.groups)} 组地震波到:\n{out_dir}"
            )

        except Exception as e:
            QMessageBox.critical(self, "导出错误", str(e))

    def _export_spectra_csv(self, out_dir, combiner: Combiner):
        """导出反应谱 CSV"""
        import csv
        path = os.path.join(out_dir, "spectra_comparison.csv")

        periods = self._code_periods
        header = ["T(s)", "Code_Sa(g)"]
        data_cols = [self._code_sa]

        for g in combiner.groups:
            if g.h1 is not None:
                from seiswave.core import Spectra
                spec = Spectra.compute(g.h1.acc, g.h1.dt, periods, 0.05)
                header.append(f"{g.name}_H1")
                data_cols.append(spec.sa)

        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for i in range(len(periods)):
                row = [f"{periods[i]:.4f}"]
                for col in data_cols:
                    row.append(f"{col[i]:.6f}")
                writer.writerow(row)

    def _export_comparison_plot(self, out_dir, combiner: Combiner):
        """导出反应谱对比图"""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 7))
        colors = get_mpl_colors(self._dark)
        periods = self._code_periods

        # 规范谱
        ax.plot(periods, self._code_sa, label="规范谱",
                color=colors['secondary'], linewidth=2.5, linestyle='--')

        # 各波反应谱
        palette = colors['palette']
        sa_list = []
        for i, g in enumerate(combiner.groups):
            if g.h1 is not None:
                from seiswave.core import Spectra
                spec = Spectra.compute(g.h1.acc, g.h1.dt, periods, 0.05)
                ax.plot(periods, spec.sa, label=g.name,
                        color=palette[i % len(palette)],
                        linewidth=1.2, alpha=0.8)
                sa_list.append(spec.sa)

        # 均值谱
        if len(sa_list) > 1:
            mean_sa = np.mean(sa_list, axis=0)
            ax.plot(periods, mean_sa, label="均值谱",
                    color=colors['fg'], linewidth=2.0, linestyle='-.')

        ax.set_xscale('log')
        ax.set_xlabel("周期 T (s)")
        ax.set_ylabel("加速度反应谱 Sa (g)")
        ax.set_title("选波结果 - 反应谱对比")
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        path = os.path.join(out_dir, "spectrum_comparison.png")
        fig.savefig(path, dpi=300, bbox_inches='tight')
        plt.close(fig)

        matplotlib.use('QtAgg')

    # ──────────── 报告 ────────────

    def _generate_report(self):
        if not self._results and not self._generated_waves:
            QMessageBox.warning(self, "警告", "没有选波结果")
            return

        lines = [
            "=" * 60,
            "SeisWave 选波报告",
            "=" * 60,
            "",
        ]

        if self._results:
            lines.append(f"天然波: {len(self._results)} 条")
            lines.append("-" * 60)
            for i, r in enumerate(self._results, 1):
                rec = r.record
                devs = ", ".join(f"T={k:.2f}s: {v:.0%}"
                                for k, v in r.deviations.items())
                lines.append(f"  {i}. RSN{rec.rsn} - {rec.event}")
                lines.append(f"     台站: {rec.station}, 分量: {rec.component}")
                lines.append(f"     缩放系数: {r.scale_factor:.3f}")
                lines.append(f"     匹配误差 RMSE: {r.match_error:.4f}")
                lines.append(f"     主周期偏差: {devs}")
                lines.append("")

        if self._generated_waves:
            lines.append(f"\n人工波: {len(self._generated_waves)} 条")
            lines.append("-" * 60)
            for i, sig in enumerate(self._generated_waves, 1):
                pga = float(np.max(np.abs(sig.acc)))
                dur = sig.n * sig.dt
                lines.append(f"  {i}. {sig.name}")
                lines.append(f"     PGA = {pga:.4f} g, 持时 = {dur:.1f} s")
                lines.append("")

        report_text = "\n".join(lines)
        self._preview.setPlainText(report_text)

        # 保存到文件
        out_dir = self._dir_edit.text()
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, "selection_report.txt")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            QMessageBox.information(self, "完成", f"报告已保存:\n{path}")

    def set_dark(self, dark: bool):
        self._dark = dark
