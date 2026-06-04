"""
选波报告预览面板

仅负责展示选波 / 人工波组合的报告预览。
文件导出（波形、谱 CSV、对比图、报告）统一由「组合」面板的一键导出负责，
本面板不再重复提供输出目录 / 导出选项 / 导出按钮，避免两条导出路径。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
)
from PySide6.QtCore import Qt


class ResultPanel(QWidget):
    """选波报告预览面板（只读预览，不负责文件导出）"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._results = []
        self._database = None
        self._code_periods = None
        self._code_sa = None
        self._generated_waves = []
        self._combiner = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("选波报告预览")
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        self._report_btn = QPushButton("刷新报告")
        self._report_btn.setProperty("secondary", True)
        self._report_btn.clicked.connect(self._generate_report)
        header.addWidget(self._report_btn)
        layout.addLayout(header)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText(
            "选波 / 生成人工波后在此显示报告。\n"
            "文件导出请使用左侧「组合」面板的「一键导出（波形+报告）」。")
        layout.addWidget(self._preview, 1)

    # ──────────── 外部接口 ────────────

    def set_results(self, results, database=None):
        self._results = results
        if database:
            self._database = database
        self._generate_report()

    def set_code_spectrum(self, periods, sa):
        self._code_periods = periods
        self._code_sa = sa

    def add_generated_wave(self, signal):
        self._generated_waves.append(signal)
        self._generate_report()

    def set_dark(self, dark):
        self._dark = dark

    # ──────────── 报告 ────────────

    def _generate_report(self):
        if not self._results and not self._generated_waves:
            self._preview.clear()
            return

        n_periods = len(self._code_periods) if self._code_periods is not None else 0
        lines = [
            "SeisWave 地震动选波与人工波组合报告（GB 工程实践格式）",
            "=" * 72,
            "1. 项目概况与目标谱",
            f"- 目标谱点数: {n_periods}",
            "- 阻尼比: 5%",
            "",
            "2. 天然波选取结果",
            f"- 入选数量: {len(self._results)}",
        ]
        for i, r in enumerate(self._results, 1):
            rec = r.record
            devs = ", ".join(f"T={k:.2f}s:{v:.0%}" for k, v in r.deviations.items())
            lines.append(
                f"  {i}) RSN{rec.rsn} | {rec.event} | {rec.station} | "
                f"{rec.component} | 缩放={r.scale_factor:.3f} | "
                f"RMSE={r.match_error:.4f} | 偏差={devs}")

        lines += ["", "3. 人工波结果", f"- 入选数量: {len(self._generated_waves)}"]
        for i, sig in enumerate(self._generated_waves, 1):
            pga = float(np.max(np.abs(sig.acc)))
            dur = sig.n * sig.dt
            lines.append(
                f"  {i}) {sig.name} | PGA={pga:.4f}g | 持时={dur:.2f}s | "
                f"dt={sig.dt:.4f}s")

        lines += [
            "", "4. 组合与导出",
            "- 输出包含: 波形文件、spectra_comparison.csv、"
            "spectrum_comparison.png、selection_report.txt",
            "- 导出操作请使用「组合」面板的一键导出。",
        ]
        self._preview.setPlainText("\n".join(lines))
