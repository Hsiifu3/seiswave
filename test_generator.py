#!/usr/bin/env python3
"""
验证人工波生成算法的测试脚本

测试条件：
- GB50011 目标谱：8度0.2g，II类场地，第1组，多遇
- 阻尼比 ζ = 0.05
- 目标：最大偏差 < 15%，均方根偏差 < 5%
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.spectrum import Spectra
from seiswave.core.generator import WaveGenerator


def test_newmark_vs_analytical():
    """验证 Newmark-β 法：用简谐激励对比解析解"""
    print("=" * 60)
    print("测试 1: Newmark-β 法验证（简谐激励）")
    print("=" * 60)

    dt = 0.01
    T_sdof = 1.0  # SDOF 周期
    zeta = 0.05
    omega_n = 2 * np.pi / T_sdof

    # 简谐激励 ẍg = sin(ω_f·t)，ω_f ≠ ω_n
    omega_f = 1.5 * omega_n
    t = np.arange(0, 20, dt)
    acc = np.sin(omega_f * t)

    # Newmark 计算
    ra, rv, rd = Spectra._newmark_beta(acc, dt, T_sdof, zeta)
    abs_acc = ra + acc

    # 稳态解析解（忽略瞬态）
    # 对于 ü + 2ζω_n·u̇ + ω_n²·u = -sin(ω_f·t)
    # 稳态位移幅值：
    beta_r = omega_f / omega_n
    D = 1.0 / np.sqrt((1 - beta_r**2)**2 + (2*zeta*beta_r)**2)
    u_max_analytical = D / omega_n**2

    # 取后半段（稳态部分）的位移峰值
    u_max_numerical = np.max(np.abs(rd[len(rd)//2:]))

    error = abs(u_max_numerical - u_max_analytical) / u_max_analytical
    print(f"  解析稳态位移幅值: {u_max_analytical:.6f}")
    print(f"  数值稳态位移幅值: {u_max_numerical:.6f}")
    print(f"  相对误差: {error:.4%}")
    print(f"  {'✓ 通过' if error < 0.02 else '✗ 失败'}")
    print()
    return error < 0.02


def test_spectrum_generation():
    """测试人工波生成与谱匹配"""
    print("=" * 60)
    print("测试 2: 人工波生成与谱匹配")
    print("=" * 60)

    # GB50011 参数：8度(0.2g)，第1组，II类场地，多遇
    params = CodeSpectrum.get_params(
        intensity=8, group=1, site_class="II", level="frequent"
    )
    print(f"  Tg = {params['Tg']:.2f} s, α_max = {params['alpha_max']:.3f}")

    # 生成周期数组（减少点数以加速测试）
    periods = Spectra.default_periods(0.04, 6.0, 50, mode="mixed")

    # 计算目标谱（地震影响系数 α）
    target_alpha = CodeSpectrum.gb50011(
        periods, params['Tg'], params['alpha_max'], zeta=0.05
    )

    # 目标 PGA：对于多遇地震，PGA ≈ α_max * g
    # 但 α 在 T→0 时趋近 0.45*α_max，在平台段为 η2*α_max ≈ α_max
    # 使用 α_max 作为 PGA 的近似值（单位 g）
    target_pga = params['alpha_max']
    print(f"  目标 PGA = {target_pga:.3f} g")

    # 生成人工波
    print("  正在生成人工波...")
    np.random.seed(42)  # 固定随机种子以便复现

    def progress(iteration, max_err, mean_err):
        if iteration % 10 == 0 or iteration <= 3:
            print(f"    迭代 {iteration:3d}: 最大偏差 = {max_err:.4f}, "
                  f"均方根偏差 = {mean_err:.4f}")

    signal = WaveGenerator.generate(
        target_alpha, periods,
        n=2048, dt=0.02, zeta=0.05,
        pga=target_pga, tol=0.05, max_iter=60,
        progress_callback=progress,
    )

    print(f"\n  生成结果:")
    print(f"    PGA = {signal.pga:.4f} g")
    print(f"    持时 = {signal.duration:.2f} s")
    print(f"    数据点数 = {signal.n}")

    # 计算生成波的反应谱（用 mixed 方法，与算法内部一致）
    spec = Spectra.compute(signal.acc, signal.dt, periods, zeta=0.05,
                           method="mixed")

    # 计算误差
    fit = WaveGenerator.fit_error(spec.sa, target_alpha)
    print(f"\n  拟合误差:")
    print(f"    最大偏差 = {fit['max_error']:.4f} ({fit['max_error']:.1%})")
    print(f"    均方根偏差 = {fit['mean_error']:.4f} ({fit['mean_error']:.1%})")

    # 逐周期点误差
    print(f"\n  各周期点偏差（抽样）:")
    indices = np.linspace(0, len(periods)-1, 20, dtype=int)
    for idx in indices:
        T = periods[idx]
        tgt = target_alpha[idx]
        act = spec.sa[idx]
        if tgt > 1e-10:
            err = abs(act - tgt) / tgt
            print(f"    T={T:6.3f}s: 目标={tgt:.4f}, 实际={act:.4f}, "
                  f"偏差={err:.1%}")

    max_ok = fit['max_error'] < 0.15
    mean_ok = fit['mean_error'] < 0.05
    print(f"\n  最大偏差 < 15%: {'✓ 通过' if max_ok else '✗ 失败'}")
    print(f"  均方根偏差 < 5%: {'✓ 通过' if mean_ok else '✗ 失败'}")
    print()
    return max_ok and mean_ok


def test_unit_consistency():
    """测试单位一致性"""
    print("=" * 60)
    print("测试 3: 单位一致性检查")
    print("=" * 60)

    # 生成一个简单的加速度时程（单位 g）
    dt = 0.02
    n = 2048
    t = np.arange(n) * dt
    # 简单的正弦波，PGA = 0.1g
    acc = 0.1 * np.sin(2 * np.pi * 2.0 * t) * np.exp(-0.1 * t)

    periods = np.array([0.5])  # T = 0.5s, f = 2Hz（共振）
    zeta = 0.05

    spec = Spectra.compute(acc, dt, periods, zeta=zeta, method="newmark")

    # 对于共振频率附近，Sa 应该远大于 PGA
    # 放大系数约为 1/(2ζ) = 10
    pga = np.max(np.abs(acc))
    amplification = spec.sa[0] / pga

    print(f"  PGA = {pga:.4f} g")
    print(f"  Sa(T=0.5s) = {spec.sa[0]:.4f} g")
    print(f"  放大系数 = {amplification:.2f}")
    print(f"  理论放大系数 ≈ {1/(2*zeta):.1f} (共振时)")

    # 放大系数应该在合理范围内（考虑瞬态效应，不会精确等于 1/(2ζ)）
    ok = 2.0 < amplification < 15.0
    print(f"  放大系数合理 (2~15): {'✓ 通过' if ok else '✗ 失败'}")
    print()
    return ok


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SeisWave 人工波生成算法验证")
    print("=" * 60 + "\n")

    results = []
    results.append(("Newmark-β 验证", test_newmark_vs_analytical()))
    results.append(("单位一致性", test_unit_consistency()))
    results.append(("谱匹配生成", test_spectrum_generation()))

    print("=" * 60)
    print("总结")
    print("=" * 60)
    all_pass = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("所有测试通过！🎉")
    else:
        print("部分测试失败，需要进一步调试。")

    sys.exit(0 if all_pass else 1)
