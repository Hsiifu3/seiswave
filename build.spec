# -*- mode: python ; coding: utf-8 -*-
"""
SeisWave PyInstaller spec file
Build: python -m PyInstaller build.spec
"""

import sys
import os
from pathlib import Path

block_cipher = None

# Project root
ROOT = os.path.abspath(os.path.dirname(SPECPATH if 'SPECPATH' in dir() else '.'))

a = Analysis(
    [os.path.join(ROOT, 'seiswave', '__main__.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        # NumPy
        'numpy',
        'numpy.core._methods',
        'numpy.lib.format',
        # SciPy
        'scipy',
        'scipy.signal',
        'scipy.fft',
        'scipy.interpolate',
        'scipy.linalg',
        # Matplotlib backends
        'matplotlib',
        'matplotlib.backends.backend_agg',
        'matplotlib.backends.backend_svg',
        'matplotlib.backends.backend_pdf',
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.backends.backend_qtagg',
        # PySide6
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        # SeisWave modules
        'seiswave',
        'seiswave.core',
        'seiswave.core.signal',
        'seiswave.core.spectrum',
        'seiswave.core.filter',
        'seiswave.core.generator',
        'seiswave.core.io',
        'seiswave.core.code_spec',
        'seiswave.core.selector',
        'seiswave.core.fft',
        'seiswave.core.response',
        'seiswave.gui',
        'seiswave.gui.main_window',
        'seiswave.gui.styles',
        'seiswave.gui.workers',
        'seiswave.gui.panels',
        'seiswave.gui.panels.spectrum_panel',
        'seiswave.gui.panels.import_panel',
        'seiswave.gui.panels.selector_panel',
        'seiswave.gui.panels.generator_panel',
        'seiswave.gui.panels.signal_panel',
        'seiswave.gui.panels.result_panel',
        'seiswave.gui.widgets',
        'seiswave.gui.widgets.plot_widget',
        'seiswave.gui.widgets.spectrum_plot',
        'seiswave.gui.widgets.wave_table',
        'seiswave.gui.widgets.progress_dialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Unused toolkits
        'tkinter',
        '_tkinter',
        'PyQt5',
        'PyQt6',
        'wx',
        # Unused heavy packages
        'IPython',
        'jupyter',
        'notebook',
        'pandas',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
        'sklearn',
        # Test frameworks
        'pytest',
        'unittest',
        'doctest',
        # Dev tools
        'setuptools',
        'pip',
        'wheel',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Icon path (use if exists)
icon_file = None
if sys.platform == 'win32':
    ico = os.path.join(ROOT, 'resources', 'icon.ico')
    if os.path.exists(ico):
        icon_file = ico
elif sys.platform == 'darwin':
    icns = os.path.join(ROOT, 'resources', 'icon.icns')
    if os.path.exists(icns):
        icon_file = icns

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SeisWave',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SeisWave',
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='SeisWave.app',
        icon=icon_file,
        bundle_identifier='com.seiswave.app',
        info_plist={
            'CFBundleName': 'SeisWave',
            'CFBundleDisplayName': 'SeisWave',
            'CFBundleVersion': '2.0.0',
            'CFBundleShortVersionString': '2.0.0',
            'NSHighResolutionCapable': True,
        },
    )
