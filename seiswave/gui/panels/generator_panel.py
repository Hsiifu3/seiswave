"""人工波生成面板（三栏响应式布局版）

支持四种地震动类型：
- 一般人工波：基于目标谱的迭代匹配
- 远场 FF：基于 GMPE 目标谱 + 远场包络
- 近场无脉冲 NF：基于 GMPE 目标谱 + 近场包络
- 近场脉冲 NFP：脉冲分量 + 残余分量叠加

三栏布局：左栏参数（320px） | 中间绘图（弹性≥500px） | 右栏信息（280px）
底部状态栏（32px）
"""

import os
import logging
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Signal, Qt

from seiswave.gui.panels.left_panel import LeftPanel
from seiswave.gui.panels.center_panel import CenterPanel
from seiswave.gui.panels.right_panel import RightPanel
from seiswave.gui.panels.bottom_bar import BottomBar
from seiswave.gui.panels.result_presenter import ResultPresenter
from seiswave.gui.panels.generator_controller import GeneratorController

# 向后兼容：常量仍可从本模块导入
from seiswave.gui.panels.param_form import GM_TYPE_LABELS, GM_TYPE_CODES

logger = logging.getLogger(__name__)


def _load_theme_qss(dark: bool = False) -> str:
    """加载并可选替换 theme.qss 颜色"""
    path = os.path.join(
        os.path.dirname(__file__), "..", "styles", "theme.qss"
    )
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        qss = f.read()
    if dark:
        # 浅色→深色关键色替换
        qss = qss.replace("#2196F3", "#64B5F6")
        qss = qss.replace("#1976D2", "#42A5F5")
        qss = qss.replace("#0D47A1", "#1976D2")
        qss = qss.replace("#607D8B", "#78909C")
        qss = qss.replace("#CCCCCC", "#3D3D3D")
        qss = qss.replace("#E0E0E0", "#3D3D3D")
        qss = qss.replace("#E3F2FD", "#1E3A5F")
        qss = qss.replace("#888", "#AAAAAA")
        qss = qss.replace("#666", "#AAAAAA")
    return qss


class GeneratorPanel(QWidget):
    """人工波生成面板（三栏响应式 + 卡片化参数）"""

    wave_generated = Signal(object)  # 生成完成信号 (EQSignal)

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._code_periods = None
        self._code_sa = None
        self._generated = None
        self._setup_ui()
        self._connect_signals()
        self._apply_panel_theme()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── 三栏主体 ──
        body = QHBoxLayout()
        body.setSpacing(4)

        # 左栏
        self._left_panel = LeftPanel()
        body.addWidget(self._left_panel)

        # 中间
        self._center_panel = CenterPanel(dark=self._dark)
        body.addWidget(self._center_panel, 1)

        # 右栏
        self._right_panel = RightPanel()
        body.addWidget(self._right_panel)

        root.addLayout(body, 1)

        # ── 底部状态栏 ──
        self._bottom_bar = BottomBar()
        root.addWidget(self._bottom_bar)

        # ── 内部向后兼容组件 ──
        # ParamFormWidget 和 ProgressWidget 已嵌入左栏
        self._param_form = self._left_panel.param_form
        self._progress = self._left_panel.progress

        # 绘图引用
        spec_plot = self._center_panel.spec_plot
        time_plot = self._center_panel.time_plot

        # 结果呈现器与控制器
        self._result_presenter = ResultPresenter(
            spec_plot, time_plot, dark=self._dark
        )
        self._controller = GeneratorController()

    def _connect_signals(self):
        self._param_form.run_clicked.connect(self._run_generation)
        self._controller.progress.connect(self._on_progress)
        self._controller.finished.connect(self._on_finished)
        self._controller.error.connect(self._on_error)

        # 类型切换时更新右栏可见性
        self._param_form.type_changed.connect(self._on_type_changed)

    def _apply_panel_theme(self):
        qss = _load_theme_qss(self._dark)
        if qss:
            self.setStyleSheet(qss)

    def _on_type_changed(self, index):
        label = GM_TYPE_LABELS[index]
        is_nfp = (label == "近场脉冲 NFP")
        self._right_panel.set_nfp_visible(is_nfp)
        if is_nfp:
            self._right_panel.set_fault_type(
                self._param_form._fault_combo.currentText()
            )
        else:
            self._right_panel.clear()

    def _on_progress(self, pct, text):
        logger.info("[panel] progress pct=%s text=%s", pct, text)
        self._progress.update(pct, text)
        self._bottom_bar.set_progress_value(pct)
        self._bottom_bar.set_status(text)

    # ── 生成触发 ──

    def _run_generation(self):
        label = self._param_form._type_combo.currentText()
        is_general = (label == "一般人工波")
        logger.info("[panel] run clicked label=%s is_general=%s", label, is_general)

        if is_general and (self._code_sa is None or len(self._code_sa) == 0):
            logger.warning("[panel] run blocked: target spectrum missing")
            QMessageBox.warning(self, "警告",
                                "请先设置目标谱（在规范谱面板中设置）")
            return

        params = self._param_form.get_params()
        target_info = {
            'periods': 0 if self._code_periods is None else len(self._code_periods),
            'pga': float(max(self._code_sa)) if self._code_sa is not None and len(self._code_sa) > 0 else None,
            'Tg': params.get('Tg'),
        }
        logger.info("[panel] dispatch generation params=%s target=%s",
                    {
                        'n': params['n'], 'dt': params['dt'], 'zeta': params['zeta'],
                        'tol': params['tol'], 'max_iter': params['max_iter'],
                        'n_trials': params['n_trials'], 'fm': params.get('fm', 0),
                    }, target_info)
        self._param_form._run_btn.setEnabled(False)
        self._progress.start()
        self._bottom_bar.set_status("正在生成...")
        self._right_panel.clear()

        if is_general:
            self._controller.run_general(
                self._param_form, self._code_periods, self._code_sa)
        else:
            self._controller.run_special(
                self._param_form, self._code_periods, self._code_sa)

    # ── 完成回调 ──

    def _on_finished(self, result, label):
        logger.info("[panel] finished signal received label=%s result_type=%s", label, type(result).__name__)
        self._param_form._run_btn.setEnabled(True)
        is_general = (label == "一般人工波")
        is_nfp = (label == "近场脉冲 NFP")

        try:
            if is_general:
                info_lines, progress_text = self._result_presenter.present_general(
                    result, self._code_periods, self._code_sa)
                best = result['best']
                # 记录关键指标
                from seiswave.core.generator import WaveGenerator
                from seiswave.core.spectrum import Spectra
                pga = float(np.max(np.abs(best.acc)))
                if self._code_periods is not None and self._code_sa is not None:
                    spec = Spectra.compute(best.acc, best.dt, self._code_periods, 0.05, method='mixed')
                    fit = WaveGenerator.fit_error(spec.sa, self._code_sa)
                    logger.info("[panel] result metrics PGA=%.4f mean_err=%.2f%% max_err=%.2f%% trials=%s",
                                pga, fit['mean_error']*100, fit['max_error']*100,
                                result.get('n_trials', 1))
                else:
                    logger.info("[panel] result metrics PGA=%.4f (no target spectrum)", pga)
            else:
                info_lines, progress_text = self._result_presenter.present_special(
                    result, label, self._code_periods, self._code_sa)
                best = result
                pga = float(np.max(np.abs(best.acc))) if hasattr(best, 'acc') else 0
                logger.info("[panel] result metrics PGA=%.4f label=%s", pga, label)

            self._progress.finish(info_lines, progress_text)
            self._bottom_bar.set_progress_text(progress_text)
            self._bottom_bar.set_status("生成完成")

            self._generated = best
            self.wave_generated.emit(best)

            # 更新右栏
            self._right_panel.set_info(info_lines)
            if is_nfp:
                self._right_panel.set_nfp_visible(True)
                if hasattr(best, 'pulse_params') and best.pulse_params:
                    self._right_panel.set_pulse_params(best.pulse_params)
                if hasattr(best, 'pulse_metrics') and best.pulse_metrics:
                    self._right_panel.set_baker_metrics(best.pulse_metrics)
                self._right_panel.set_fault_type(
                    self._param_form._fault_combo.currentText()
                )

        except Exception as e:
            logger.exception("[panel] result presentation failed: %s", e)
            self._progress.error(str(e))
            self._bottom_bar.set_status(f"生成出错: {e}")

    def _on_error(self, err):
        logger.error("[panel] worker error=%s", err)
        self._param_form._run_btn.setEnabled(True)
        self._progress.error(err)
        self._bottom_bar.set_status(f"生成出错: {err}")

    # ── 公共接口 ──

    def set_code_spectrum(self, periods, sa):
        """设置规范谱作为目标谱"""
        logger.info("[panel] set_code_spectrum points=%s has_sa=%s", 0 if periods is None else len(periods), sa is not None)
        self._code_periods = periods
        self._code_sa = sa
        if sa is not None and len(sa) > 0:
            self._param_form.set_target_pga(max(sa))
            self._param_form.set_target_info(f"已设置 ({len(sa)} 点, PGA={max(sa):.3f}g)")
            self._param_form.set_code_spectrum_set(True)
        else:
            self._param_form.set_target_info("尚未设置")
            self._param_form.set_code_spectrum_set(False)
        self._center_panel.spec_plot.clear()
        self._center_panel.spec_plot.plot_code_spectrum(periods, sa, label="目标谱")
        self._center_panel.spec_plot.ax.set_title("目标反应谱", fontsize=11)
        self._center_panel.spec_plot.refresh()

    def get_generated(self):
        return self._result_presenter.get_generated()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._center_panel.set_dark(dark)
        self._result_presenter.set_dark(dark)
        self._apply_panel_theme()

    # ── 向后兼容属性委托（现有测试直接访问这些属性）──

    @property
    def _type_combo(self):
        return self._param_form._type_combo

    @property
    def _special_group(self):
        return self._param_form._special_group

    @property
    def _fault_combo(self):
        return self._param_form._fault_combo

    @property
    def _dt_spin(self):
        return self._param_form._dt_spin

    @property
    def _run_btn(self):
        return self._param_form._run_btn
