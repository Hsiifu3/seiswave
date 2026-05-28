"""右栏结果面板

- 宽度 280px，固定
- 一般/FF/NF 时：显示基本信息（PGA、持时、误差）
- NFP 时：额外显示脉冲参数卡片（Tp、A、φ、Baker 置信度进度条）
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt

from seiswave.gui.panels.param_cards import NFPExtraCard


class RightPanel(QWidget):
    """右栏：结果摘要 + NFP 脉冲参数"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedWidth(280)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── 基本信息卡片 ──
        self._info_group = QFrame()
        self._info_group.setFrameShape(QFrame.StyledPanel)
        info_layout = QVBoxLayout(self._info_group)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(6)

        self._lbl_type = QLabel("--")
        self._lbl_type.setStyleSheet("font-weight: bold; font-size: 13px;")
        info_layout.addWidget(self._lbl_type)

        grid = QHBoxLayout()
        grid.setSpacing(8)

        self._lbl_pga = QLabel("--")
        self._lbl_pga.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._lbl_dur = QLabel("--")
        self._lbl_dur.setStyleSheet("font-family: monospace; font-size: 12px;")
        self._lbl_err = QLabel("--")
        self._lbl_err.setStyleSheet("font-family: monospace; font-size: 12px;")

        v1 = QVBoxLayout(); v1.addWidget(QLabel("PGA (g)")); v1.addWidget(self._lbl_pga)
        v2 = QVBoxLayout(); v2.addWidget(QLabel("持时 (s)")); v2.addWidget(self._lbl_dur)
        v3 = QVBoxLayout(); v3.addWidget(QLabel("误差")); v3.addWidget(self._lbl_err)
        grid.addLayout(v1)
        grid.addLayout(v2)
        grid.addLayout(v3)
        info_layout.addLayout(grid)
        layout.addWidget(self._info_group)

        # ── NFP 脉冲参数卡片 ──
        self._nfp_card = NFPExtraCard()
        layout.addWidget(self._nfp_card)

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

    def set_info(self, info_lines: list[str]):
        """设置基本信息

        info_lines 形如:
            ["类型: 远场 FF", "PGA = 0.2000 g", "持时 = 40.00 s", ...]
        """
        type_text = ""
        pga_text = "--"
        dur_text = "--"
        err_text = "--"

        for line in info_lines:
            if line.startswith("类型:"):
                type_text = line.replace("类型:", "").strip()
            elif "PGA" in line and "=" in line:
                pga_text = line.split("=")[-1].strip()
            elif "持时" in line and "=" in line:
                dur_text = line.split("=")[-1].strip()
            elif "偏差" in line and "=" in line:
                err_text = line.split("=")[-1].strip()

        self._lbl_type.setText(type_text or "结果")
        self._lbl_pga.setText(pga_text)
        self._lbl_dur.setText(dur_text)
        self._lbl_err.setText(err_text)

    def set_nfp_visible(self, visible: bool):
        self._nfp_card.setVisible(visible)

    def set_pulse_params(self, params):
        self._nfp_card.set_pulse_params(params)

    def set_baker_metrics(self, metrics):
        self._nfp_card.set_baker_metrics(metrics)

    def set_fault_type(self, fault: str):
        self._nfp_card.set_fault_type(fault)

    def clear(self):
        self._lbl_type.setText("--")
        self._lbl_pga.setText("--")
        self._lbl_dur.setText("--")
        self._lbl_err.setText("--")
        self._nfp_card.setVisible(False)
        self._nfp_card.set_pulse_params(None)
        self._nfp_card.set_baker_metrics(None)
