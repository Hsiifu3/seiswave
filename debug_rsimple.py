#!/usr/bin/env python3
"""Verify rsimple against known values"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from seiswave.core.generator import WaveGenerator

# Test case: pe0=0.5, p0=1.0, phi=0.3, t=5.0, zeta=0.05
pe0, p0, phi, t, zeta = 0.5, 1.0, 0.3, 5.0, 0.05
rs = WaveGenerator._rsimple(pe0, p0, phi, t, zeta)
print(f"rsimple({pe0}, {p0}, {phi}, {t}, {zeta}) = {rs:.10f}")

# Manual Fortran-style computation
TWO_PI = 2.0 * np.pi
we = TWO_PI / pe0
w = TWO_PI / p0
we2 = we*we; w2 = w*w
we3 = we2*we; w3 = w2*w
we4 = we3*we; w4 = w3*w
zeta2 = zeta*zeta; zeta3 = zeta2*zeta; zeta4 = zeta3*zeta
sinphi = np.sin(phi); cosphi = np.cos(phi)

# Direct Fortran formula (single expression)
result_fortran = np.cos(we*t+phi) - np.exp(-w*zeta*t)*((4*w*we3*zeta \
    -4*w*we3*zeta3)*np.exp(w*zeta*t)*np.sin(we*t+phi)+((2*we4 \
    -2*w2*we2)*zeta2-2*we4+2*w2*we2)*np.exp(w*zeta*t)*np.cos(we*t \
    +phi)+np.sqrt(4*w2-4*w2*zeta2)*(4*cosphi*w*we2*zeta3 \
    +2*sinphi*we3*zeta2+(cosphi*w3-3*cosphi*w*we2) \
    *zeta-sinphi*we3+sinphi*w2*we)*np.sin(np.sqrt(4*w2-4*w2 \
    *zeta2)*t/2)+(8*cosphi*w2*we2*zeta4+4*sinphi*w \
    *we3*zeta3+(2*cosphi*w4-10*cosphi*w2*we2)*zeta2-4 \
    *sinphi*w*we3*zeta+2*cosphi*w2*we2-2*cosphi*w4) \
    *np.cos(np.sqrt(4*w2-4*w2*zeta2)*t/2))/(8*w2*we2*zeta4 \
    +(2*we4-12*w2*we2+2*w4)*zeta2-2*we4+4*w2*we2 \
    -2*w4)

print(f"Fortran-style direct = {result_fortran:.10f}")
print(f"Match: {np.isclose(rs, result_fortran)}")

# Test with large t (potential overflow)
t_large = 50.0
rs_large = WaveGenerator._rsimple(pe0, p0, phi, t_large, zeta)
print(f"\nrsimple with t={t_large}: {rs_large:.10f}")
print(f"exp(w*zeta*t) = {np.exp(w*zeta*t_large):.6e}")
print(f"exp(-w*zeta*t) = {np.exp(-w*zeta*t_large):.6e}")

# The Fortran code has exp(-wzt) * exp(wzt) terms that cancel
# But numerically, exp(wzt) can overflow for large t
# Let's check if this causes issues
wzt = w * zeta * t_large
print(f"w*zeta*t = {wzt:.4f}")
