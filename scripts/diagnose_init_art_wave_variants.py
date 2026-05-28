import json
import math
from contextlib import contextmanager

import numpy as np

from seiswave.core.generator import WaveGenerator
from seiswave.core.spectrum import Spectra
from seiswave.core.code_spec import CodeSpectrum


periods300 = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
sa300 = CodeSpectrum.gb50011(periods300, Tg=0.35, alpha_max=0.16, zeta=0.05)


def build_ext(periods, target):
    nP_orig = len(periods)
    nP_ext = nP_orig + 2
    P_ext = np.empty(nP_ext)
    P_ext[0] = periods[0] * 0.5
    P_ext[1:nP_orig + 1] = periods
    P_ext[nP_orig + 1] = periods[-1] * 1.5
    SPAT_ext = np.empty(nP_ext)
    SPAT_ext[1:nP_orig + 1] = target
    SPAT_ext[0] = target[0] - (target[1] - target[0]) / (periods[1] - periods[0]) * periods[0] * 0.5
    SPAT_ext[nP_orig + 1] = target[-1] + (target[-1] - target[-2]) / (periods[-1] - periods[-2]) * periods[-1] * 0.5
    return P_ext, SPAT_ext, nP_ext


P_ext, SPAT_ext, nP_ext = build_ext(periods300, sa300)


@contextmanager
def patch_variant(config):
    orig = WaveGenerator._init_art_wave

    def patched(n, dt, zeta, P, SPT, nP, seed=42):
        nfft = WaveGenerator._nextpow2(n)
        fs = 1.0 / dt
        df = fs / nfft
        TWO_PI = 2.0 * np.pi
        PI = np.pi

        f = np.zeros(nfft)
        f[1:nfft//2] = np.arange(1, nfft//2) * df
        f[nfft//2:] = np.arange(-(nfft//2), 0) * df

        n_pf = nfft // 2
        Pf = np.zeros(n_pf)
        pos_f = f[1:nfft//2]
        Pf[1:n_pf] = 1.0 / pos_f
        Pf[0] = 100.0 * Pf[1] if n_pf > 1 else 1e6

        IPf1 = WaveGenerator._decrfindfirst(Pf, P[-1])
        IPf2 = WaveGenerator._decrfindlast(Pf, P[0])

        SPTf = np.zeros(nfft // 2)
        SPTf[IPf1:IPf2+1] = WaveGenerator._decrlininterp_core(P, SPT[:int(nP)], Pf[IPf1:IPf2+1])

        rng = np.random.default_rng(seed=seed)
        af = np.zeros(nfft, dtype=complex)

        max_sptf = float(np.max(SPTf[IPf1:IPf2+1])) if IPf2 >= IPf1 else 0.0
        for k in range(IPf1, IPf2 + 1):
            phi = rng.uniform(0, TWO_PI)
            wk = TWO_PI * f[k]
            if abs(wk) < 1e-30:
                continue
            log_arg = (-PI / wk / dt / n) * np.log(1.0 - 0.85)
            if log_arg > 0 and log_arg < 1:
                Saw = (zeta / PI / wk) * SPTf[k]**2 / np.log(1.0 / log_arg)
            else:
                Saw = (zeta / PI / wk) * SPTf[k]**2
            Saw = max(Saw, 0.0)

            mode = config["mode"]
            if mode == "tilt":
                w_ref = config["w_ref"]
                alpha = config["alpha"]
                ratio = max(wk / w_ref, 1e-12)
                weight = ratio ** alpha
                weight = float(np.clip(weight, config.get("clip_min", 0.6), config.get("clip_max", 2.5)))
                Saw *= weight
            elif mode == "plateau":
                boost = config["boost"]
                sharpness = config.get("sharpness", 0.05)
                x = 0.0 if max_sptf <= 0 else SPTf[k] / max_sptf
                weight = 1.0 + boost / (1.0 + np.exp(-(x - 0.85) / sharpness))
                Saw *= float(weight)
            elif mode == "combo":
                w_ref = config["w_ref"]
                alpha = config["alpha"]
                ratio = max(wk / w_ref, 1e-12)
                weight = ratio ** alpha
                weight = float(np.clip(weight, config.get("clip_min", 0.6), config.get("clip_max", 2.5)))
                x = 0.0 if max_sptf <= 0 else SPTf[k] / max_sptf
                boost = config.get("boost", 0.15)
                smooth = 1.0 + boost / (1.0 + np.exp(-(x - 0.85) / config.get("sharpness", 0.05)))
                Saw *= weight * smooth
            elif mode == "baseline":
                pass
            else:
                raise ValueError(mode)

            if not np.isfinite(Saw):
                Saw = 0.0
            Ak = 2.0 * np.sqrt(Saw * TWO_PI * fs * nfft / 2)
            af[k] = Ak * (np.cos(phi) + 1j * np.sin(phi))
            af[nfft - k] = Ak * (np.cos(phi) - 1j * np.sin(phi))

        a0 = np.fft.ifft(af)
        return np.real(a0[:n])

    WaveGenerator._init_art_wave = staticmethod(patched)
    try:
        yield
    finally:
        WaveGenerator._init_art_wave = orig


def eval_variant(config):
    with patch_variant(config):
        acc = WaveGenerator._init_art_wave(2000, 0.02, 0.05, P_ext, SPAT_ext, nP_ext, seed=13)
        spec = Spectra.compute(acc, 0.02, periods300, 0.05, method="mixed")
        fit0 = WaveGenerator.fit_error(spec.sa, sa300)
        out = {
            "name": config["name"],
            "init_pga": float(np.max(np.abs(acc))),
            "init_mean_error": float(fit0["mean_error"]),
            "init_max_error": float(fit0["max_error"]),
        }

        sig = WaveGenerator.generate(
            target_spectrum=sa300, periods=periods300,
            n=2000, dt=0.02, zeta=0.05, pga=float(sa300.max()),
            tol=0.05, max_iter=30, fm=1, n_trials=1,
        )
        spec2 = Spectra.compute(sig.acc, sig.dt, periods300, 0.05, method="mixed")
        fit1 = WaveGenerator.fit_error(spec2.sa, sa300)
        out.update({
            "final_mean_error": float(fit1["mean_error"]),
            "final_max_error": float(fit1["max_error"]),
        })
        return out


w_ref = 2.0 * math.pi / 0.15
variants = [
    {"name": "baseline", "mode": "baseline"},
    {"name": "tilt_a025", "mode": "tilt", "w_ref": w_ref, "alpha": 0.25, "clip_min": 0.7, "clip_max": 2.0},
    {"name": "tilt_a05", "mode": "tilt", "w_ref": w_ref, "alpha": 0.5, "clip_min": 0.6, "clip_max": 2.5},
    {"name": "tilt_a075", "mode": "tilt", "w_ref": w_ref, "alpha": 0.75, "clip_min": 0.5, "clip_max": 3.0},
    {"name": "plateau_b025", "mode": "plateau", "boost": 0.25, "sharpness": 0.05},
    {"name": "combo_a05_b015", "mode": "combo", "w_ref": w_ref, "alpha": 0.5, "clip_min": 0.6, "clip_max": 2.5, "boost": 0.15, "sharpness": 0.05},
]

results = [eval_variant(v) for v in variants]
print(json.dumps(results, ensure_ascii=False, indent=2))
