# EQSignalPy - 地震信号处理Python库

EQSignalPy是对EQSignal库的Python封装，提供了地震信号处理的各种功能。该库使用Python重新实现了原C/Fortran库的核心功能，更易于集成到现代数据分析工作流程中。

## 功能特点

- **地震记录处理**：读取、写入多种格式的地震记录，支持基线校正和单位转换
- **时程分析**：计算加速度、速度和位移时程，支持自定义滤波
- **频谱分析**：计算傅里叶振幅谱、功率谱和相位谱
- **反应谱计算**：支持加速度、速度和位移反应谱计算，可自定义阻尼比
- **结构响应分析**：支持线性和非线性结构响应分析
- **滤波功能**：包含多种滤波器（巴特沃斯、切比雪夫等）
- **人工地震波生成**：基于目标反应谱生成人工地震波

## 安装

### 从GitHub安装

```bash
# 克隆仓库
git clone https://github.com/hsiifu3/eqsignalpy.git

# 进入项目目录
cd eqsignalpy

# 安装依赖
pip install -r requirements.txt

# 安装库（开发模式）
pip install -e .
```

### 依赖项

- NumPy >= 1.19.0
- Matplotlib >= 3.3.0
- SciPy >= 1.5.0

## 主要模块

EQSignalPy包含以下主要模块：

- `EQSignal`: 地震信号处理的核心类，包含时程处理和分析功能
- `EQSpectra`: 反应谱计算和分析
- `Response`: 结构响应分析，包括线性和非线性响应
- `Filter`: 各种滤波算法的实现
- `EQGenerator`: 人工地震波生成工具

## 使用示例

### 基本地震记录处理

```python
import numpy as np
from eqsignalpy import EQSignal

# 从文件加载地震记录
eq = EQSignal.from_file("earthquake_data.txt", dt=0.02)

# 基线校正
eq.baseline_correction()

# 计算速度和位移
eq.acc2vd()

# 绘制三种时程曲线
eq.plot(title="地震记录时程曲线")
```

### 反应谱计算

```python
from eqsignalpy import EQSignal, EQSpectra

# 加载地震记录
eq = EQSignal.from_file("earthquake_data.txt", dt=0.02)

# 计算反应谱（阻尼比5%）
spectra = eq.compute_response_spectrum(zeta=0.05)

# 设置绘图参数
spectra.plot(logx=True, grid=True, title="5%阻尼比反应谱")

# 保存反应谱数据
spectra.save("response_spectrum.csv")
```

### 人工地震波生成

```python
import numpy as np
import matplotlib.pyplot as plt
from eqsignalpy import EQGenerator

# 生成设计反应谱
periods = np.logspace(-1, 1, 100)
design_spectrum = EQGenerator.generate_design_spectrum(
    periods, site_class='II', pga=0.2, damping=0.05
)

# 基于设计反应谱生成人工地震波
eq_wave = EQGenerator.generate_from_spectrum(
    design_spectrum, n=4096, dt=0.01, zeta=0.05
)

# 绘制生成的地震波
eq_wave.plot(title="人工生成的地震波")

# 比较目标反应谱和生成波的反应谱
plt.figure(figsize=(10, 6))
plt.loglog(periods, design_spectrum, 'r-', label='目标反应谱')
actual_spectrum = eq_wave.compute_response_spectrum(zeta=0.05)
plt.loglog(actual_spectrum.period, actual_spectrum.psa, 'b--', label='实际反应谱')
plt.grid(True)
plt.legend()
plt.xlabel('周期 (s)')
plt.ylabel('谱加速度 (g)')
plt.title('反应谱比较')
plt.show()
```

## 如何贡献

欢迎对EQSignalPy项目做出贡献！

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m '添加了某功能'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交Pull Request


## 致谢

感谢原EQSignal项目的开发者提供了宝贵的算法和思路。 
