"""
地震波列表表格控件

显示导入的地震波信息：文件名、PGA、持时、有效持时等。
"""

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Signal, Qt


class WaveTable(QTableWidget):
    """地震波列表表格"""

    wave_selected = Signal(int)       # 选中行索引
    wave_double_clicked = Signal(int) # 双击行索引

    COLUMNS = ["文件名", "PGA (g)", "持时 (s)", "有效持时 (s)", "采样间隔 (s)", "数据点数"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._signals = []
        self._setup()

    def _setup(self):
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.cellDoubleClicked.connect(self._on_double_click)

    def _on_selection_changed(self):
        rows = self.selectionModel().selectedRows()
        if rows:
            self.wave_selected.emit(rows[0].row())

    def _on_double_click(self, row, _col):
        self.wave_double_clicked.emit(row)

    def load_signals(self, signals):
        """加载地震波列表"""
        self._signals = signals
        self.setRowCount(len(signals))
        for i, sig in enumerate(signals):
            self.setItem(i, 0, QTableWidgetItem(sig.name or f"Wave_{i+1}"))
            self.setItem(i, 1, QTableWidgetItem(f"{sig.pga:.4f}"))
            self.setItem(i, 2, QTableWidgetItem(f"{sig.duration:.2f}"))
            eff_dur = sig.effective_duration
            self.setItem(i, 3, QTableWidgetItem(f"{eff_dur:.2f}"))
            self.setItem(i, 4, QTableWidgetItem(f"{sig.dt:.4f}"))
            self.setItem(i, 5, QTableWidgetItem(str(sig.n)))
            # 右对齐数值列
            for j in range(1, 6):
                item = self.item(i, j)
                if item:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def get_signal(self, row):
        """获取指定行的信号对象"""
        if 0 <= row < len(self._signals):
            return self._signals[row]
        return None

    def get_selected_signal(self):
        """获取当前选中的信号对象"""
        rows = self.selectionModel().selectedRows()
        if rows:
            return self.get_signal(rows[0].row())
        return None

    def clear_all(self):
        """清空表格"""
        self._signals = []
        self.setRowCount(0)
