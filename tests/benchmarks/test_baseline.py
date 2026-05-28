"""
SeisWave 性能基准测试脚本

使用标准库 timeit 实现，不依赖 pytest-benchmark。
每个基准包含小/中/大数据三档，输出 JSON 到 benchmarks/results/。

运行方式:
    python tests/benchmarks/test_baseline.py
或 (若 pytest 可用):
    pytest tests/benchmarks/test_baseline.py -v
"""

import json
import os
import sys
import time
import timeit
import statistics
import tempfile
import shutil
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Callable, Any
import numpy as np

# 确保 seiswave 可被 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from seiswave.core.fft import FFT
from seiswave.core.spectrum import Spectra
from seiswave.core.signal import EQSignal
from seiswave.core.io import FileIO
from seiswave.core.generator import WaveGenerator


# ── 目录初始化 ──
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "../../benchmarks/results")
os.makedirs(RESULTS_DIR, exist_ok=True)


@dataclass
class BenchmarkResult:
    """单次基准测试结果"""
    name: str
    group: str
    size_label: str
    params: dict
    runs: int
    times: list[float]  # 秒
    mean: float
    min: float
    max: float
    stdev: float
    unit: str = "s"

    def to_dict(self):
        d = asdict(self)
        d["times"] = [round(t, 6) for t in self.times]
        for k in ("mean", "min", "max", "stdev"):
            d[k] = round(getattr(self, k), 6)
        return d


def run_benchmark(
    name: str,
    group: str,
    size_label: str,
    params: dict,
    fn: Callable[[], Any],
    repeats: int = 5,
    number: int = 1,
) -> BenchmarkResult:
    """运行单次基准并收集统计量"""
    times = []
    for _ in range(repeats):
        # 预热 GC / 缓存
        fn()
        t0 = time.perf_counter()
        for _ in range(number):
            fn()
        t1 = time.perf_counter()
        times.append((t1 - t0) / number)

    mean_t = statistics.mean(times)
    min_t = min(times)
    max_t = max(times)
    stdev_t = statistics.stdev(times) if len(times) > 1 else 0.0

    return BenchmarkResult(
        name=name, group=group, size_label=size_label,
        params=params, runs=repeats, times=times,
        mean=mean_t, min=min_t, max=max_t, stdev=stdev_t,
    )


# ═══════════════════════════════════════════════════════════════
#  基准 1: FFT/IFFT 大信号处理
# ═══════════════════════════════════════════════════════════════

def bench_fft():
    results = []
    configs = [
        ("small", 4096, 10),
        ("medium", 32768, 5),
        ("large", 262144, 3),
    ]

    for label, n, repeats in configs:
        dt = 0.01
        acc = np.random.randn(n).astype(np.float64)
        params = {"n": n, "dt": dt}

        r = run_benchmark(
            "FFT.amplitude_spectrum", "fft", label, params,
            lambda: FFT.amplitude_spectrum(acc, dt),
            repeats=repeats, number=1,
        )
        results.append(r)

        r = run_benchmark(
            "FFT.welch_psd", "fft", label, params,
            lambda: FFT.welch_psd(acc, dt),
            repeats=repeats, number=1,
        )
        results.append(r)

        r = run_benchmark(
            "FFT.phase_spectrum", "fft", label, params,
            lambda: FFT.phase_spectrum(acc, dt),
            repeats=repeats, number=1,
        )
        results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════
#  基准 2: 反应谱计算 (Spectra.compute)
# ═══════════════════════════════════════════════════════════════

def bench_spectra():
    results = []
    n = 8192
    dt = 0.01
    acc = np.random.randn(n).astype(np.float64)

    configs = [
        ("small", 50, 5),
        ("medium", 200, 5),
        ("large", 800, 3),
    ]

    for label, n_periods, repeats in configs:
        periods = Spectra.default_periods(n=n_periods)
        params = {"n": n, "dt": dt, "n_periods": n_periods}

        for method in ("newmark", "freq", "mixed"):
            r = run_benchmark(
                f"Spectra.compute(method={method})", "spectra", label, params,
                lambda m=method, p=periods: Spectra.compute(acc, dt, p, zeta=0.05, method=m),
                repeats=repeats, number=1,
            )
            results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════
#  基准 3: 频域谱匹配 (_fitspectra)
# ═══════════════════════════════════════════════════════════════

def bench_fitspectra():
    """基准 WaveGenerator._fitspectra（频域法谱匹配）

    构造简单目标谱，在不同信号长度和迭代次数下测试。
    """
    results = []

    configs = [
        # (label, n, dt, max_iter, repeats)
        ("small", 2048, 0.02, 10, 5),
        ("medium", 4096, 0.02, 20, 3),
        ("large", 8192, 0.02, 30, 2),
    ]

    for label, n, dt, max_iter, repeats in configs:
        # 简单目标谱：对数周期 + 线性衰减目标
        nP = 20
        periods = np.logspace(np.log10(0.05), np.log10(5.0), nP)
        target_sa = np.exp(-periods / 2.0) * 0.5 + 0.05

        # 构造扩展谱（内部 init_art_wave 需要）
        nP_ext = nP + 2
        P_ext = np.empty(nP_ext)
        P_ext[0] = periods[0] * 0.5
        P_ext[1:nP+1] = periods
        P_ext[nP+1] = periods[-1] * 1.5
        SPAT_ext = np.empty(nP_ext)
        SPAT_ext[1:nP+1] = target_sa
        SPAT_ext[0] = target_sa[0]
        SPAT_ext[nP+1] = target_sa[-1]

        zeta = 0.05
        peak0 = 0.2

        # 预生成初始信号，避免每次重复 init_art_wave
        acc_init = WaveGenerator._init_art_wave(n, dt, zeta, P_ext, SPAT_ext, nP_ext, seed=42)
        pk = np.max(np.abs(acc_init))
        if pk > 0:
            acc_init *= peak0 / pk

        # 谱匹配所需的扩展参数
        nP_full = nP + 2
        P_full = np.empty(nP_full)
        P_full[0] = periods[0] * 0.5
        P_full[1:nP+1] = periods
        P_full[nP+1] = periods[-1] * 1.5
        SPAT_full = np.empty(nP_full)
        SPAT_full[1:nP+1] = target_sa
        SPAT_full[0] = target_sa[0]
        SPAT_full[nP+1] = target_sa[-1]

        params = {"n": n, "dt": dt, "nP": nP, "max_iter": max_iter, "fm": 0}

        r = run_benchmark(
            "WaveGenerator._fitspectra", "fitspectra", label, params,
            lambda: WaveGenerator._fitspectra(
                acc_init.copy(), n, dt, zeta,
                P_full, nP_full, SPAT_full,
                tol=0.05, max_iter=max_iter, peak0=peak0,
                progress_callback=None,
            ),
            repeats=repeats, number=1,
        )
        results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════
#  基准 4: 特殊地震动生成 (FF / NF)
# ═══════════════════════════════════════════════════════════════

def bench_special_generators():
    """基准 FarField / NearField 生成器

    使用较小规模参数，因为完整生成涉及 GMPE + 谱匹配，耗时较长。
    """
    results = []

    configs = [
        ("small", 2048, 0.02, 5, 3),
        ("medium", 4096, 0.02, 10, 2),
        # large 档直接跳过，避免单次超过 30s
    ]

    for label, n, dt, max_iter, repeats in configs:
        params = {"Mw": 7.0, "R": 10.0, "Vs30": 760, "n": n, "dt": dt,
                  "max_iter": max_iter, "fm": 0}

        r = run_benchmark(
            "FarFieldGenerator.generate", "special_generators", label, params,
            lambda: WaveGenerator.generate(
                type="FF", Mw=7.0, R=10.0, Vs30=760,
                n=n, dt=dt, zeta=0.05, max_iter=max_iter, fm=0,
            ),
            repeats=repeats, number=1,
        )
        results.append(r)

        r = run_benchmark(
            "NearFieldNoPulseGenerator.generate", "special_generators", label, params,
            lambda: WaveGenerator.generate(
                type="NF", Mw=7.0, R=5.0, Vs30=760,
                n=n, dt=dt, zeta=0.05, max_iter=max_iter, fm=0,
            ),
            repeats=repeats, number=1,
        )
        results.append(r)

    return results


# ═══════════════════════════════════════════════════════════════
#  基准 5: 文件 I/O (大文件读写)
# ═══════════════════════════════════════════════════════════════

def bench_io():
    """基准 FileIO 读写性能

    构造不同大小的 AT2/txt 文件，测试读写速度。
    """
    results = []
    tmpdir = tempfile.mkdtemp(prefix="seiswave_bench_")

    configs = [
        ("small", 2048, 5),
        ("medium", 16384, 5),
        ("large", 65536, 3),
    ]

    try:
        for label, n, repeats in configs:
            dt = 0.01
            acc = np.random.randn(n).astype(np.float64)
            params = {"n": n, "dt": dt}

            # AT2 写入
            at2_path = os.path.join(tmpdir, f"test_{label}.AT2")
            FileIO.write_at2(at2_path, acc, dt, metadata={"event": "bench"})

            r = run_benchmark(
                "FileIO.read_at2", "io", label, params,
                lambda p=at2_path: FileIO.read_at2(p),
                repeats=repeats, number=1,
            )
            results.append(r)

            # txt 写入（单列）
            txt_path = os.path.join(tmpdir, f"test_{label}.txt")
            FileIO.write_txt(txt_path, acc, dt, two_col=False)

            r = run_benchmark(
                "FileIO.read_txt", "io", label, params,
                lambda p=txt_path: FileIO.read_txt(p, dt=dt),
                repeats=repeats, number=1,
            )
            results.append(r)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return results


# ═══════════════════════════════════════════════════════════════
#  主控
# ═══════════════════════════════════════════════════════════════

def run_all():
    all_results = []
    groups = [
        ("fft", bench_fft),
        ("spectra", bench_spectra),
        ("fitspectra", bench_fitspectra),
        ("special_generators", bench_special_generators),
        ("io", bench_io),
    ]

    print("=" * 60)
    print(" SeisWave 性能基准测试")
    print(f" 时间: {datetime.now().isoformat()}")
    print(f" NumPy: {np.__version__}")
    print("=" * 60)

    for group_name, bench_fn in groups:
        print(f"\n▶ 运行组: {group_name}")
        try:
            group_results = bench_fn()
            all_results.extend(group_results)
            for r in group_results:
                print(
                    f"  [{r.size_label:6s}] {r.name:40s} "
                    f"mean={r.mean*1000:8.3f}ms  min={r.min*1000:8.3f}ms  "
                    f"max={r.max*1000:8.3f}ms  stdev={r.stdev*1000:8.3f}ms"
                )
        except Exception as e:
            print(f"  ⚠ {group_name} 失败: {e}")
            import traceback
            traceback.print_exc()

    # 保存 JSON
    payload = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "numpy_version": np.__version__,
            "platform": sys.platform,
        },
        "results": [r.to_dict() for r in all_results],
    }

    out_path = os.path.join(
        RESULTS_DIR,
        f"baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 结果已保存: {out_path}")
    print(f"   总基准数: {len(all_results)}")
    return all_results, out_path


if __name__ == "__main__":
    run_all()
