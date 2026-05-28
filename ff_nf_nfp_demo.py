"""
FF vs NF vs NFP 地震动生成对比 Demo
使用 SeisWave Feature-001 统一入口
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# 统一参数
Mw, R, Vs30 = 7.0, 5.0, 760.0
fault_type = "strike_slip"
dt = 0.01
n = 3000
t = np.arange(n) * dt

# 生成三类地震动
from seiswave.core.generator import create_ground_motion

print("生成 FF...")
ff = create_ground_motion("FF", Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type, dt=dt, n=n)

print("生成 NF...")
nf = create_ground_motion("NF", Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type, dt=dt, n=n)

print("生成 NFP...")
nfp = create_ground_motion("NFP", Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type, dt=dt, n=n)

# 计算反应谱
from seiswave.core.spectrum import Spectra
periods = np.logspace(-1, 1, 50)

ff_spec = Spectra.compute(ff.acc, dt, periods, zeta=0.05, method="mixed")
nf_spec = Spectra.compute(nf.acc, dt, periods, zeta=0.05, method="mixed")
nfp_spec = Spectra.compute(nfp.acc, dt, periods, zeta=0.05, method="mixed")

# 绘图
fig = plt.figure(figsize=(18, 14))
gs = GridSpec(4, 3, figure=fig, hspace=0.35, wspace=0.25)

# 颜色
C_FF = "#2E86AB"   # 蓝
C_NF = "#A23B72"   # 紫
C_NFP = "#F18F01"  # 橙

# Row 0: 加速度时程
for col, (sig, name, color) in enumerate([(ff, "FF", C_FF), (nf, "NF", C_NF), (nfp, "NFP", C_NFP)]):
    ax = fig.add_subplot(gs[0, col])
    ax.plot(t, sig.acc, color=color, lw=0.6)
    ax.axhline(0, color="gray", lw=0.5)
    ax.set_xlim(0, 30)
    ax.set_title(name, fontsize=14, fontweight="bold", color=color)
    if col == 0:
        ax.set_ylabel("Accel (cm/s²)", fontsize=10)
    ax.set_xlabel("Time (s)", fontsize=10)

# Row 1: 速度时程
for col, (sig, name, color) in enumerate([(ff, "FF", C_FF), (nf, "NF", C_NF), (nfp, "NFP", C_NFP)]):
    ax = fig.add_subplot(gs[1, col])
    ax.plot(t, sig.vel, color=color, lw=0.8)
    ax.axhline(0, color="gray", lw=0.5)
    ax.set_xlim(0, 30)
    if col == 0:
        ax.set_ylabel("Vel (cm/s)", fontsize=10)
    ax.set_xlabel("Time (s)", fontsize=10)
    # 标注 PGV
    pgv = np.max(np.abs(sig.vel))
    ax.text(0.97, 0.95, f"PGV={pgv:.1f} cm/s", transform=ax.transAxes,
            ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8, edgecolor=color))

# Row 2: 反应谱对比（三类叠在一起）
ax = fig.add_subplot(gs[2, :])
ax.plot(periods, ff_spec.sa, color=C_FF, lw=1.5, label=f"FF  PGA={np.max(np.abs(ff.acc)):.1f}")
ax.plot(periods, nf_spec.sa, color=C_NF, lw=1.5, label=f"NF  PGA={np.max(np.abs(nf.acc)):.1f}")
ax.plot(periods, nfp_spec.sa, color=C_NFP, lw=1.5, label=f"NFP PGA={np.max(np.abs(nfp.acc)):.1f}")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Period (s)", fontsize=11)
ax.set_ylabel("Sa (cm/s²)", fontsize=11)
ax.set_title("Response Spectrum Comparison (5% damping)", fontsize=12, fontweight="bold")
ax.legend(loc="upper right", fontsize=10)
ax.grid(True, which="both", ls="--", alpha=0.4)
ax.set_xlim(0.1, 10)

# Row 3: NFP 脉冲分析
ax_pulse = fig.add_subplot(gs[3, :2])
ax_pulse.plot(t, nfp.vel, color=C_NFP, lw=0.8, alpha=0.7, label="Total velocity")
# 如果有脉冲速度分量，画出来
if hasattr(nfp, "pulse_vel") and nfp.pulse_vel is not None:
    ax_pulse.plot(t, nfp.pulse_vel, color="red", lw=1.5, label="Pulse component", alpha=0.9)
    if hasattr(nfp, "residual_vel") and nfp.residual_vel is not None:
        ax_pulse.plot(t, nfp.residual_vel, color="gray", lw=0.8, ls="--", label="Residual", alpha=0.6)
ax_pulse.axhline(0, color="black", lw=0.5)
ax_pulse.set_xlim(0, 30)
ax_pulse.set_xlabel("Time (s)", fontsize=10)
ax_pulse.set_ylabel("Vel (cm/s)", fontsize=10)
ax_pulse.set_title("NFP Pulse Decomposition", fontsize=12, fontweight="bold", color=C_NFP)
ax_pulse.legend(loc="upper right", fontsize=9)

# NFP 脉冲参数文本框
ax_text = fig.add_subplot(gs[3, 2])
ax_text.axis("off")

# 获取脉冲参数
pulse_params = getattr(nfp, "pulse_params", None)
pulse_metrics = getattr(nfp, "pulse_metrics", None)

text_lines = [
    "═══ NFP Pulse Parameters ═══",
    "",
]
if pulse_params:
    # PulseParams 是 dataclass，用属性访问
    text_lines += [
        f"Tp = {getattr(pulse_params, 'Tp', 'N/A'):.2f} s",
        f"A  = {getattr(pulse_params, 'A', 'N/A'):.1f} cm/s",
        f"φ  = {getattr(pulse_params, 'phi', 'N/A'):.2f} rad",
        f"t₀ = {getattr(pulse_params, 't0', 'N/A'):.1f} s",
        "",
    ]
if pulse_metrics:
    conf = pulse_metrics.get("confidence", 0)
    has_pulse = pulse_metrics.get("has_pulse", False)
    text_lines += [
        f"Baker (2007) Detection:",
        f"  Has pulse: {'✓ YES' if has_pulse else '✗ NO'}",
        f"  Confidence: {conf:.2f}",
        f"  Energy ratio: {pulse_metrics.get('energy_ratio', 0):.2f}",
        "",
    ]

pgv_nfp = np.max(np.abs(nfp.vel))
text_lines += [
    f"PGV = {pgv_nfp:.1f} cm/s",
    f"PGA = {np.max(np.abs(nfp.acc)):.1f} cm/s²",
]

ax_text.text(0.1, 0.5, "\n".join(text_lines), transform=ax_text.transAxes,
             fontsize=10, verticalalignment="center", family="monospace",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF8E7", edgecolor=C_NFP, lw=2))

plt.suptitle(f"SeisWave Feature-001 Demo: Mw={Mw}, R={R}km, Vs30={Vs30}m/s, {fault_type}",
             fontsize=14, fontweight="bold", y=0.995)

out_path = "/Users/yachiyo/.openclaw/workspace/ff_nf_nfp_demo.png"
plt.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Demo图已保存: {out_path}")

# 打印关键指标
print("\n═══ 关键指标对比 ═══")
print(f"{'':6} {'PGV(cm/s)':>12} {'PGA(cm/s²)':>12} {'Baker脉冲':>10}")
print("-" * 50)
for sig, name in [(ff, "FF"), (nf, "NF"), (nfp, "NFP")]:
    pgv = np.max(np.abs(sig.vel))
    pga = np.max(np.abs(sig.acc))
    metrics = getattr(sig, "pulse_metrics", {})
    pulse_flag = "YES" if metrics.get("has_pulse", False) else "NO"
    print(f"{name:6} {pgv:12.1f} {pga:12.1f} {pulse_flag:>10}")
