# EQSignalPy - 地震信号处理Python库

EQSignalPy是对EQSignal库的Python封装，提供了地震信号处理的各种功能。

## 功能特点

- 地震加速度记录处理
- 地震反应谱计算
- 时程分析
- 频谱分析
- 地震信号滤波
- 非线性分析
- 人工地震波生成

## 安装

```bash
pip install eqsignalpy
```

## 使用示例

```python
import numpy as np
from eqsignalpy import EQSignal

# 从文件加载地震记录
eq = EQSignal.from_file("earthquake_data.txt", dt=0.02)

# 计算速度和位移
eq.acc2vd()

# 计算反应谱
spectra = eq.compute_response_spectrum(zeta=0.05)

# 绘制反应谱
spectra.plot()
```

## 依赖项

- NumPy
- Matplotlib
- SciPy

## 许可证

与原EQSignal项目相同的许可证 