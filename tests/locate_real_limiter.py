"""定位当前真实限制因素 (两个 audit bug 在 working tree 已修, 仍 34%)。

两个假设:
  H1: wavelet 迭代被砍到 max_iter=1, 实际需要多迭代才收敛。
  H2: 内部目标 _errora 含 45 个不可表示点 (T<0.04s), 污染了优化方向;
      只喂可表示控制点给求解器应改善。

做法: 对每个配置跑 generate(), 一律在同一组 255 个可表示点 (T>=0.04) 上评 RMS。
"""
import os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from seiswave.core import CodeSpectrum, Spectra, WaveGenerator

warnings.filterwarnings("ignore")

# 完整评分网格 (固定, 用于所有配置的公平对比)
periods_full = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
params = CodeSpectrum.get_params(8, 2, "II", "frequent")
sa_full = CodeSpectrum.gb50011(periods_full, params["Tg"], params["alpha_max"], zeta=0.05)
target_pga = float(sa_full.max())

n, dt, zeta = 2000, 0.02, 0.05
T_nyq = 2.0 * dt  # 0.04s
repr_mask_full = periods_full >= T_nyq          # 255 点评分集
short = (periods_full >= T_nyq) & (periods_full < 0.1)
mid = (periods_full >= 0.1) & (periods_full < 0.5)
lng = periods_full >= 0.5


def score(acc):
    """在固定 255 点可表示集上评 RMS;并给短/中/长分带。"""
    resp = Spectra.compute(acc, dt, periods_full, zeta=zeta, method="mixed").sa
    def rms(m):
        e = (resp[m] - sa_full[m]) / sa_full[m]
        return float(np.sqrt(np.mean(e ** 2))) * 100
    return rms(repr_mask_full), rms(short), rms(mid), rms(lng)


def run(periods_in, sa_in, max_iter, seed=42):
    np.random.seed(seed)
    sig = WaveGenerator.generate(target_spectrum=sa_in, periods=periods_in, n=n,
                                 dt=dt, zeta=zeta, pga=target_pga,
                                 max_iter=max_iter, fm=1, use_atik=True)
    return np.asarray(sig.acc if hasattr(sig, "acc") else sig, dtype=np.float64)


print("=" * 76)
print("评分: RMS 在 255 个可表示点 (T>=0.04s) 上; 分带 短0.04-0.1 / 中0.1-0.5 / 长>=0.5")
print("=" * 76)
print(f"{'配置':<34}{'可表示':>8}{'短':>8}{'中':>8}{'长':>8}")
print("-" * 76)

periods_repr = periods_full[repr_mask_full]
sa_repr = sa_full[repr_mask_full]

# H1: 全 300 点 (含污染) vs H2: 仅可表示 255 点, 同 max_iter 扫描, 增量打印
for mi in [1, 5, 10, 20]:
    r, s, m, l = score(run(periods_full, sa_full, mi))
    print(f"{'全300点(含污染) max_iter='+str(mi):<34}{r:>7.1f}%{s:>7.1f}%{m:>7.1f}%{l:>7.1f}%", flush=True)
    r, s, m, l = score(run(periods_repr, sa_repr, mi))
    print(f"{'仅可表示255点   max_iter='+str(mi):<34}{r:>7.1f}%{s:>7.1f}%{m:>7.1f}%{l:>7.1f}%", flush=True)
    print("-" * 76, flush=True)
