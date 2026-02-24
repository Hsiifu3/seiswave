#!/usr/bin/env python3
"""Debug iteration divergence with full 50-period test"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.spectrum import Spectra
from seiswave.core.generator import WaveGenerator

params = CodeSpectrum.get_params(intensity=8, group=1, site_class="II", level="frequent")
periods = Spectra.default_periods(0.04, 6.0, 50, mode="mixed")
target = CodeSpectrum.gb50011(periods, params['Tg'], params['alpha_max'], zeta=0.05)
pga = params['alpha_max']

# Extended spectrum
nP_orig = len(periods)
nP = nP_orig + 2
P = np.empty(nP)
P[0] = periods[0] * 0.5
P[1:nP_orig+1] = periods
P[nP_orig+1] = periods[-1] * 1.5

SPAT = np.empty(nP)
SPAT[1:nP_orig+1] = target
SPAT[0] = target[0] - (target[1] - target[0]) / (periods[1] - periods[0]) * periods[0] * 0.5
SPAT[nP_orig+1] = target[-1] + (target[-1] - target[-2]) / (periods[-1] - periods[-2]) * periods[-1] * 0.5

n = 2048
dt = 0.02
zeta = 0.05
peak0 = pga

nfft = (1 << int(np.ceil(np.log2(n)))) * 4
freqs = np.fft.rfftfreq(nfft, dt)
n_freqs = len(freqs)
pf = np.zeros(n_freqs)
pf[1:] = 1.0 / freqs[1:]
pf[0] = 2.0 * pf[1]

ipf1 = 1
for i in range(1, n_freqs):
    if pf[i] <= P[-1]:
        ipf1 = i
        break
ipf2 = n_freqs - 1
for i in range(n_freqs - 1, 0, -1):
    if pf[i] >= P[0]:
        ipf2 = i
        break

print(f"nP={nP}, ipf1={ipf1} (pf={pf[ipf1]:.4f}), ipf2={ipf2} (pf={pf[ipf2]:.4f})")
print(f"P range: [{P[0]:.4f}, {P[-1]:.4f}]")

# Generate initial signal
rng = np.random.default_rng(seed=13)
acc = rng.standard_normal(n)
envelope = WaveGenerator._envelope(n, dt)
acc *= envelope
pk = np.max(np.abs(acc))
acc *= peak0 / pk

a = acc.copy()
a0 = np.zeros(nfft)
a0[:n] = a
af = np.fft.rfft(a0)

# Initial spectrum
spa, spi = WaveGenerator._spamixed(a, dt, zeta, P, nP)
aerror, merror = WaveGenerator._error(np.abs(spa), SPAT, nP)
print(f"Initial: aerror={aerror:.4f}, merror={merror:.4f}")

R = SPAT / np.maximum(np.abs(spa), 1e-30)
Rf = np.ones(n_freqs)
WaveGenerator._decrlininterp(P, R, nP, pf, Rf, ipf1, ipf2)

print(f"R range: [{R.min():.4f}, {R.max():.4f}]")
print(f"Rf range: [{Rf[ipf1:ipf2+1].min():.4f}, {Rf[ipf1:ipf2+1].max():.4f}]")

# Run 5 iterations manually
for it in range(1, 11):
    # rsimple sign check
    j = ipf2
    n_flipped = 0
    for i in range(1, nP - 1):
        p0 = P[i]
        t_peak = dt * spi[i] - dt
        dp = min(p0 - P[i-1], P[i+1] - p0)
        while j > ipf1 and pf[j] < p0 + 0.5 * dp:
            pe0 = pf[j]
            phi = np.arctan2(af[j].imag, af[j].real)
            rs = WaveGenerator._rsimple(pe0, p0, phi, t_peak, zeta)
            if np.sign(rs) * np.sign(spa[i]) < 0:
                Rf[j] = 1.0 / Rf[j]
                n_flipped += 1
            j -= 1

    print(f"\nIter {it}: rsimple flipped {n_flipped} frequencies")
    
    # Apply Rf
    af[ipf1:ipf2+1] *= Rf[ipf1:ipf2+1]
    
    # IFFT
    a0_out = np.fft.irfft(af.copy(), nfft)
    a = a0_out[:n].copy()
    
    # adjustpeak
    a = WaveGenerator._adjust_peak(a, peak0)
    
    # Recompute spectrum
    spa, spi = WaveGenerator._spamixed(a, dt, zeta, P, nP)
    aerror, merror = WaveGenerator._error(np.abs(spa), SPAT, nP)
    
    R = SPAT / np.maximum(np.abs(spa), 1e-30)
    Rf = np.ones(n_freqs)
    WaveGenerator._decrlininterp(P, R, nP, pf, Rf, ipf1, ipf2)
    
    print(f"  aerror={aerror:.4f}, merror={merror:.4f}")
    print(f"  R range: [{R.min():.4f}, {R.max():.4f}]")
    print(f"  Rf range: [{Rf[ipf1:ipf2+1].min():.4f}, {Rf[ipf1:ipf2+1].max():.4f}]")
    print(f"  PGA={np.max(np.abs(a)):.6f}")
    
    # Show worst periods
    abs_spa = np.abs(spa)
    rel_err = np.abs(abs_spa - SPAT) / SPAT
    worst = np.argsort(rel_err)[-3:]
    for w in worst:
        print(f"  Worst: P={P[w]:.4f}, target={SPAT[w]:.4f}, actual={abs_spa[w]:.4f}, err={rel_err[w]:.2%}")
