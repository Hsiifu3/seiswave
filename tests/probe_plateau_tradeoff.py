"""验证 plateau enhancement 对 NFP max_error 与 FF mean 的双向影响。

monkeypatch _init_art_wave 为 HEAD 的 plateau 版, 对比当前(已移除)版:
  - NFP m7.0/m7.2: max_error 能否回到 <=0.18
  - FF: mean_error 损���多少(plateau 当初被移除就是为了改善 FF mean)
"""
import os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import warnings as _w; _w.filterwarnings("ignore")
from seiswave.core import generator as gm
from seiswave.core.generator import WaveGenerator as WG
from seiswave.core import Spectra
from seiswave.core.gmpe import FaultType, GMPEAdapter, MotionType
from seiswave.core import CodeSpectrum

PI = np.pi


def _init_art_wave_plateau(n, dt, zeta, P, SPT, nP, seed=42):
    """HEAD 版: 含 plateau enhancement。"""
    TWO_PI = 2.0 * np.pi
    nfft = WG._nextpow2(n); fs = 1.0 / dt; df = fs / nfft
    f = np.zeros(nfft)
    f[1:nfft//2] = np.arange(1, nfft//2) * df
    f[nfft//2:] = np.arange(-(nfft//2), 0) * df
    n_pf = nfft // 2; Pf = np.zeros(n_pf)
    pos_f = f[1:nfft//2]; Pf[1:n_pf] = 1.0 / pos_f
    Pf[0] = 100.0 * Pf[1] if n_pf > 1 else 1e6
    IPf1 = WG._decrfindfirst(Pf, P[-1]); IPf2 = WG._decrfindlast(Pf, P[0])
    SPTf = np.zeros(nfft // 2)
    SPTf[IPf1:IPf2+1] = WG._decrlininterp_core(P, SPT[:int(nP)], Pf[IPf1:IPf2+1])
    rng = np.random.default_rng(seed=seed)
    af = np.zeros(nfft, dtype=complex)
    max_sptf = float(np.max(SPTf[IPf1:IPf2+1])) if IPf2 >= IPf1 else 0.0
    for k in range(IPf1, IPf2 + 1):
        phi = rng.uniform(0, TWO_PI); wk = TWO_PI * f[k]
        if abs(wk) < 1e-30:
            continue
        log_arg = (-PI / wk / dt / n) * np.log(1.0 - 0.85)
        if 0 < log_arg < 1:
            Saw = (zeta / PI / wk) * SPTf[k]**2 / np.log(1.0 / log_arg)
        else:
            Saw = (zeta / PI / wk) * SPTf[k]**2
        if max_sptf > 0.0:  # ← plateau enhancement
            pr = SPTf[k] / max_sptf
            Saw *= 1.0 + 0.4 / (1.0 + np.exp(-(pr - 0.85) / 0.05))
        Saw = max(Saw, 0.0)
        if not np.isfinite(Saw):
            Saw = 0.0
        Ak = 2.0 * np.sqrt(Saw * TWO_PI * fs * nfft / 2)
        af[k] = Ak * (np.cos(phi) + 1j * np.sin(phi))
        af[nfft - k] = Ak * (np.cos(phi) - 1j * np.sin(phi))
    return np.real(np.fft.ifft(af)[:n])


def nfp_max(Mw, R):
    periods, target = GMPEAdapter.compute_spectrum(Mw=Mw, R=R, Vs30=760.0,
        fault_type=FaultType.STRIKE_SLIP, motion_type=MotionType.NEAR_FIELD_PULSE)
    np.random.seed(0)
    sig = gm.NearFieldPulseGenerator.generate(Mw=Mw, R=R, dt=0.01, n=1024,
        max_iter=15, tol=0.10, Vs30=760.0)
    spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed")
    e = np.abs((spec.sa - target) / np.maximum(np.abs(target), 1e-30))[1:-1]
    return float(np.sqrt(np.mean(e**2))), float(e.max())


def ff_mean():
    periods = Spectra.default_periods(0.04, 6.0, 200, mode="mixed")
    p = CodeSpectrum.get_params(8, 2, "II", "frequent")
    sa = CodeSpectrum.gb50011(periods, p["Tg"], p["alpha_max"], zeta=0.05)
    np.random.seed(42)
    sig = WG.generate(target_spectrum=sa, periods=periods, n=2000, dt=0.02,
        zeta=0.05, pga=float(sa.max()), max_iter=20, fm=1, use_atik=True)
    acc = np.asarray(sig.acc if hasattr(sig, "acc") else sig)
    r = Spectra.compute(acc, 0.02, periods, zeta=0.05, method="mixed").sa
    e = (r - sa) / sa
    return float(np.sqrt(np.mean(e[1:-1]**2)))


orig = WG._init_art_wave
for label, fn in [("当前(plateau已移除)", orig), ("HEAD(plateau保留)", staticmethod(_init_art_wave_plateau).__func__)]:
    WG._init_art_wave = staticmethod(fn)
    m70 = nfp_max(7.0, 4.0); m72 = nfp_max(7.2, 4.0); ffm = ff_mean()
    print(f"{label:<22} NFP m7.0 max={m70[1]:.4f}(限0.19)  m7.2 max={m72[1]:.4f}(限0.18)  "
          f"FF mean={ffm*100:.1f}%", flush=True)
WG._init_art_wave = orig
