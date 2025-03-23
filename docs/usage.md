# PySignal 使用文档

PySignal 是一个用于地震信号处理的 Python 库，基于 EQSignal C/Fortran 库进行了 Python 化的实现。本文档提供了 PySignal 的基本使用方法。

## 安装

```bash
pip install pysignal
```

## 基本用法

### 导入模块

```python
from pysignal import EQSignal, EQSpectra, Response, Filter
```

### 加载地震记录

可以从文件加载地震记录，或者创建一个新的地震记录：

```python
# 从文件加载
eq = EQSignal.from_file("earthquake_data.txt", dt=0.02)

# 创建新的记录
import numpy as np
acc = np.sin(2 * np.pi * 2 * np.arange(0, 10, 0.01)) * np.exp(-0.1 * np.arange(0, 10, 0.01))
eq = EQSignal(acc, dt=0.01)
```

### 计算速度和位移

```python
eq.acc2vd()  # 计算速度和位移
```

### 绘制时程

```python
eq.plot()  # 绘制加速度、速度和位移时程
```

### 信号处理

```python
# 基线校正
eq_corrected = eq.baseline_correction(order_high=3, order_low=1)

# 滤波
filtered_acc = Filter.butterworth(eq.acc, eq.dt, ftype='bandpass', order=4, freqs=(0.1, 25.0))
eq_filtered = EQSignal(filtered_acc, dt=eq.dt)
eq_filtered.acc2vd()

# 归一化
eq_normalized = eq.normalize(peak_acc=1.0)

# 重采样
eq_resampled = eq.resample(new_dt=0.005)
```

### 计算反应谱

```python
# 使用默认参数计算反应谱（阻尼比5%）
spectra = eq.compute_response_spectrum()

# 指定阻尼比和周期
import numpy as np
periods = np.logspace(-1, 1, 50)  # 从0.1秒到10秒的对数分布
spectra = eq.compute_response_spectrum(zeta=0.02, periods=periods)

# 绘制反应谱
spectra.plot()

# 保存反应谱数据
spectra.save("response_spectrum.csv")
```

### 计算单自由度系统响应

```python
# 线性响应分析
response = eq.response(zeta=0.05, period=1.0)

# 非线性响应分析
response_nl = eq.response(zeta=0.05, period=1.0, mu=2.0)

# 绘制响应
response.plot()

# 绘制滞回曲线
response_nl.plot_hysteresis()

# 计算能量
Ek, Es, Ed, Eh, Ein = response.energy()
```

## 高级用法

### 多阻尼比反应谱比较

```python
import numpy as np
import matplotlib.pyplot as plt

zetas = [0.02, 0.05, 0.10]
periods = np.logspace(-1, 1, 100)

plt.figure(figsize=(10, 6))

for zeta in zetas:
    spectra = EQSpectra(eq, zeta, periods)
    spectra.calc()
    plt.plot(spectra.periods, spectra.SPA, label=f"$\\zeta$ = {zeta:.2f}")

plt.xscale('log')
plt.grid(True)
plt.xlabel("周期 (s)")
plt.ylabel("加速度反应谱 (m/s²)")
plt.title("不同阻尼比的加速度反应谱")
plt.legend()
plt.show()
```

### 不同屈服强度折减系数的非线性响应比较

```python
period = 1.0
mu_values = [1.0, 2.0, 4.0, 8.0]

plt.figure(figsize=(12, 8))

for i, mu in enumerate(mu_values):
    resp = Response(eq, zeta=0.05, period=period)
    if mu == 1.0:
        resp.calc()  # 线性分析
    else:
        resp.calc(mu=mu)  # 非线性分析
    
    plt.subplot(2, 2, i+1)
    plt.plot(resp.rd, resp.rf)
    plt.grid(True)
    plt.xlabel("位移")
    plt.ylabel("恢复力")
    plt.title(f"$\\mu$ = {mu:.1f}")

plt.tight_layout()
plt.show()
```

## 示例

可以在 `examples` 目录下找到更多使用示例。 