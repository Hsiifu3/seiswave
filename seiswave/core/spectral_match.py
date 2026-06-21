"""Standalone spectral-matching core."""

from __future__ import annotations

from typing import Callable

import numpy as np


def _match_to_target_impl(
    acc: np.ndarray,
    dt: float,
    periods: np.ndarray,
    target_sa: np.ndarray,
    *,
    zeta: float = 0.05,
    tol: float = 0.05,
    max_iter: int = 20,
    progress_callback: Callable[[int, float, float], None] | None = None,
) -> tuple[np.ndarray, float]:
    """Return the best matched acceleration and its RMS spectral error."""
    from .generator import WaveGenerator

    acc_arr = np.asarray(acc, dtype=np.float64).copy()
    periods_arr = np.asarray(periods, dtype=np.float64).copy()
    target_arr = np.asarray(target_sa, dtype=np.float64).copy()

    if acc_arr.ndim != 1:
        raise ValueError("acc 必须是一维数组")
    if periods_arr.ndim != 1 or target_arr.ndim != 1:
        raise ValueError("periods 和 target_sa 必须是一维数组")
    if len(periods_arr) != len(target_arr):
        raise ValueError("periods 和 target_sa 长度必须一致")
    if len(periods_arr) == 0:
        raise ValueError("target_sa 不能为空")
    if dt <= 0:
        raise ValueError("dt 必须大于 0")

    n = len(acc_arr)
    nP = len(periods_arr)
    peak0 = float(np.max(np.abs(acc_arr)))
    a = acc_arr.copy()

    SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, periods_arr, nP)
    aerror, merror = WaveGenerator._errora(np.abs(SPA), target_arr, nP)

    if aerror <= tol and merror <= 3.0 * tol:
        return a, aerror

    minerr = aerror
    best = a.copy()
    iteration = 1
    stall = 0

    two_pi = 2.0 * np.pi
    nfft_freq = WaveGenerator._nextpow2(n) * 2
    nf = nfft_freq // 2 + 1
    fs = 1.0 / dt
    df_freq = fs / nfft_freq
    wj = np.zeros(nf)
    wj[1:] = two_pi * np.arange(1, nf) * df_freq
    wj2 = wj * wj
    w0_arr = two_pi / periods_arr

    while iteration <= max_iter:
        if aerror <= tol and merror <= 3.0 * tol:
            break

        dR = np.sign(SPA) - SPA / np.maximum(target_arr, 1e-30)

        W = np.zeros((n, nP), dtype=np.float64)
        for i in range(nP):
            W[:, i] = WaveGenerator._wfunc_atik(
                n,
                dt,
                int(SPI[i]),
                float(periods_arr[i]),
                zeta,
            )

        M = np.zeros((nP, nP), dtype=np.float64)
        W_padded = np.zeros((nP, nfft_freq), dtype=np.float64)
        W_padded[:, :n] = W.T
        Wf = np.fft.rfft(W_padded, axis=1)

        spi_idx = SPI - 1
        for i in range(nP):
            w0 = w0_arr[i]
            w0i2 = w0 * w0
            w0iwj = w0 * wj
            denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
            safe = np.abs(denom) > 1e-30
            H = np.ones(nf, dtype=complex)
            H[safe] = (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]

            raf = Wf * H[np.newaxis, :]
            ra_all = np.fft.irfft(raf, nfft_freq, axis=1)

            si = int(spi_idx[i])
            if 0 <= si < n:
                M[i, :] = ra_all[:, si] / max(float(target_arr[i]), 1e-30)
            else:
                M[i, i] = 1.0

        alpha = WaveGenerator._solve_tikhonov(M, dR, lam=10.0)
        alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
        alpha = np.clip(alpha, -1e3, 1e3)

        W_safe = np.nan_to_num(W, nan=0.0, posinf=0.0, neginf=0.0)
        base_delta = W_safe @ alpha
        base_delta = np.nan_to_num(base_delta, nan=0.0, posinf=0.0, neginf=0.0)
        amax = float(np.max(np.abs(base_delta)))
        if amax > 0.5 * peak0 and amax > 0:
            base_delta *= (0.5 * peak0) / amax

        improved = False
        step = 1.0
        for _ls in range(8):
            a_trial = a + step * base_delta
            SPA_t, SPI_t = WaveGenerator._spamixed(a_trial, dt, zeta, periods_arr, nP)
            ae_t, me_t = WaveGenerator._errora(np.abs(SPA_t), target_arr, nP)
            if ae_t < aerror:
                a = a_trial
                SPA, SPI = SPA_t, SPI_t
                aerror, merror = ae_t, me_t
                improved = True
                break
            step *= 0.5

        if progress_callback:
            progress_callback(iteration, merror, aerror)

        if not improved:
            break

        if aerror < minerr - 1e-9:
            minerr = aerror
            best = a.copy()
            stall = 0
        else:
            stall += 1
            if stall >= 3:
                break

        iteration += 1

    return best, minerr


def match_to_target(
    acc: np.ndarray,
    dt: float,
    periods: np.ndarray,
    target_sa: np.ndarray,
    zeta: float = 0.05,
    tol: float = 0.05,
    max_iter: int = 20,
    progress_callback: Callable[[int, float, float], None] | None = None,
) -> np.ndarray:
    """Match an acceleration history to a target spectrum."""
    matched, _ = _match_to_target_impl(
        acc,
        dt,
        periods,
        target_sa,
        zeta=zeta,
        tol=tol,
        max_iter=max_iter,
        progress_callback=progress_callback,
    )
    return matched


__all__ = ["match_to_target"]
