"""
导出与报告面板

导出时程数据（txt/csv/AT2）、反应谱数据（CSV）、图片（PNG/SVG）。
选波报告生成。
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QFormLayout, QPushButton, QFileDialog, QCheckBox,
    QLineEdit, QMessageBox, QTextEdit,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import FileIO, Spectra
from seiswave.gui.styles import get_mpl_colors


class ResultPanel(QWidget):
    """导出与报告面板"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._results = []
        self._code_periods = None
        self._code_sa = None
        self._generated_waves = []
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
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择输出目录...")
        self._dir_edit.setReadOnly(True)
        dir_layout.addWidget(self._dir_edit)
        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.setProperty("secondary", True)
        self._browse_btn.clicked.connect(self._browse_output)
        dir_layout.addWidget(self._browse_btn)
        param_layout.addWidget(dir_group)

        # 时程数据导出
        wave_group = QGroupBox("时程数据导出")
        wave_form = QFormLayout(wave_group)

        self._wave_fmt_combo = QComboBox()
        self._wave_fmt_combo.addItems(["AT2 格式", "TXT 单列", "CSV 格式"])
        wave_form.addRow("导出格式:", self._wave_fmt_combo)

        self._export_passed_check = QCheckBox("仅导出通过的地震波")
        self._export_passed_check.setChecked(True)
        wave_form.addRow(self._export_passed_check)

        self._export_generated_check = QCheckBox("包含人工波")
        wave_form.addRow(self._export_generated_check)

        self._export_wave_btn = QPushButton("导出时程数据")
        self._export_wave_btn.clicked.connect(self._export_waves)
        wave_form.addRow(self._export_wave_btn)

        param_layout.addWidget(wave_group)

        # 反应谱数据导出
        spec_group = QGroupBox("反应谱数据导出")
        spec_form = QFormLayout(spec_group)

        self._export_code_check = QCheckBox("规范谱")
        self._export_code_check.setChecked(True)
        spec_form.addRow(self._export_code_check)

        self._export_wave_spec_check = QCheckBox("各波反应谱")
        self._export_wave_spec_check.setChecked(True)
        spec_form.addRow(self._export_wave_spec_check)

        self._export_spec_btn = QPushButton("导出反应谱数据")
        self._export_spec_btn.clicked.connect(self._export_spectra)
        spec_form.addRow(self._export_spec_btn)

        param_layout.addWidget(spec_group)

        # 图片导出
        img_group = QGroupBox("图片导出")
        img_form = QFormLayout(img_group)

        self._img_fmt_combo = QComboBox()
        self._img_fmt_combo.addItems(["PNG (300 DPI)", "SVG 矢量图", "PDF"])
        img_form.addRow("图片格式:", self._img_fmt_combo)

        self._export_img_btn = QPushButton("导出对比图")
        self._export_img_btn.clicked.connect(self._export_images)
        img_form.addRow(self._export_img_btn)

        param_layout.addWidget(img_group)

        # 报告生成
        report_group = QGroupBox("选波报告")
        report_form = QFormLayout(report_group)

        self._gen_report_btn = QPushButton("生成选波报告")
        self._gen_report_btn.clicked.connect(self._generate_report)
        report_form.addRow(self._gen_report_btn)

        param_layout.addWidget(report_group)

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

    def _get_output_dir(self):
        d = self._dir_edit.text()
        if not d:
            QMessageBox.warning(self, "警告", "请先选择输出目录")
            return None
        os.makedirs(d, exist_ok=True)
        return d

    def set_results(self, results):
        """设置选波结果"""
        self._results = results

    def set_code_spectrum(self, periods, sa):
        self._code_periods = periods
        self._code_sa = sa

    def add_generated_wave(self, signal):
        self._generated_waves.append(signal)

    def _export_waves(self):
        """导出时程数据"""
        out_dir = self._get_output_dir()
        if not out_dir:
            return

        fmt_idx = self._wave_fmt_combo.currentIndex()
        signals_to_export = []

        if self._results:
            if self._export_passed_check.isChecked():
                signals_to_export = [r.signal for r in self._results if r.passed]
            else:
                signals_to_export = [r.signal for r in self._results]

        if self._export_generated_check.isChecked():
            signals_to_export.extend(self._generated_waves)

        if not signals_to_export:
            QMessageBox.information(self, "提示", "没有可导出的地震波数据")
            return

        count = 0
        for sig in signals_to_export:
            name = sig.name or f"wave_{count+1}"
            name = name.replace("/", "_").replace("\\", "_")
            try:
                if fmt_idx == 0:
                    FileIO.write_at2(os.path.join(out_dir, f"{name}.AT2"),
                                     sig.acc, sig.dt)
                elif fmt_idx == 1:
                    FileIO.write_txt(os.path.join(out_dir, f"{name}.txt"),
                                     sig.acc, sig.dt)
                else:
                    FileIO.write_csv(os.path.join(out_dir, f"{name}.csv"),
                                     time=sig.time, acc=sig.acc)
                count += 1
            except Exception:
                continue

        QMessageBox.information(self, "完成", f"已导出 {count} 条地震波到:\n{out_dir}")

    def _export_spectra(self):
        """导出反应谱数据"""
        out_dir = self._get_output_dir()
        if not out_dir:
            return

        if self._export_code_check.isChecked() and self._code_sa is not None:
            FileIO.write_csv(
                os.path.join(out_dir, "code_spectrum.csv"),
                T=self._code_periods, Sa=self._code_sa,
            )

        if self._export_wave_spec_check.isChecked() and self._results:
            passed = [r for r in self._results if r.passed]
            for r in passed:
                spec = Spectra.compute(r.signal.acc, r.signal.dt,
                                       self._code_periods, 0.05)
                name = (r.signal.name or "wave").replace("/", "_")
                FileIO.write_csv(
                    os.path.join(out_dir, f"spectrum_{name}.csv"),
                    T=self._code_periods, Sa=spec.sa,
                )

        QMessageBox.information(self, "完成", f"反应谱数据已导出到:\n{out_dir}")

    def _export_images(self):
        """导出对比图"""
        out_dir = self._get_output_dir()
        if not out_dir:
            return

        if self._code_sa is None or not self._results:
            QMessageBox.warning(self, "警告", "没有可导出的图表数据")
            return

        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fmt_map = {0: ("png", 300), 1: ("svg", None), 2: ("pdf", None)}
        ext, dpi = fmt_map[self._img_fmt_combo.currentIndex()]

        fig, ax = plt.subplots(figsize=(10, 6))
        colors = get_mpl_colors(self._dark)

        ax.plot(self._code_periods, self._code_sa, label="规范谱",
                color=colors['secondary'], linewidth=2.5, linestyle='--')

        passed = [r for r in self._results if r.passed]
        palette = colors['palette']
        for i, r in enumerate(passed):
            spec = Spectra.compute(r.signal.acc, r.signal.dt,
                                   self._code_periods, 0.05)
            ax.plot(self._code_periods, spec.sa, label=r.signal.name,
                    color=palette[i % len(palette)], linewidth=1.2, alpha=0.8)

        ax.set_xscale('log')
        ax.set_xlabel("周期 T (s)")
        ax.set_ylabel("加速度反应谱 Sa (g)")
        ax.set_title("选波结果 - 反应谱对比")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        path = os.path.join(out_dir, f"spectrum_comparison.{ext}")
        fig.savefig(path, dpi=dpi, bbox_inches='tight')
        plt.close(fig)

        # 恢复 Qt backend
        matplotlib.use('QtAgg')

        QMessageBox.information(self, "完成", f"图片已导出:\n{path}")

    def _generate_report(self):
        """生成选波报告"""
        if not self._results:
            QMessageBox.warning(self, "警告", "没有选波结果")
            return

        passed = [r for r in self._results if r.passed]
        total = len(self._results)

        lines = [
            "=" * 60,
            "SeisWave 选波报告",
            "=" * 60,
            "",
            f"总计筛选: {total} 条地震波",
            f"通过: {len(passed)} 条",
            f"通过率: {len(passed)/total*100:.1f}%",
            "",
            "-" * 60,
            "通过的地震波:",
            "-" * 60,
        ]

        for i, r in enumerate(passed, 1):
            devs = ", ".join(f"T={k:.3f}s: {v*100:.1f}%"
                            for k, v in sorted(r.deviations.items()))
            lines.append(f"  {i}. {r.signal.name}")
            lines.append(f"     有效持时: {r.effective_duration:.2f} s")
            lines.append(f"     谱偏差: {devs}")
            if r.shear_ratio is not None:
                lines.append(f"     剪力比: {r.shear_ratio:.3f}")
            lines.append("")

        lines.extend([
            "-" * 60,
            "未通过的地震波:",
            "-" * 60,
        ])
        failed = [r for r in self._results if not r.passed]
        for i, r in enumerate(failed, 1):
            lines.append(f"  {i}. {r.signal.name}")

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
