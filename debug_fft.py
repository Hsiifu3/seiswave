#!/usr/bin/env python3
"""Check FFT normalization: np.fft.rfft/irfft vs FFTW convention"""
import numpy as np

# FFTW: forward FFT has no normalization, inverse has no normalization
# So round-trip: irfft(rfft(x)) = x * N
# numpy: rfft has no normalization, irfft normalizes by 1/N
# So round-trip: irfft(rfft(x)) = x

n = 8
x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
X = np.fft.rfft(x)
x_back = np.fft.irfft(X, n)
print(f"Original:    {x}")
print(f"Round-trip:  {x_back}")
print(f"Match: {np.allclose(x, x_back)}")

# In EQSignal:
# af = fftw_r2c(a0)  → no normalization
# afs = af
# a0 = fftw_c2r(afs) → no normalization, so a0 = original * Nfft
# a = a0(1:n) * iNfft → a = original * Nfft * (1/Nfft) = original ✓
#
# In Python:
# af = np.fft.rfft(a0)  → no normalization
# a0 = np.fft.irfft(af, nfft) → normalized by 1/N
# a = a0[:n]  → already correct, no need for iNfft ✓
print("\nFFT normalization is correct in Python code.")

# But wait - let's check if rfft/irfft match FFTW r2c/c2r
# FFTW r2c returns Nfft/2+1 complex values (same as rfft)
# FFTW c2r returns Nfft real values (same as irfft)
# The difference is just the 1/N factor in irfft
print("numpy rfft = FFTW r2c (no normalization)")
print("numpy irfft = FFTW c2r * (1/N)")
print("So: np.fft.irfft(af, N) = fftw_c2r(af) / N")
print("EQSignal does: a = fftw_c2r(af) * iNfft = fftw_c2r(af) / N")
print("Python does: a = np.fft.irfft(af, N)")
print("These are equivalent. ✓")
