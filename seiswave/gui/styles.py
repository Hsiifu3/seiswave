"""
SeisWave GUI 样式表 - 深色/浅色主题

现代学术科研风格
"""

LIGHT_THEME = """
QMainWindow {
    background-color: #f5f5f5;
}
QMenuBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    padding: 2px;
}
QMenuBar::item:selected {
    background-color: #e3f2fd;
    border-radius: 4px;
}
QMenu {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 4px;
}
QMenu::item:selected {
    background-color: #e3f2fd;
    border-radius: 4px;
}
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    spacing: 4px;
    padding: 4px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
}
QToolButton:hover {
    background-color: #e3f2fd;
    border: 1px solid #bbdefb;
}
QToolButton:checked {
    background-color: #bbdefb;
    border: 1px solid #90caf9;
}
QStatusBar {
    background-color: #ffffff;
    border-top: 1px solid #e0e0e0;
    font-size: 12px;
    color: #666666;
}
QGroupBox {
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #1565c0;
}
QLabel {
    font-size: 13px;
    color: #333333;
}
QComboBox {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: #ffffff;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #90caf9;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QSpinBox, QDoubleSpinBox {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: #ffffff;
    min-height: 24px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #90caf9;
}
QLineEdit {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: #ffffff;
    min-height: 24px;
}
QLineEdit:hover {
    border-color: #90caf9;
}
QLineEdit:focus {
    border-color: #1565c0;
}
QPushButton {
    background-color: #1565c0;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #1976d2;
}
QPushButton:pressed {
    background-color: #0d47a1;
}
QPushButton:disabled {
    background-color: #bdbdbd;
}
QPushButton[secondary="true"] {
    background-color: #f5f5f5;
    color: #333333;
    border: 1px solid #e0e0e0;
}
QPushButton[secondary="true"]:hover {
    background-color: #eeeeee;
}
QCheckBox {
    font-size: 13px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #bdbdbd;
}
QCheckBox::indicator:checked {
    background-color: #1565c0;
    border-color: #1565c0;
}
QTableWidget {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background-color: #ffffff;
    gridline-color: #f0f0f0;
    font-size: 12px;
}
QTableWidget::item:selected {
    background-color: #e3f2fd;
    color: #333333;
}
QHeaderView::section {
    background-color: #fafafa;
    border: none;
    border-bottom: 1px solid #e0e0e0;
    border-right: 1px solid #f0f0f0;
    padding: 6px;
    font-weight: bold;
    font-size: 12px;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QSplitter::handle {
    background-color: #e0e0e0;
    width: 2px;
    height: 2px;
}
QProgressBar {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    text-align: center;
    font-size: 12px;
    min-height: 20px;
}
QProgressBar::chunk {
    background-color: #1565c0;
    border-radius: 3px;
}
QTabWidget::pane {
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background-color: #ffffff;
}
QTabBar::tab {
    background-color: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    font-size: 13px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    border-bottom: 2px solid #1565c0;
}
"""

DARK_THEME = """
QMainWindow {
    background-color: #1e1e1e;
}
QMenuBar {
    background-color: #2d2d2d;
    border-bottom: 1px solid #3d3d3d;
    padding: 2px;
    color: #e0e0e0;
}
QMenuBar::item:selected {
    background-color: #3d3d3d;
    border-radius: 4px;
}
QMenu {
    background-color: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 4px;
    color: #e0e0e0;
}
QMenu::item:selected {
    background-color: #3d3d3d;
    border-radius: 4px;
}
QToolBar {
    background-color: #2d2d2d;
    border-bottom: 1px solid #3d3d3d;
    spacing: 4px;
    padding: 4px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 13px;
    color: #e0e0e0;
}
QToolButton:hover {
    background-color: #3d3d3d;
    border: 1px solid #4d4d4d;
}
QToolButton:checked {
    background-color: #1565c0;
    border: 1px solid #1976d2;
}
QStatusBar {
    background-color: #2d2d2d;
    border-top: 1px solid #3d3d3d;
    font-size: 12px;
    color: #999999;
}
QGroupBox {
    font-weight: bold;
    font-size: 13px;
    border: 1px solid #3d3d3d;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    background-color: #2d2d2d;
    color: #e0e0e0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #64b5f6;
}
QLabel {
    font-size: 13px;
    color: #e0e0e0;
}
QComboBox {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: #2d2d2d;
    color: #e0e0e0;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #64b5f6;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #e0e0e0;
    selection-background-color: #3d3d3d;
}
QSpinBox, QDoubleSpinBox {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: #2d2d2d;
    color: #e0e0e0;
    min-height: 24px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #64b5f6;
}
QLineEdit {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    padding: 4px 8px;
    background-color: #2d2d2d;
    color: #e0e0e0;
    min-height: 24px;
}
QLineEdit:hover {
    border-color: #64b5f6;
}
QLineEdit:focus {
    border-color: #64b5f6;
}
QPushButton {
    background-color: #1565c0;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #1976d2;
}
QPushButton:pressed {
    background-color: #0d47a1;
}
QPushButton:disabled {
    background-color: #555555;
    color: #888888;
}
QPushButton[secondary="true"] {
    background-color: #3d3d3d;
    color: #e0e0e0;
    border: 1px solid #4d4d4d;
}
QPushButton[secondary="true"]:hover {
    background-color: #4d4d4d;
}
QCheckBox {
    font-size: 13px;
    spacing: 6px;
    color: #e0e0e0;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #555555;
}
QCheckBox::indicator:checked {
    background-color: #1565c0;
    border-color: #1565c0;
}
QTableWidget {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    background-color: #2d2d2d;
    gridline-color: #3d3d3d;
    font-size: 12px;
    color: #e0e0e0;
}
QTableWidget::item:selected {
    background-color: #1565c0;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #333333;
    border: none;
    border-bottom: 1px solid #3d3d3d;
    border-right: 1px solid #3d3d3d;
    padding: 6px;
    font-weight: bold;
    font-size: 12px;
    color: #e0e0e0;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QSplitter::handle {
    background-color: #3d3d3d;
    width: 2px;
    height: 2px;
}
QProgressBar {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    text-align: center;
    font-size: 12px;
    min-height: 20px;
    color: #e0e0e0;
    background-color: #2d2d2d;
}
QProgressBar::chunk {
    background-color: #1565c0;
    border-radius: 3px;
}
QTabWidget::pane {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    background-color: #2d2d2d;
}
QTabBar::tab {
    background-color: #333333;
    border: 1px solid #3d3d3d;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    font-size: 13px;
    color: #e0e0e0;
}
QTabBar::tab:selected {
    background-color: #2d2d2d;
    border-bottom: 2px solid #64b5f6;
}
"""


def get_theme(dark: bool = False) -> str:
    """获取主题样式表"""
    return DARK_THEME if dark else LIGHT_THEME


# Matplotlib 绘图配色
MPL_COLORS = {
    'light': {
        'bg': '#ffffff',
        'fg': '#333333',
        'grid': '#e0e0e0',
        'axes_bg': '#fafafa',
        'primary': '#1565c0',
        'secondary': '#e53935',
        'accent': '#43a047',
        'palette': ['#1565c0', '#e53935', '#43a047', '#ff8f00',
                     '#6a1b9a', '#00838f', '#d81b60', '#558b2f'],
    },
    'dark': {
        'bg': '#2d2d2d',
        'fg': '#e0e0e0',
        'grid': '#3d3d3d',
        'axes_bg': '#1e1e1e',
        'primary': '#64b5f6',
        'secondary': '#ef5350',
        'accent': '#66bb6a',
        'palette': ['#64b5f6', '#ef5350', '#66bb6a', '#ffb74d',
                     '#ce93d8', '#4dd0e1', '#f06292', '#aed581'],
    },
}


def get_mpl_colors(dark: bool = False) -> dict:
    """获取 Matplotlib 配色方案"""
    return MPL_COLORS['dark' if dark else 'light']
