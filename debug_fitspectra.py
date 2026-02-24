#!/usr/bin/env python3
"""Focused debug of fitspectra iteration"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.spectrum import Spectra
from seiswave.core.generator import WaveGenerator

# GB50011: 8度(0.2g), 第1组, II类场地, 多遇
params = CodeSpectrum.get_params(intensity=8, group=1, site_class="II", level="frequent")
periods = np.array([0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 3.0])
target = CodeSpectrum.gb50011(periods, params['Tg'], params['alpha_max'], zeta=0.05)
pga = params['alpha_max']

print(f"Tg={params['Tg']}, alpha_max={params['alpha_max']}")
print(f"Periods: {periods}")
print(f"Target:  {target}")
print(f"PGA:     {pga}")

# Extended spectrum (same as generator)
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

print(f"\nExtended P:    {P}")
print(f"Extended SPAT: {SPAT}")

# Generate initial signal
n = 2048
dt = 0.02
zeta = 0.05
peak0 = pga

rng = np.random.default_rng(seed=13)
acc = rng.standard_normal(n)
envelope = WaveGenerator._envelope(n, dt)
acc *= envelope
pk = np.max(np.abs(acc))
acc *= peak0 / pk

# Compute initial spectrum
spa, spi = WaveGenerator._spamixed(acc, dt, zeta, P, nP)
print(f"\nInitial SPA (abs): {np.abs(spa)}")
print(f"Initial SPI:       {spi}")

aerror, merror = WaveGenerator._error(np.abs(spa), SPAT, nP)
print(f"Initial aerror={aerror:.4f}, merror={merror:.4f}")

# Check ratio
R = SPAT / np.maximum(np.abs(spa), 1e-30)
print(f"Initial R: {R}")

# Check Pf range
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

print(f"\nnfft={nfft}, n_freqs={n_freqs}")
print(f"ipf1={ipf1}, pf[ipf1]={pf[ipf1]:.4f}")
print(f"ipf2={ipf2}, pf[ipf2]={pf[ipf2]:.4f}")
print(f"P range: [{P[0]:.4f}, {P[-1]:.4f}]")
print(f"Pf range in [ipf1:ipf2]: [{pf[ipf2]:.4f}, {pf[ipf1]:.4f}]")

# Check Rf interpolation
Rf = np.ones(n_freqs)
WaveGenerator._decrlininterp(P, R, nP, pf, Rf, ipf1, ipf2)
print(f"\nRf sample [ipf1..ipf1+5]: {Rf[ipf1:ipf1+6]}")
print(f"Rf sample [ipf2-5..ipf2]: {Rf[ipf2-5:ipf2+1]}")
print(f"Rf min={np.min(Rf[ipf1:ipf2+1]):.4f}, max={np.max(Rf[ipf1:ipf2+1]):.4f}")

# Manual iteration step
a0 = np.zeros(nfft)
a0[:n] = acc
af = np.fft.rfft(a0)

print(f"\n--- Manual iteration 1 ---")
# Apply Rf
af[ipf1:ipf2+1] *= Rf[ipf1:ipf2+1]
a0_out = np.fft.irfft(af.copy(), nfft)
a_new = a0_out[:n].copy()
a_new = WaveGenerator._adjust_peak(a_new, peak0)

spa2, spi2 = WaveGenerator._spamixed(a_new, dt, zeta, P, nP)
aerror2, merror2 = WaveGenerator._error(np.abs(spa2), SPAT, nP)
print(f"After iter 1: aerror={aerror2:.4f}, merror={merror2:.4f}")
print(f"SPA (abs): {np.abs(spa2)}")
print(f"PGA of result: {np.max(np.abs(a_new)):.6f}")

# Check if the spectrum improved
for i in range(nP):
    print(f"  P={P[i]:.3f}: target={SPAT[i]:.4f}, before={np.abs(spa[i]):.4f}, after={np.abs(spa2[i]):.4f}")
