"""直接观察 _adjustspectra_atik 内层迭代的误差轨迹。

假设: wavelet 迭代每步都让误差变大 (叠加后 _adjust_peak 硬裁剪破坏修正),
best-tracking 永远停在第0次(初始波形), 所以加大 max_iter 输出不变。

利用 _adjustspectra_atik 每轮调用的 progress_callback(iter, merror, aerror)
来记录轨迹, 不改源码。
"""
import os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from seiswave.core import CodeSpectrum, Spectra, WaveGenerator as WG

warnings.filterwarnings("ignore")

periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
params = CodeSpectrum.get_params(8, 2, "II", "frequent")
sa = CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)
target_pga = float(sa.max())
n, dt, zeta = 2000, 0.02, 0.05

# 只用可表示控制点 (排除污染)
mask = periods >= 2.0 * dt
P = periods[mask].copy()
SPAT = sa[mask].copy()
nP = len(P)

# 复刻 _generate_python 的初始波形 (init_art_wave + envelope), 不预缩放
nP_ext = nP + 2
P_ext = np.empty(nP_ext); P_ext[0] = P[0]*0.5; P_ext[1:nP+1] = P; P_ext[-1] = P[-1]*1.5
SPAT_ext = np.empty(nP_ext); SPAT_ext[1:nP+1] = SPAT
SPAT_ext[0] = SPAT[0] - (SPAT[1]-SPAT[0])/(P[1]-P[0])*P[0]*0.5
SPAT_ext[-1] = SPAT[-1] + (SPAT[-1]-SPAT[-2])/(P[-1]-P[-2])*P[-1]*0.5

acc0 = WG._init_art_wave(n, dt, zeta, P_ext, SPAT_ext, nP_ext, seed=13)
acc0 = acc0 * WG._resolve_envelope(n, dt, None)
print(f"初始波形 PGA={np.max(np.abs(acc0)):.4f}  target_pga={target_pga:.4f}")

# 初始误差 (内部口径: SPA via _spamixed)
SPA0, _ = WG._spamixed(acc0, dt, zeta, P, nP)
ae0, me0 = WG._errora(np.abs(SPA0), SPAT, nP)
print(f"初始内部误差: aerror={ae0*100:.1f}%  merror={me0*100:.1f}%")
print("-" * 56)
print(f"{'iter':>5}{'aerror':>10}{'merror':>10}")
traj = []
def cb(it, me, ae):
    traj.append((it, ae, me))
    print(f"{it:>5}{ae*100:>9.1f}%{me*100:>9.1f}%", flush=True)

best, minerr = WG._adjustspectra_atik(acc0, n, dt, zeta, P, nP, SPAT,
                                      tol=0.05, max_iter=20, progress_callback=cb)
print("-" * 56)
print(f"返回 minerr={minerr*100:.1f}%  (初始={ae0*100:.1f}%)")
if traj:
    aes = [t[1] for t in traj]
    print(f"迭代中 aerror: min={min(aes)*100:.1f}%  max={max(aes)*100:.1f}%  末={aes[-1]*100:.1f}%")
    print("判定: " + ("迭代从未改进初始波形 (best=初始)" if minerr >= ae0 - 1e-6
                      else f"迭代有改进 {(ae0-minerr)*100:.1f}pt"))
# 验证 best 是否就是 acc0
print(f"best 与初始波形是否相同: {np.allclose(best, WG._adjust_peak(acc0, np.max(np.abs(acc0))))}")
