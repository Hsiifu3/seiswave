# SeisWave

**地震信号处理与选波工具包 / Seismic Signal Processing & Wave Selection Toolkit**

SeisWave 是一个用 Python 编写的地震工程工具包，提供地震信号处理、反应谱计算、规范谱生成、地震波选取和人工波生成等功能。v2.0 基于 EQSignal C++ 库完全重写，并附带 PySide6 桌面 GUI 应用。

SeisWave is a Python toolkit for earthquake engineering, providing seismic signal processing, response spectrum computation, code-based design spectrum generation, ground motion selection, and artificial wave generation. v2.0 is a complete rewrite based on the EQSignal C++ library, with a PySide6 desktop GUI.

---

## 功能特性 / Features

- **地震记录 I/O**：支持 AT2（新旧格式）、TXT（单列/双列）、CSV 格式读写与批量加载
- **信号处理**：加速度→速度→位移积分、基线校正（多项式/双线性去趋势）、Butterworth 滤波、裁剪、重采样
- **反应谱计算**：Newmark-β 法、频域法、混合法，支持对数/线性/混合周期分布
- **规范反应谱**：GB 50011 抗震设计谱 + 隔震设计谱，含完整参数表（烈度×分组×场地）
- **地震波选取**：三步筛选（有效持时→主周期偏差→底部剪力校核），支持 SDOF/MDOF 分析
- **人工波生成**：基于目标谱的迭代频域拟合算法（移植自 EQSignal C++ fitSP）
- **FFT / PSD**：傅里叶振幅谱、Welch 功率谱密度、相位谱
- **GUI 工作台**：PySide6 三栏工作台，统一接入导入、预览、自动选波、人工波生成、谱拟合、基线校正、滤波、组合校核与导出

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
from seiswave import FileIO, EQSignal

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
from seiswave import Spectra

periods = Spectra.default_periods()
sa = Spectra.newmark_beta(eq.acc, eq.dt, periods, zeta=0.05)
```

### 生成规范谱 / Generate code design spectrum

```python
from seiswave import CodeSpectrum

# GB 50011: 8度(0.2g)、第一组、II类场地、多遇
spec = CodeSpectrum.gb50011(
    intensity=8, group=1, site_class="II", level="frequent", damping=0.05
)
```

### 生成人工波 / Generate artificial wave

```python
from seiswave import WaveGenerator, Spectra
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
# macOS / Linux（仓库内直接启动）
./run.sh

# Windows（仓库内直接启动）
run.bat

# 方式三：模块启动 / Module entry
python -m seiswave

# 方式四：命令行入口（安装后）/ Console entry (after install)
seiswave
```

---

## 项目结构 / Project Structure

```
seiswave/
├── seiswave/
│   ├── __init__.py          # 包入口，导出核心类
│   ├── __main__.py          # 工作台启动入口
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
│       ├── fonts.py         # 跨平台中英文字体封装
│       ├── styles.py        # 工作台主题
│       ├── workbench/       # 三栏工作台主壳与工具
│       ├── workers.py       # 兼容保留的后台任务封装
│       └── widgets/         # 通用绘图/表格控件
├── tests/                   # 单元测试
├── examples/                # 使用示例
├── matlab_ref/              # MATLAB 参考数据
├── run.sh                   # macOS / Linux 启动脚本
├── run.bat                  # Windows 启动脚本
├── setup.py
└── README.md
```

---

## 许可证 / License

MIT License. See [LICENSE](LICENSE) for details.

---

## Claude Code Hooks 异步开发（OpenClaw）

本项目集成了 Claude Code Hooks 机制，实现"派发任务 → 后台执行 → 自动回报"的零轮询异步开发流程：

- **`scripts/dispatch-claude.sh`**：异步派发脚本。接收任务描述后在后台启动 `claude -p`（非交互模式），主进程立即返回不阻塞终端。
- **`.claude/hooks/on-task-complete.sh`**：任务完成钩子。Claude Code 结束时自动触发，将会话 ID、事件类型、时间戳等信息写入结果文件，并唤醒 OpenClaw。
- **`results/latest.json`**（位于 `.claude/results/latest.json`）：每次 Hook 触发后写入的结构化结果快照，包含 `timestamp`、`session_id`、`event`、`status` 等字段，供下游系统读取。
- **`openclaw system event wake`**：Hook 末尾调用 OpenClaw CLI 发送系统事件通知，告知 OpenClaw "Claude Code 任务已完成，请读取 latest.json"，从而驱动后续自动化流程。

典型用法：`./scripts/dispatch-claude.sh "修复人工波生成报错"` — 任务在后台运行，完成后 Hook 自动写结果并唤醒 OpenClaw，全程无需手动轮询。
