"""
EQSignalPy基本使用示例
"""

import numpy as np
import matplotlib.pyplot as plt
from eqsignalpy import EQSignal, EQSpectra, Filter

# 创建一个简单的人工地震记录
def create_artificial_eq_record(n=2000, dt=0.01):
    """创建一个简单的人工地震记录"""
    t = np.arange(n) * dt
    # 创建一个包络函数
    envelope = np.exp(-0.5 * ((t - 10) / 5) ** 2)
    
    # 创建一个频率从2Hz增加到5Hz的正弦波
    freq = 2 + 3 * t / (n * dt)
    sine_wave = np.sin(2 * np.pi * freq * t)
    
    # 创建地震记录
    acc = envelope * sine_wave
    return acc

def main():
    # 创建人工地震记录
    acc = create_artificial_eq_record()
    eq = EQSignal(acc, dt=0.01)
    
    # 计算速度和位移
    eq.acc2vd()
    
    # 绘制时程
    eq.plot(title="人工地震记录")
    
    # 计算反应谱
    spectra = eq.compute_response_spectrum(zeta=0.05)
    
    # 绘制反应谱
    spectra.plot()
    
    # 使用滤波器
    filtered_acc = Filter.butterworth(eq.acc, eq.dt, ftype='bandpass', order=4, freqs=(0.5, 10.0))
    filtered_eq = EQSignal(filtered_acc, dt=eq.dt)
    filtered_eq.acc2vd()
    
    # 绘制滤波后的结果
    filtered_eq.plot(title="滤波后的地震记录")
    
    # 计算单自由度系统响应
    response = eq.response(zeta=0.05, period=1.0)
    response.plot()
    
    # 绘制滞回曲线
    response_nl = eq.response(zeta=0.05, period=1.0, mu=2.0)
    response_nl.plot_hysteresis()

if __name__ == "__main__":
    main() 