"""设置目标谱对话框：规范设计谱 / 从选中信号 / 自定义文件。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from seiswave.core.signal_pool import SignalPool
from seiswave.core.target_spectrum import TargetSpectrumService


_INTENSITY_ITEMS = [
    ("6 度 (0.05g)", 6),
    ("7 度 (0.10g)", 7),
    ("7 度 (0.15g)", 7.5),
    ("8 度 (0.20g)", 8),
    ("8 度 (0.30g)", 8.5),
    ("9 度 (0.40g)", 9),
]
_GROUP_ITEMS = [("第一组", 1), ("第二组", 2), ("第三组", 3)]
_SITE_ITEMS = [("I0 类", "I0"), ("I1 类", "I1"), ("II 类", "II"), ("III 类", "III"), ("IV 类", "IV")]
_LEVEL_ITEMS = [
    ("多遇地震(小震, 选波标准谱)", "frequent"),
    ("罕遇地震(大震)", "rare"),
    ("设防地震(中震, 近似·规范未列表)", "basic"),
]
_CODE_ITEMS = [("GB50011 建筑抗震设计", "GB50011"), ("GB/T51408 隔震设计", "GBT51408")]


class TargetSpectrumDialog(QDialog):
    """统一设置共享目标谱。"""

    def __init__(
        self,
        pool: SignalPool,
        target_service: TargetSpectrumService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._pool = pool
        self._target_service = target_service
        self.setWindowTitle("设置目标谱")
        self.setMinimumWidth(440)
        self._build_ui()
        self._prefill()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("规范设计谱", "code")
        self._mode_combo.addItem("从选中信号", "record")
        self._mode_combo.addItem("自定义文件 (两列 周期,Sa)", "custom")
        mode_form = QFormLayout()
        mode_form.addRow("来源:", self._mode_combo)
        root.addLayout(mode_form)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_code_page())
        self._stack.addWidget(self._build_record_page())
        self._stack.addWidget(self._build_custom_page())
        root.addWidget(self._stack)
        self._mode_combo.currentIndexChanged.connect(self._stack.setCurrentIndex)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_code_page(self):
        from PySide6.QtWidgets import QWidget

        page = QWidget()
        form = QFormLayout(page)
        self._code_combo = _combo(_CODE_ITEMS)
        self._intensity_combo = _combo(_INTENSITY_ITEMS)
        self._group_combo = _combo(_GROUP_ITEMS)
        self._site_combo = _combo(_SITE_ITEMS)
        self._level_combo = _combo(_LEVEL_ITEMS)
        self._code_zeta = _zeta_spin()
        # 默认 8 度 / 第二组 / II 类 / 多遇(选波标准谱)
        self._intensity_combo.setCurrentIndex(3)
        self._group_combo.setCurrentIndex(1)
        self._site_combo.setCurrentIndex(2)
        self._level_combo.setCurrentIndex(0)
        form.addRow("规范:", self._code_combo)
        form.addRow("设防烈度:", self._intensity_combo)
        form.addRow("设计地震分组:", self._group_combo)
        form.addRow("场地类别:", self._site_combo)
        form.addRow("地震水准:", self._level_combo)
        form.addRow("阻尼比 ζ:", self._code_zeta)
        return page

    def _build_record_page(self):
        from PySide6.QtWidgets import QWidget

        page = QWidget()
        form = QFormLayout(page)
        self._record_combo = QComboBox()
        for record in self._pool.all():
            self._record_combo.addItem(f"{record.name} ({record.kind})", record.id)
        self._record_zeta = _zeta_spin()
        if self._record_combo.count() == 0:
            form.addRow(QLabel("信号库为空，请先导入或生成信号。"))
        else:
            form.addRow("选择信号:", self._record_combo)
            form.addRow("阻尼比 ζ:", self._record_zeta)
        return page

    def _build_custom_page(self):
        from PySide6.QtWidgets import QWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel("选择两列文本/CSV 文件：第一列周期 T(s)，第二列谱加速度 Sa(g)。")
        )
        row = QHBoxLayout()
        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText("目标谱文件路径")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_custom)
        row.addWidget(self._custom_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _browse_custom(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择目标谱文件", "", "谱文件 (*.csv *.txt *.dat);;所有文件 (*)"
        )
        if path:
            self._custom_edit.setText(path)

    def _prefill(self) -> None:
        if self._target_service.source() != "code":
            return
        meta = self._target_service.meta()
        self._mode_combo.setCurrentIndex(0)
        _select_data(self._code_combo, meta.get("code", "GB50011").replace("/", "").replace(" ", ""))
        _select_data(self._intensity_combo, meta.get("intensity"))
        _select_data(self._group_combo, meta.get("group"))
        _select_data(self._site_combo, meta.get("site_class"))
        _select_data(self._level_combo, meta.get("level"))
        self._code_zeta.setValue(float(meta.get("zeta", 0.05)))

    def _apply(self) -> None:
        mode = str(self._mode_combo.currentData())
        try:
            if mode == "code":
                self._target_service.set_code(
                    str(self._code_combo.currentData()),
                    intensity=self._intensity_combo.currentData(),
                    group=int(self._group_combo.currentData()),
                    site_class=str(self._site_combo.currentData()),
                    level=str(self._level_combo.currentData()),
                    zeta=float(self._code_zeta.value()),
                )
            elif mode == "record":
                if self._record_combo.count() == 0:
                    raise ValueError("信号库为空，无法从信号设置目标谱")
                record = self._pool.get(str(self._record_combo.currentData()))
                if record is None:
                    raise ValueError("选中的信号已不存在")
                self._target_service.set_from_record(
                    record, zeta=float(self._record_zeta.value())
                )
            else:
                path = self._custom_edit.text().strip()
                if not path:
                    raise ValueError("请先选择目标谱文件")
                self._target_service.set_custom(path)
        except Exception as exc:
            QMessageBox.critical(self, "设置目标谱", str(exc))
            return
        self.accept()


def _combo(items) -> QComboBox:
    combo = QComboBox()
    for label, data in items:
        combo.addItem(label, data)
    return combo


def _zeta_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.01, 0.30)
    spin.setDecimals(3)
    spin.setSingleStep(0.01)
    spin.setValue(0.05)
    return spin


def _select_data(combo: QComboBox, data) -> None:
    if data is None:
        return
    index = combo.findData(data)
    if index >= 0:
        combo.setCurrentIndex(index)
