import csv
from pathlib import Path

import numpy as np

from seiswave.core import CodeSpectrum, Spectra, WaveGenerator
from seiswave.core.gmpe import FaultType, GMPEAdapter, MotionType
from seiswave.core.generator import (
    FarFieldGenerator,
    NearFieldNoPulseGenerator,
    NearFieldPulseGenerator,
)
from seiswave.core.pulse import BakerPulseDetector

OUT_CSV = Path("/tmp/seiswave_batch_validation.csv")
OUT_MD = Path("/tmp/seiswave_batch_validation.md")


def fit_against_target(sig, *, Mw, R, motion_type, Vs30=760.0):
    periods, target_sa = GMPEAdapter.compute_spectrum(
        Mw=Mw,
        R=R,
        Vs30=Vs30,
        fault_type=FaultType.STRIKE_SLIP,
        motion_type=motion_type,
    )
    spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed")
    fit = WaveGenerator.fit_error(spec.sa, target_sa)
    return periods, target_sa, fit


def validate_general():
    rows = []
    periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
    supported = 0
    skipped = 0
    for level in ["frequent", "design", "rare"]:
        for category in ["I0", "I", "II", "III", "IV"]:
            for group in [1, 2, 3]:
                for intensity in [6, 7, 8, 9]:
                    try:
                        params = CodeSpectrum.get_params(intensity, group, category, level)
                    except (ValueError, KeyError):
                        skipped += 1
                        rows.append({
                            "suite": "general",
                            "case": f"{intensity}-{group}-{category}-{level}",
                            "status": "skipped",
                            "reason": "unsupported combination",
                        })
                        continue
                    supported += 1
                    target_sa = CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)
                    target_pga = float(target_sa.max())
                    sig = WaveGenerator.generate(
                        target_spectrum=target_sa,
                        periods=periods,
                        n=2000,
                        dt=0.02,
                        zeta=0.05,
                        pga=target_pga,
                        tol=0.05,
                        max_iter=30,
                        fm=1,
                        n_trials=1,
                    )
                    spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed")
                    fit = WaveGenerator.fit_error(spec.sa, target_sa)
                    gen_pga = float(np.max(np.abs(sig.acc)))
                    pga_rel = abs(gen_pga - target_pga) / max(target_pga, 1e-12)
                    passed = (fit["mean_error"] <= 0.80 and fit["max_error"] <= 2.50 and pga_rel <= 0.05)
                    rows.append({
                        "suite": "general",
                        "case": f"{intensity}-{group}-{category}-{level}",
                        "status": "passed" if passed else "failed",
                        "mean_error": fit["mean_error"],
                        "max_error": fit["max_error"],
                        "target_pga": target_pga,
                        "gen_pga": gen_pga,
                        "pga_rel": pga_rel,
                    })
    return rows, supported, skipped


def validate_special(generator_cls, motion_type, name, cases, velocity_scale, mean_limit, max_limit, expect_pulse, conf_limit=None):
    rows = []
    for Mw, R, Vs30 in cases:
        sig = generator_cls.generate(
            Mw=Mw, R=R, Vs30=Vs30,
            n=1024 if name != "nfp" else 1024,
            dt=0.02 if name != "nfp" else 0.01,
            zeta=0.05,
            max_iter=15,
            tol=0.10,
        )
        _, target_sa, fit = fit_against_target(sig, Mw=Mw, R=R, motion_type=motion_type, Vs30=Vs30)
        metrics = BakerPulseDetector.analyze(sig.vel * velocity_scale, sig.dt)
        gen_pga = float(np.max(np.abs(sig.acc)))
        target_peak = float(np.max(target_sa))
        pga_ratio = gen_pga / max(target_peak, 1e-12)
        passed = (
            fit["mean_error"] <= mean_limit
            and fit["max_error"] <= max_limit
            and metrics["has_pulse"] is expect_pulse
            and 0.30 <= pga_ratio <= 3.00
        )
        if expect_pulse and conf_limit is not None:
            passed = passed and metrics["confidence"] >= conf_limit
        rows.append({
            "suite": name,
            "case": f"Mw{Mw}-R{R}-Vs30{Vs30}",
            "status": "passed" if passed else "failed",
            "mean_error": fit["mean_error"],
            "max_error": fit["max_error"],
            "gen_pga": gen_pga,
            "target_peak": target_peak,
            "pga_ratio": pga_ratio,
            "pulse": metrics["has_pulse"],
            "confidence": metrics["confidence"],
        })
    return rows


def write_outputs(rows):
    fieldnames = sorted({k for row in rows for k in row.keys()})
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    suites = {}
    for row in rows:
        suites.setdefault(row["suite"], []).append(row)

    lines = ["# SeisWave Batch Validation", ""]
    for suite, items in suites.items():
        passed = sum(1 for r in items if r["status"] == "passed")
        failed = sum(1 for r in items if r["status"] == "failed")
        skipped = sum(1 for r in items if r["status"] == "skipped")
        lines.append(f"## {suite}")
        lines.append(f"- passed: {passed}")
        lines.append(f"- failed: {failed}")
        lines.append(f"- skipped: {skipped}")
        if failed:
            lines.append("- failed cases:")
            for r in items:
                if r["status"] == "failed":
                    lines.append(f"  - {r['case']}: mean={r.get('mean_error')}, max={r.get('max_error')}, pulse={r.get('pulse')}, conf={r.get('confidence')}, pga_ratio={r.get('pga_ratio')}")
        lines.append("")
    OUT_MD.write_text("\n".join(lines))


def main():
    all_rows = []

    rows, _, _ = validate_general()
    all_rows.extend(rows)

    ff_cases = [(Mw, R, Vs30) for Mw in [6.0, 6.5, 7.0, 7.5, 8.0] for R in [10.0, 30.0, 50.0, 80.0, 120.0] for Vs30 in [260, 360, 540, 760, 1000, 1500]]
    nf_cases = [(Mw, R, Vs30) for Mw in [6.0, 6.5, 7.0, 7.5, 8.0] for R in [3.0, 5.0, 8.0, 12.0, 20.0] for Vs30 in [260, 360, 540, 760, 1000, 1500]]
    nfp_cases = [(Mw, R, Vs30) for Mw in [6.5, 7.0, 7.2, 7.5, 8.0] for R in [3.0, 4.0, 5.0, 8.0, 12.0] for Vs30 in [260, 360, 540, 760, 1000]]

    all_rows.extend(validate_special(FarFieldGenerator, MotionType.FAR_FIELD, "ff", ff_cases, 100.0, 0.15, 0.50, False))
    all_rows.extend(validate_special(NearFieldNoPulseGenerator, MotionType.NEAR_FIELD, "nf", nf_cases, 100.0, 0.20, 0.60, False))
    all_rows.extend(validate_special(NearFieldPulseGenerator, MotionType.NEAR_FIELD_PULSE, "nfp", nfp_cases, 980.0, 0.10, 0.30, True, conf_limit=0.85))

    write_outputs(all_rows)

    total_passed = sum(1 for r in all_rows if r["status"] == "passed")
    total_failed = sum(1 for r in all_rows if r["status"] == "failed")
    total_skipped = sum(1 for r in all_rows if r["status"] == "skipped")
    print(f"TOTAL passed={total_passed} failed={total_failed} skipped={total_skipped}")
    print(f"CSV: {OUT_CSV}")
    print(f"MD: {OUT_MD}")


if __name__ == "__main__":
    main()
