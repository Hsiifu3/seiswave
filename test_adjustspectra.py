"""测试 _adjustspectra 的收敛行为"""
import numpy as np
import sys
sys.path.insert(0, '.')

from seiswave.core.generator import WaveGenerator

# 生成简单的测试加速度时程
np.random.seed(42)
dt = 0.02
n = 2000
t = np.arange(n) * dt

# 简单的模拟地震波：带包络的白噪声
env = np.exp(-0.1 * (t - 5)**2)
acc = np.random.randn(n) * env * 0.3

# 目标谱：简单的设计谱
periods = np.array([0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0])
nP = len(periods)
zeta = 0.05

# 先计算当前谱
SPA, SPI = WaveGenerator._spamixed(acc, dt, zeta, periods, nP)
print("初始谱值 (abs):", np.abs(SPA))

# 目标谱：在当前谱基础上放大一些
SPAT = np.abs(SPA) * 1.5
print("目标谱值:", SPAT)

# 运行 adjustspectra
def progress(iteration, merror, aerror):
    print(f"  iter {iteration:3d}: aerror={aerror:.6f}, merror={merror:.6f}")

result, final_err = WaveGenerator._adjustspectra(
    acc, n, dt, zeta, periods, nP, SPAT, 
    tol=0.05, max_iter=20, progress_callback=progress
)

# 验证结果
SPA_final, _ = WaveGenerator._spamixed(result, dt, zeta, periods, nP)
print("\n最终谱值 (abs):", np.abs(SPA_final))
print("目标谱值:      ", SPAT)
print("相对误差:      ", (np.abs(SPA_final) - SPAT) / SPAT)
print("最终 aerror:", final_err)
