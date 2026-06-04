"""验证: 误差指标里混进了 dt=0.02 下不可表示的短周期点 (T<0.04s)。

复用与 frequency_domain_iteration_report 完全相同的配置 (GB50011 8度2组II类多遇,
n=2000, dt=0.02, 300 点 0.01~6.0s), 跑当前基线 generate(), 然后把 RMS 相对误差
按周期带拆开, 看 T<0.04s (>25Hz, 超 Nyquist) 这批点抬高了多少整体 mean_error。
"""
import os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from seiswave.core import CodeSpectrum, Spectra, WaveGenerator

warnings.filterwarnings("ignore")

# ── 与报告一致的配置 ──
periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
params = CodeSpectrum.get_params(8, 2, "II", "frequent")
sa = CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)
target_pga = float(sa.max())

n, dt, zeta = 2000, 0.02, 0.05
fs = 1.0 / dt
nyq_hz = fs / 2.0
T_nyq = 1.0 / nyq_hz  # 最短可表示周期

print("=" * 68)
print("指标污染验证: GB50011 8度2组II类多遇, n=2000, dt=0.02")
print(f"  fs={fs:.0f}Hz  Nyquist={nyq_hz:.0f}Hz  -> 最短可表示周期 T={T_nyq:.3f}s")
print(f"  周期网格: {periods.min():.3f}~{periods.max():.2f}s, {len(periods)}点")
n_below = int(np.sum(periods < T_nyq))
print(f"  其中 T<{T_nyq:.3f}s (超 Nyquist, 物理上无法匹配): {n_below}/{len(periods)} 点")
print("=" * 68)

# ── 跑当前基线 ──
np.random.seed(42)
sig = WaveGenerator.generate(target_spectrum=sa, periods=periods, n=n, dt=dt,
                             zeta=zeta, pga=target_pga, max_iter=1, fm=1,
                             use_atik=True)
acc = np.asarray(sig.acc if hasattr(sig, "acc") else sig, dtype=np.float64)
resp = Spectra.compute(acc, dt, periods, zeta=zeta, method="mixed").sa


def rms_rel(mask):
    m = mask & (np.abs(sa) > 1e-12)
    if not np.any(m):
        return float("nan"), float("nan"), 0
    e = (resp[m] - sa[m]) / sa[m]
    return float(np.sqrt(np.mean(e ** 2))), float(np.max(np.abs(e))), int(np.sum(m))


bands = [
    ("全周期 0.01-6.0s (报告口径)", periods > 0),
    ("超 Nyquist  T<0.04s (不可表示)", periods < T_nyq),
    ("可表示    T>=0.04s",            periods >= T_nyq),
    ("  -- 短   0.04-0.1s",          (periods >= T_nyq) & (periods < 0.1)),
    ("  -- 中   0.1-0.5s",           (periods >= 0.1) & (periods < 0.5)),
    ("  -- 长   T>=0.5s",            periods >= 0.5),
]
print(f"{'周期带':<30}{'RMS误差':>10}{'max误差':>10}{'点数':>7}")
print("-" * 68)
for name, mask in bands:
    rms, mx, cnt = rms_rel(mask)
    print(f"{name:<30}{rms*100:>9.1f}%{mx*100:>9.1f}%{cnt:>7}")
print("-" * 68)
full, _, _ = rms_rel(periods > 0)
repr_, _, _ = rms_rel(periods >= T_nyq)
print(f"\n结论: 全周期 RMS={full*100:.1f}%  ->  剔除不可表示点后={repr_*100:.1f}%"
      f"  (下降 {(full-repr_)*100:.1f} 个百分点)")
