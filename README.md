# EQSignalPy

**地震信号处理与选波工具包 / Seismic Signal Processing & Wave Selection Toolkit**

EQSignalPy 是一个用 Python 编写的地震工程工具包，提供地震信号处理、反应谱计算、规范谱生成、地震波选取和人工波生成等功能。v2.0 基于 EQSignal C++ 库完全重写，并附带 PySide6 桌面 GUI 应用。

EQSignalPy is a Python toolkit for earthquake engineering, providing seismic signal processing, response spectrum computation, code-based design spectrum generation, ground motion selection, and artificial wave generation. v2.0 is a complete rewrite based on the EQSignal C++ library, with a PySide6 desktop GUI.

---

## 功能特性 / Features

- **地震记录 I/O**：支持 AT2（新旧格式）、TXT（单列/双列）、CSV 格式读写与批量加载
- **信号处理**：加速度→速度→位移积分、基线校正（多项式/双线性去趋势）、Butterworth 滤波、裁剪、重采样
- **反应谱计算**：Newmark-β 法、频域法、混合法，支持对数/线性/混合周期分布
- **规范反应谱**：GB 50011 抗震设计谱 + 隔震设计谱，含完整参数表（烈度×分组×场地）
- **地震波选取**：三步筛选（有效持时→主周期偏差→底部剪力校核），支持 SDOF/MDOF 分析
- **人工波生成**：基于目标谱的迭代频域拟合算法（移植自 EQSignal C++ fitSP）
- **FFT / PSD**：傅里叶振幅谱、Welch 功率谱密度、相位谱
- **GUI 桌面应用**：PySide6 界面，含规范谱设置、数据导入、选波、人工波生成、信号处理、导出报告六大面板

---

## 安装 / Installation

### 仅核心库 / Core library only

```bash
pip install -e .
```

### 含 GUI / With GUI

```bash
pip install -e ".[gui]"
```

### 依赖 / Dependencies

- Python >= 3.10
- NumPy >= 1.22
- SciPy >= 1.8
- Matplotlib >= 3.5
- PySide6 >= 6.5（GUI 可选 / optional for GUI）

---

## 快速开始 / Quick Start

### 加载地震记录 / Load a seismic record

```python
from eqsignalpy import FileIO, EQSignal

# 从 AT2 文件加载 / Load from AT2 file
record = FileIO.read_at2("RSN96_MANAGUA_B-ESO090-Acc.txt")
eq = EQSignal(record.acc, record.dt)

# 积分得到速度和位移 / Integrate to get velocity and displacement
eq.a2vd()
print(f"PGA = {eq.pga:.4f} g")
print(f"Duration = {eq.duration:.2f} s")
```

### 计算反应谱 / Compute response spectrum

```python
from eqsignalpy import Spectra

periods = Spectra.default_periods()
sa = Spectra.newmark_beta(eq.acc, eq.dt, periods, zeta=0.05)
```

### 生成规范谱 / Generate code design spectrum

```python
from eqsignalpy import CodeSpectrum

# GB 50011: 8度(0.2g)、第一组、II类场地、多遇
spec = CodeSpectrum.gb50011(
    intensity=8, group=1, site_class="II", level="frequent", damping=0.05
)
```

### 生成人工波 / Generate artificial wave

```python
from eqsignalpy import WaveGenerator, Spectra
import numpy as np

periods = Spectra.default_periods()
target_sa = spec.evaluate(periods)

wave = WaveGenerator.generate(
    target_sa=target_sa, periods=periods,
    dt=0.01, n=4096, pga=0.2, zeta=0.05
)
```

---

## GUI 启动 / Launch GUI

```bash
# 方式一：模块启动 / Module entry
python -m eqsignalpy

# 方式二：命令行入口（安装后）/ Console entry (after install)
eqsignalpy
```

---

## 项目结构 / Project Structure

```
eqsignalpy/
├── eqsignalpy/
│   ├── __init__.py          # 包入口，导出核心类
│   ├── __main__.py          # GUI 启动入口
│   ├── core/                # 核心计算库（无 GUI 依赖）
│   │   ├── signal.py        # EQSignal 信号处理
│   │   ├── spectrum.py      # Spectra 反应谱计算
│   │   ├── code_spec.py     # CodeSpectrum 规范谱
│   │   ├── filter.py        # Filter 滤波与基线校正
│   │   ├── fft.py           # FFT / PSD
│   │   ├── generator.py     # WaveGenerator 人工波生成
│   │   ├── selector.py      # WaveSelector 选波引擎
│   │   ├── response.py      # Response 结构响应分析
│   │   └── io.py            # FileIO 文件读写
│   └── gui/                 # PySide6 桌面应用
│       ├── main_window.py   # 主窗口
│       ├── styles.py        # 深色/浅色主题
│       ├── workers.py       # 后台计算线程
│       ├── panels/          # 功能面板
│       └── widgets/         # 自定义控件
├── tests/                   # 单元测试
├── examples/                # 使用示例
├── matlab_ref/              # MATLAB 参考数据
├── setup.py
└── README.md
```

---

## 许可证 / License

MIT License. See [LICENSE](LICENSE) for details.
