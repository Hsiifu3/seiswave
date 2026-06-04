"""端到端验证修复后的 generate(): 可表示带 RMS vs 34% 基线。"""
import os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from seiswave.core import CodeSpectrum, Spectra, WaveGenerator

warnings.filterwarnings("ignore")

periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
params = CodeSpectrum.get_params(8, 2, "II", "frequent")
sa = CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)
target_pga = float(sa.max())
n, dt, zeta = 2000, 0.02, 0.05
T_nyq = 2.0 * dt
repr_mask = periods >= T_nyq
short = (periods >= T_nyq) & (periods < 0.1)
mid = (periods >= 0.1) & (periods < 0.5)
lng = periods >= 0.5


def score(acc):
    resp = Spectra.compute(acc, dt, periods, zeta=zeta, method="mixed").sa
    def rms(m):
        e = (resp[m] - sa[m]) / sa[m]
        return float(np.sqrt(np.mean(e ** 2))) * 100
    return rms(repr_mask), rms(short), rms(mid), rms(lng), float(np.max(np.abs(acc)))


def run(periods_in, sa_in, mi, seed=42):
    np.random.seed(seed)
    sig = WaveGenerator.generate(target_spectrum=sa_in, periods=periods_in, n=n, dt=dt,
                                 zeta=zeta, pga=target_pga, max_iter=mi, fm=1, use_atik=True)
    return np.asarray(sig.acc if hasattr(sig, "acc") else sig, dtype=np.float64)


print("评分: RMS@可表示255点(T>=0.04); 分带 短/中/长; PGA  | target_pga=%.4f" % target_pga)
print("基线(修复前) 全300 max_iter=1: 可表示34.0 短70.5 中34.1 长22.1")
print("-" * 72)
print(f"{'配置':<30}{'可表示':>7}{'短':>7}{'中':>7}{'长':>7}{'PGA':>8}")
for mi in [5, 15, 30]:
    r, s, m, l, pk = score(run(periods, sa, mi))
    print(f"{'全300点      max_iter='+str(mi):<30}{r:>6.1f}%{s:>6.1f}%{m:>6.1f}%{l:>6.1f}%{pk:>8.4f}", flush=True)
print("-" * 72)
periods_r = periods[repr_mask]; sa_r = sa[repr_mask]
for mi in [5, 15, 30]:
    r, s, m, l, pk = score(run(periods_r, sa_r, mi))
    print(f"{'仅可表示255点 max_iter='+str(mi):<30}{r:>6.1f}%{s:>6.1f}%{m:>6.1f}%{l:>6.1f}%{pk:>8.4f}", flush=True)
