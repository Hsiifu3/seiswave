"""测试 _adjustspectra 的收敛行为 - 更严格的测试"""
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

# 目标谱：一个典型的设计谱形状（和初始谱差异较大）
periods = np.array([0.04, 0.06, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 
                    1.0, 1.5, 2.0, 3.0, 4.0, 5.0])
nP = len(periods)
zeta = 0.05

# 典型设计谱
def design_spectrum(T, pga=1.0):
    """简化的设计谱"""
    sa = np.zeros_like(T)
    for i, t in enumerate(T):
        if t < 0.1:
            sa[i] = pga * (1.0 + 15.0 * t)
        elif t < 0.5:
            sa[i] = pga * 2.5
        else:
            sa[i] = pga * 2.5 * 0.5 / t
    return sa

SPAT = design_spectrum(periods, pga=0.5)
print("目标谱值:", SPAT)

# 先计算当前谱
SPA, SPI = WaveGenerator._spamixed(acc, dt, zeta, periods, nP)
print("初始谱值 (abs):", np.abs(SPA))

# 初始误差
e = (np.abs(SPA) - SPAT) / SPAT
print("初始相对误差:", e)
print("初始 aerror:", np.sqrt(np.mean(e**2)))

# 运行 adjustspectra
def progress(iteration, merror, aerror):
    if iteration <= 10 or iteration % 10 == 0:
        print(f"  iter {iteration:3d}: aerror={aerror:.6f}, merror={merror:.6f}")

result, final_err = WaveGenerator._adjustspectra(
    acc, n, dt, zeta, periods, nP, SPAT, 
    tol=0.02, max_iter=50, progress_callback=progress
)

# 验证结果
SPA_final, _ = WaveGenerator._spamixed(result, dt, zeta, periods, nP)
print("\n最终谱值 (abs):", np.abs(SPA_final))
print("目标谱值:      ", SPAT)
print("相对误差:      ", (np.abs(SPA_final) - SPAT) / SPAT)
print("最终 aerror:", final_err)
