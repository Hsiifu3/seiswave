"""左侧信号库面板。"""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from seiswave.core.signal_pool import SignalPool, SignalRecord


KIND_LABELS = {
    "natural": "天然",
    "artificial": "人工",
    "processed": "处理后",
}


class SignalPoolPanel(QWidget):
    """工作台共享信号库面板。"""

    tool_requested = Signal(str)

    def __init__(self, pool: SignalPool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pool = pool
        self._summary_label: QLabel | None = None
        self._list: QListWidget | None = None
        self._setup_ui()
        self._connect_pool()
        self.refresh_records()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("信号库")
        root.addWidget(group)

        layout = QVBoxLayout(group)
        self._summary_label = QLabel("0 条记录")
        layout.addWidget(self._summary_label)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, 1)

        button_row = QHBoxLayout()
        for text, tool_name in (
            ("导入", "导入"),
            ("自动选波", "自动选波"),
            ("生成", "人工波生成"),
        ):
            button = QPushButton(text)
            button.clicked.connect(
                lambda _checked=False, name=tool_name: self.tool_requested.emit(name)
            )
            button_row.addWidget(button)
        layout.addLayout(button_row)

    def _connect_pool(self) -> None:
        self._pool.signals_changed.connect(self.refresh_records)
        self._pool.selection_changed.connect(self.sync_selection_from_pool)

    def refresh_records(self) -> None:
        """从共享信号池刷新列表。"""
        assert self._list is not None
        records = self._pool.all()
        with QSignalBlocker(self._list):
            self._list.clear()
            for record in records:
                item = QListWidgetItem(self._display_text(record))
                item.setData(Qt.UserRole, record.id)
                self._list.addItem(item)
        if self._summary_label is not None:
            self._summary_label.setText(f"{len(records)} 条记录")
        self.sync_selection_from_pool()

    def sync_selection_from_pool(self) -> None:
        """将池内选中状态同步到列表。"""
        assert self._list is not None
        selected_ids = set(self._pool.selection_ids())
        with QSignalBlocker(self._list):
            for index in range(self._list.count()):
                item = self._list.item(index)
                item.setSelected(item.data(Qt.UserRole) in selected_ids)

    def _on_selection_changed(self) -> None:
        assert self._list is not None
        selected_ids = [
            item.data(Qt.UserRole)
            for item in self._list.selectedItems()
            if item.data(Qt.UserRole)
        ]
        self._pool.set_selection(selected_ids)

    def _display_text(self, record: SignalRecord) -> str:
        kind = KIND_LABELS.get(record.kind, record.kind or "未分类")
        source = self._source_text(record)
        name = record.name or "未命名信号"
        return f"[{kind}] {name} · {source}"

    def _source_text(self, record: SignalRecord) -> str:
        meta = record.meta
        if "source" in meta and meta["source"]:
            return str(meta["source"])
        if "record_name" in meta and meta["record_name"]:
            return str(meta["record_name"])
        if "file_name" in meta and meta["file_name"]:
            return str(meta["file_name"])
        if "rsn" in meta:
            return f"RSN{meta['rsn']}"
        if record.parent_id:
            return "派生信号"
        return "本地/内存"
