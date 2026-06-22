# -*- mode: python ; coding: utf-8 -*-
"""SeisWave PyInstaller spec file.

Build examples:
    python -m PyInstaller build.spec --noconfirm --clean
"""

from __future__ import annotations

import sys
from pathlib import Path


APP_NAME = "SeisWave"
ROOT = Path(globals().get("SPECPATH", ".")).resolve()
ENTRY_SCRIPT = ROOT / "seiswave" / "__main__.py"
RESOURCES_DIR = ROOT / "resources"
WINDOWS_ICON = RESOURCES_DIR / "icon.ico"
MACOS_ICON = RESOURCES_DIR / "icon.icns"


def _existing_data_entries() -> list[tuple[str, str]]:
    """仅收集仓库中真实存在的数据文件。"""
    candidates = [
        (ROOT / "README.md", "."),
        (ROOT / "LICENSE", "."),
        (ROOT / "seiswave" / "gui" / "styles" / "theme.qss", "seiswave/gui/styles"),
    ]
    return [(str(path), target) for path, target in candidates if path.exists()]


def _icon_for_platform() -> str | None:
    """返回当前平台可用的图标路径。"""
    if sys.platform.startswith("win") and WINDOWS_ICON.exists():
        return str(WINDOWS_ICON)
    if sys.platform == "darwin" and MACOS_ICON.exists():
        return str(MACOS_ICON)
    return None


HIDDEN_IMPORTS = [
    "numpy",
    "numpy.core._methods",
    "numpy.lib.format",
    "scipy",
    "scipy.fft",
    "scipy.interpolate",
    "scipy.linalg",
    "scipy.signal",
    "matplotlib",
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_pdf",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_svg",
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtSvg",
    "PySide6.QtWidgets",
    "seiswave",
    "seiswave.core",
    "seiswave.core.code_spec",
    "seiswave.core.combiner",
    "seiswave.core.fft",
    "seiswave.core.filter",
    "seiswave.core.generator",
    "seiswave.core.gmpe",
    "seiswave.core.io",
    "seiswave.core.peer_db",
    "seiswave.core.pulse",
    "seiswave.core.reporting",
    "seiswave.core.selector",
    "seiswave.core.signal",
    "seiswave.core.signal_pool",
    "seiswave.core.spectral_match",
    "seiswave.core.spectrum",
    "seiswave.core.target_spectrum",
    "seiswave.gui",
    "seiswave.gui.fonts",
    "seiswave.gui.styles",
    "seiswave.gui.widgets",
    "seiswave.gui.widgets.plot_widget",
    "seiswave.gui.widgets.progress_dialog",
    "seiswave.gui.widgets.spectrum_plot",
    "seiswave.gui.widgets.wave_table",
    "seiswave.gui.workbench",
    "seiswave.gui.workbench.app_window",
    "seiswave.gui.workbench.preview_panel",
    "seiswave.gui.workbench.project_io",
    "seiswave.gui.workbench.scorecard",
    "seiswave.gui.workbench.signal_pool_panel",
    "seiswave.gui.workbench.tool_dock",
    "seiswave.gui.workbench.tools",
    "seiswave.gui.workbench.tools.artificial_tool",
    "seiswave.gui.workbench.tools.auto_select_tool",
    "seiswave.gui.workbench.tools.combine_tool",
    "seiswave.gui.workbench.tools.common",
    "seiswave.gui.workbench.tools.data_export_tool",
    "seiswave.gui.workbench.tools.import_tool",
    "seiswave.gui.workbench.tools.plot_export_tool",
    "seiswave.gui.workbench.tools.signal_process_tool",
    "seiswave.gui.workbench.tools.spectra_tool",
    "seiswave.gui.workbench.tools.spectral_match_tool",
]


a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_existing_data_entries(),
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "PyQt5",
        "PyQt6",
        "_tkinter",
        "cv2",
        "jupyter",
        "notebook",
        "pandas",
        "sklearn",
        "tensorflow",
        "tkinter",
        "torch",
        "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=(sys.platform == "darwin"),
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon_for_platform(),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=_icon_for_platform(),
        bundle_identifier="com.seiswave.workbench",
        info_plist={
            "CFBundleDisplayName": APP_NAME,
            "CFBundleName": APP_NAME,
            "CFBundleShortVersionString": "2.0.0",
            "CFBundleVersion": "2.0.0",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        },
    )
