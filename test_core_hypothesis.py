"""
核心假设验证：谱匹配后的信号线性缩放是否保持谱误差？
"""

import numpy as np
import sys
sys.path.insert(0, '/Users/yachiyo/Developer/seiswave')

# 从 test_lm_prototype.py 复用关键函数
exec(open('/Users/yachiyo/Developer/seiswave/test_lm_prototype.py').read())

# 生成测试数据
n, dt, zeta = 2000, 0.02, 0.05
n_periods = 300
Tg, alpha_max, PGA = 0.2, 0.16, 0.16

periods = default_periods(0.04, 6.0, n_periods, mode="mixed")
target_sa = gb50011(periods, Tg, alpha_max, zeta=zeta)

nP_ext = n_periods + 2
P_ext = np.empty(nP_ext)
P_ext[0] = periods[0] * 0.5
P_ext[1:n_periods+1] = periods
P_ext[n_periods+1] = periods[-1] * 1.5
SPAT_ext = np.empty(nP_ext)
SPAT_ext[1:n_periods+1] = target_sa
SPAT_ext[0] = target_sa[0] - (target_sa[1] - target_sa[0]) / (periods[1] - periods[0]) * periods[0] * 0.5
SPAT_ext[n_periods+1] = target_sa[-1] + (target_sa[-1] - target_sa[-2]) / (periods[-1] - periods[-2]) * periods[-1] * 1.5

acc = init_art_wave(n, dt, zeta, P_ext, SPAT_ext, nP_ext, seed=42)
env = envelope(n, dt)
acc *= env

P_ctrl, SPAT_ctrl = downsample_control_points(periods, target_sa, max_ctrl=50)
nP_ctrl = len(P_ctrl)

print("=" * 60)
print("核心假设验证：缩放是否保持谱误差？")
print("=" * 60)
print()

# 测试1：在 0.08g (0.5*PGA) 下匹配，然后直接缩放到 0.16g
print("测试1：0.08g 匹配后直接缩放到 0.16g")
acc_08 = acc.copy()
pk = np.max(np.abs(acc_08))
if pk > 1e-30:
    acc_08 = acc_08 * (0.08 / pk)

acc_08_matched, err_08 = adjustspectra(acc_08, n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl, tol=0.05, max_iter=50, use_new_wavelet=True)
sa_08 = compute_spectrum(acc_08_matched, dt, periods, zeta)
e_08 = (sa_08 - target_sa) / np.maximum(target_sa, 1e-30)
aerror_08 = float(np.sqrt(np.mean(e_08 * e_08)))

# 直接缩放到 0.16g
acc_16_scaled = acc_08_matched * (0.16 / np.max(np.abs(acc_08_matched)))
sa_16s = compute_spectrum(acc_16_scaled, dt, periods, zeta)
e_16s = (sa_16s - target_sa) / np.maximum(target_sa, 1e-30)
aerror_16_scaled = float(np.sqrt(np.mean(e_16s * e_16s)))

print(f"  0.08g 匹配后: PGA={np.max(np.abs(acc_08_matched)):.4f}g, aerror={aerror_08:.2%}")
print(f"  直接缩放 0.16g: PGA={np.max(np.abs(acc_16_scaled)):.4f}g, aerror={aerror_16_scaled:.2%}")
print()

# 测试2：在 0.08g 下匹配，然后继续做 adjustspectra 到 0.16g
print("测试2：0.08g 匹配后继续 adjustspectra 到 0.16g")
acc_16_adj, err_16 = adjustspectra(acc_16_scaled.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl, tol=0.05, max_iter=50, use_new_wavelet=True)
sa_16a = compute_spectrum(acc_16_adj, dt, periods, zeta)
e_16a = (sa_16a - target_sa) / np.maximum(target_sa, 1e-30)
aerror_16_adj = float(np.sqrt(np.mean(e_16a * e_16a)))
print(f"  缩放+迭代后: PGA={np.max(np.abs(acc_16_adj)):.4f}g, aerror={aerror_16_adj:.2%}")
print()

# 测试3：旧小波对比
print("测试3：旧小波在 0.08g 匹配后直接缩放")
acc_08_old, err_08_old = adjustspectra(acc_08.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl, tol=0.05, max_iter=50, use_new_wavelet=False)
sa_08_old = compute_spectrum(acc_08_old, dt, periods, zeta)
e_08_old = (sa_08_old - target_sa) / np.maximum(target_sa, 1e-30)
aerror_08_old = float(np.sqrt(np.mean(e_08_old * e_08_old)))

acc_16_old_scaled = acc_08_old * (0.16 / np.max(np.abs(acc_08_old)))
sa_16_old_s = compute_spectrum(acc_16_old_scaled, dt, periods, zeta)
e_16_old_s = (sa_16_old_s - target_sa) / np.maximum(target_sa, 1e-30)
aerror_16_old_scaled = float(np.sqrt(np.mean(e_16_old_s * e_16_old_s)))

acc_16_old_adj, _ = adjustspectra(acc_16_old_scaled.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl, tol=0.05, max_iter=50, use_new_wavelet=False)
sa_16_old_a = compute_spectrum(acc_16_old_adj, dt, periods, zeta)
e_16_old_a = (sa_16_old_a - target_sa) / np.maximum(target_sa, 1e-30)
aerror_16_old_adj = float(np.sqrt(np.mean(e_16_old_a * e_16_old_a)))

print(f"  旧小波 0.08g 匹配: aerror={aerror_08_old:.2%}")
print(f"  旧小波直接缩放 0.16g: aerror={aerror_16_old_scaled:.2%}")
print(f"  旧小波缩放+迭代: aerror={aerror_16_old_adj:.2%}")
print()

# 核心结论
print("=" * 60)
print("核心结论")
print("=" * 60)
print(f"Atik小波:")
print(f"  仅缩放: aerror={aerror_16_scaled:.2%}")
print(f"  缩放+迭代: aerror={aerror_16_adj:.2%}")
print(f"旧小波:")
print(f"  仅缩放: aerror={aerror_16_old_scaled:.2%}")
print(f"  缩放+迭代: aerror={aerror_16_old_adj:.2%}")
print()
if aerror_16_adj > aerror_16_scaled:
    print("⚠️ Atik 小波: adjustspectra 迭代在高 PGA 下发散")
else:
    print("✅ Atik 小波: adjustspectra 迭代有效")
if aerror_16_old_adj > aerror_16_old_scaled:
    print("⚠️ 旧小波: adjustspectra 迭代在高 PGA 下发散")
else:
    print("✅ 旧小波: adjustspectra 迭代有效")
