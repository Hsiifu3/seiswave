"""最小验证：Python 时域法 vs Fortran 时域法对比"""
import time
import numpy as np

# 构造典型目标谱（中国规范 VIII 度 0.20g 简化谱）
periods = np.linspace(0.05, 6.0, 100)
# 简化双折线谱
sa = np.zeros_like(periods)
sa[periods <= 0.1] = 0.45
mask = (periods > 0.1) & (periods <= 0.5)
sa[mask] = 0.45 * (0.1 / periods[mask]) ** 0.9
sa[periods > 0.5] = 0.45 * (0.1 / 0.5) ** 0.9 * (0.5 / periods[periods > 0.5]) ** 1.0
sa = np.clip(sa, 0.05, 2.0)

n = 2000
dt = 0.02
zeta = 0.05
pga = float(max(sa))
tol = 0.05
max_iter = 30

print("=" * 60)
print("验证：Python 时域法 vs Fortran 时域法")
print(f"参数: n={n}, dt={dt}, periods={len(periods)}, max_iter={max_iter}")
print("=" * 60)

from seiswave.core.generator import WaveGenerator
from seiswave.core.spectrum import Spectra

# --- Python 时域法（强制不走 Fortran） ---
import seiswave.core.fortran_bridge as _fb
_orig_hf = _fb.HAS_FORTRAN
_fb.HAS_FORTRAN = False

t0 = time.monotonic()
sig_py = WaveGenerator.generate(
    target_spectrum=sa, periods=periods,
    n=n, dt=dt, zeta=zeta, pga=pga,
    tol=tol, max_iter=max_iter, fm=1,
)
t_py = time.monotonic() - t0

_fb.HAS_FORTRAN = _orig_hf

spec_py = Spectra.compute(sig_py.acc, sig_py.dt, periods, zeta, method="mixed")
e_py = (np.abs(spec_py.sa) - sa) / np.maximum(sa, 1e-30)
rmse_py = float(np.sqrt(np.mean(e_py ** 2)))
maxe_py = float(np.max(np.abs(e_py)))

print(f"\nPython 时域法:")
print(f"  耗时: {t_py:.3f}s")
print(f"  RMS 误差: {rmse_py:.4f} ({rmse_py*100:.2f}%)")
print(f"  Max 误差: {maxe_py:.4f} ({maxe_py*100:.2f}%)")
print(f"  PGA: {float(np.max(np.abs(sig_py.acc))):.4f}g")

# --- Fortran 时域法（通过混合路径） ---
print(f"\nHAS_FORTRAN: {_fb.HAS_FORTRAN}")

t0 = time.monotonic()
sig_f = WaveGenerator.generate(
    target_spectrum=sa, periods=periods,
    n=n, dt=dt, zeta=zeta, pga=pga,
    tol=tol, max_iter=max_iter, fm=1,
)
t_f = time.monotonic() - t0

spec_f = Spectra.compute(sig_f.acc, sig_f.dt, periods, zeta, method="mixed")
e_f = (np.abs(spec_f.sa) - sa) / np.maximum(sa, 1e-30)
rmse_f = float(np.sqrt(np.mean(e_f ** 2)))
maxe_f = float(np.max(np.abs(e_f)))

print(f"\nFortran 时域法:")
print(f"  耗时: {t_f:.3f}s")
print(f"  RMS 误差: {rmse_f:.4f} ({rmse_f*100:.2f}%)")
print(f"  Max 误差: {maxe_f:.4f} ({maxe_f*100:.2f}%)")
print(f"  PGA: {float(np.max(np.abs(sig_f.acc))):.4f}g")
print(f"\n速度比: Python/Fortran = {t_py/t_f:.1f}x")

print("=" * 60)
print("验证完成")
