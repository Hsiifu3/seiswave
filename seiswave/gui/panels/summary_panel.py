from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt

from seiswave.core import build_selection_summary


class SummaryPanel(QWidget):
    """选波汇总页（人工波+天然波）。"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._results = []
        self._generated = []
        self._code_periods = None
        self._code_sa = None

        layout = QVBoxLayout(self)
        self._overview = QLabel("等待选波结果...")
        self._overview.setWordWrap(True)
        layout.addWidget(self._overview)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(["类型", "标识", "事件/名称", "缩放", "RMSE", "PGA(g)", "持时(s)"])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self._table)

    def set_code_spectrum(self, periods, sa):
        self._code_periods = periods
        self._code_sa = sa
        self._refresh()

    def set_results(self, results):
        self._results = results or []
        self._refresh()

    def set_generated_waves(self, waves):
        self._generated = waves or []
        self._refresh()

    def get_summary(self):
        return build_selection_summary(self._results, self._generated, self._code_periods, self._code_sa)

    def _refresh(self):
        summary = self.get_summary()
        self._overview.setText(
            f"汇总：天然波 {summary['natural_count']} 条，人工波 {summary['artificial_count']} 条，合计 {summary['total_count']} 条。"
            "\n说明：导入地震动可作为候选库或校核对象，选波结果与人工波统一在此汇总后导出。"
        )
        rows = summary['natural'] + summary['artificial']
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            if row['type'] == 'natural':
                ident = f"RSN{row['rsn']}"
                name = row['event']
                scale = f"{row['scale_factor']:.2f}"
                rmse = f"{row['match_rmse']:.4f}"
            else:
                ident = row['name']
                name = row['name']
                scale = "-"
                rmse = "-"
            vals = [
                "天然波" if row['type'] == 'natural' else "人工波",
                ident,
                name,
                scale,
                rmse,
                f"{row['pga']:.4f}",
                f"{row['duration']:.2f}",
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if j != 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(i, j, item)

    def set_dark(self, dark: bool):
        self._dark = dark
