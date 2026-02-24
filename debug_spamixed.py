#!/usr/bin/env python3
"""Check spamixed vs Spectra.compute discrepancy"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from seiswave.core.spectrum import Spectra
from seiswave.core.generator import WaveGenerator

# Simple test signal
n = 2048
dt = 0.02
rng = np.random.default_rng(42)
acc = rng.standard_normal(n) * 0.1
envelope = WaveGenerator._envelope(n, dt)
acc *= envelope

periods = np.array([0.04, 0.1, 0.2, 0.4, 0.5, 1.0, 2.0, 4.0])
nP = len(periods)
zeta = 0.05

# spamixed
spa_mixed, spi_mixed = WaveGenerator._spamixed(acc, dt, zeta, periods, nP)

# Spectra.compute (newmark only)
spec_nmk = Spectra.compute(acc, dt, periods, zeta=zeta, method="newmark")

# Spectra.compute (mixed)
spec_mix = Spectra.compute(acc, dt, periods, zeta=zeta, method="mixed")

print(f"MPR*dt = {WaveGenerator.MPR * dt}")
print(f"{'Period':>8s} {'spamixed':>12s} {'nmk_Sa':>12s} {'mix_Sa':>12s} {'ratio_nmk':>10s} {'ratio_mix':>10s}")
for i in range(nP):
    r_nmk = abs(spa_mixed[i]) / spec_nmk.sa[i] if spec_nmk.sa[i] > 0 else 0
    r_mix = abs(spa_mixed[i]) / spec_mix.sa[i] if spec_mix.sa[i] > 0 else 0
    print(f"{periods[i]:8.3f} {abs(spa_mixed[i]):12.6f} {spec_nmk.sa[i]:12.6f} {spec_mix.sa[i]:12.6f} {r_nmk:10.4f} {r_mix:10.4f}")
