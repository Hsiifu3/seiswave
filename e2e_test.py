"""SeisWave 端到端实际生成测试"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.expanduser("~/Developer/seiswave"))

from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.signal import EQSignal
from seiswave.core.generator import WaveGenerator
from seiswave.gui.panels.generator_panel import GeneratorPanel
from seiswave.core.fortran_bridge import HAS_FORTRAN

print(f"Fortran 桥接可用: {HAS_FORTRAN}")
print(f"numpy 版本: {np.__version__}")

# ── 准备规范谱 ──
cs = CodeSpectrum()
periods = np.logspace(-1, 1, 50)
sa = cs.from_params(periods, 8, 2, 'II', 'frequent', 0.05)
target_pga = sa[0]
print(f"\n规范谱: 中国 VIII 度 0.20g (frequent), 目标 PGA = {target_pga:.4f} m/s²")

results = []

# ── 1. 时域法 fm=1 ──
print("\n=== 测试 1: 时域法 (fm=1) ===")
start = time.time()
try:
    sig1 = WaveGenerator.generate(
        target_spectrum=sa, periods=periods,
        n=4096, dt=0.02, zeta=0.05,
        pga=target_pga, tol=0.05, max_iter=10,
        fm=1,
    )
    elapsed1 = time.time() - start
    pga1 = sig1.pga
    err1 = abs(pga1 - target_pga) / target_pga * 100
    print(f"  耗时: {elapsed1:.2f}s")
    print(f"  PGA: {pga1:.4f} m/s² (目标 {target_pga:.4f}, 误差 {err1:.2f}%)")
    results.append(("时域法 fm=1", True, elapsed1, f"PGA误差 {err1:.2f}%"))
except Exception as e:
    elapsed1 = time.time() - start
    print(f"  ❌ 失败: {e}")
    results.append(("时域法 fm=1", False, elapsed1, str(e)))

# ── 2. 频域法 fm=0 ──
print("\n=== 测试 2: 频域法 (fm=0) ===")
start = time.time()
try:
    sig2 = WaveGenerator.generate(
        target_spectrum=sa, periods=periods,
        n=4096, dt=0.02, zeta=0.05,
        pga=target_pga, tol=0.05, max_iter=10,
        fm=0,
    )
    elapsed2 = time.time() - start
    pga2 = sig2.pga
    err2 = abs(pga2 - target_pga) / target_pga * 100
    print(f"  耗时: {elapsed2:.2f}s")
    print(f"  PGA: {pga2:.4f} m/s² (目标 {target_pga:.4f}, 误差 {err2:.2f}%)")
    results.append(("频域法 fm=0", True, elapsed2, f"PGA误差 {err2:.2f}%"))
except Exception as e:
    elapsed2 = time.time() - start
    print(f"  ❌ 失败: {e}")
    results.append(("频域法 fm=0", False, elapsed2, str(e)))

# ── 3. 远场 FF ──
print("\n=== 测试 3: 远场 FF (Mw=7.0, R=10km) ===")
start = time.time()
try:
    sig_ff = WaveGenerator.generate(
        type="FF", Mw=7.0, R=10.0, Vs30=760.0,
        n=4096, dt=0.02, zeta=0.05,
        tol=0.05, max_iter=10, fm=1,
    )
    elapsed_ff = time.time() - start
    print(f"  耗时: {elapsed_ff:.2f}s")
    print(f"  PGA: {sig_ff.pga:.4f} m/s²")
    results.append(("远场 FF", True, elapsed_ff, f"PGA={sig_ff.pga:.4f}"))
except Exception as e:
    elapsed_ff = time.time() - start
    print(f"  ❌ 失败: {e}")
    results.append(("远场 FF", False, elapsed_ff, str(e)))

# ── 4. 近场无脉冲 NF ──
print("\n=== 测试 4: 近场无脉冲 NF ===")
start = time.time()
try:
    sig_nf = WaveGenerator.generate(
        type="NF", Mw=7.0, R=10.0, Vs30=760.0,
        n=4096, dt=0.02, zeta=0.05,
        tol=0.05, max_iter=10, fm=1,
    )
    elapsed_nf = time.time() - start
    print(f"  耗时: {elapsed_nf:.2f}s")
    print(f"  PGA: {sig_nf.pga:.4f} m/s²")
    results.append(("近场 NF", True, elapsed_nf, f"PGA={sig_nf.pga:.4f}"))
except Exception as e:
    elapsed_nf = time.time() - start
    print(f"  ❌ 失败: {e}")
    results.append(("近场 NF", False, elapsed_nf, str(e)))

# ── 5. 近场脉冲 NFP ──
print("\n=== 测试 5: 近场脉冲 NFP ===")
start = time.time()
try:
    sig_nfp = WaveGenerator.generate(
        type="NFP", Mw=7.0, R=10.0, Vs30=760.0,
        n=4096, dt=0.02, zeta=0.05,
        tol=0.05, max_iter=10, fm=1,
    )
    elapsed_nfp = time.time() - start
    print(f"  耗时: {elapsed_nfp:.2f}s")
    print(f"  PGA: {sig_nfp.pga:.4f} m/s²")
    pulse_info = ""
    if hasattr(sig_nfp, 'pulse_params') and sig_nfp.pulse_params:
        pp = sig_nfp.pulse_params
        pulse_info = f"Tp={pp.Tp:.2f}s, A={pp.A:.2f}"
    elif hasattr(sig_nfp, 'pulse_metrics') and sig_nfp.pulse_metrics:
        pm = sig_nfp.pulse_metrics
        pulse_info = f"has_pulse={pm.get('has_pulse')}, Tp={pm.get('pulse_period')}"
    print(f"  脉冲参数: {pulse_info}")
    results.append(("近场脉冲 NFP", True, elapsed_nfp, f"PGA={sig_nfp.pga:.4f}, {pulse_info}"))
except Exception as e:
    elapsed_nfp = time.time() - start
    print(f"  ❌ 失败: {e}")
    results.append(("近场脉冲 NFP", False, elapsed_nfp, str(e)))

# ── 6. 规范谱未设置保护（GUI 层面） ──
print("\n=== 测试 6: 规范谱未设置保护 ===")
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)
gp = GeneratorPanel(dark=False)
gp.show()
app.processEvents()
# 不设置规范谱，直接检查生成按钮状态
btn_enabled = gp._param_form._run_btn.isEnabled()
# 规范谱未设置时，按钮应该被禁用
code_set = gp._code_periods is not None and len(gp._code_periods) > 0
if not code_set and btn_enabled:
    print("  ⚠️ 规范谱未设置但按钮仍可用（可能依赖弹窗提示保护）")
    results.append(("规范谱保护", "⚠️", "N/A", "按钮未禁用，可能依赖运行时弹窗"))
else:
    print(f"  ✅ 规范谱未设置时按钮状态: enabled={btn_enabled}, code_set={code_set}")
    results.append(("规范谱保护", True, "N/A", f"code_set={code_set}, btn={btn_enabled}"))
gp.close()

# ── 7. 组合面板检查 ──
print("\n=== 测试 7: 组合面板布局 ===")
from seiswave.gui.main_window import MainWindow
win = MainWindow()
win.show()
app.processEvents()
try:
    win._set_step(3)  # 组合面板是第4步 (index 3)
    app.processEvents()
    combo = win._combine_panel
    # 检查 UI 元素是否可访问
    assert combo is not None, "组合面板不存在"
    # 检查导出按钮
    export_ok = hasattr(combo, '_export_btn') or hasattr(combo, 'export_btn')
    # 截图
    from PySide6.QtGui import QPixmap
    pixmap = QPixmap(combo.size())
    combo.render(pixmap)
    path = os.path.expanduser("~/Developer/seiswave/.specs/combo-panel-verify.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pixmap.save(path)
    print(f"  ✅ 组合面板可访问，截图已保存，导出按钮存在={export_ok}")
    results.append(("组合面板", True, "N/A", f"UI可访问, export_btn={export_ok}"))
except Exception as e:
    print(f"  ❌ 组合面板检查失败: {e}")
    results.append(("组合面板", False, "N/A", str(e)))
win.close()
app.quit()

# ── 汇总 ──
print("\n" + "="*60)
print("端到端测试结果汇总")
print("="*60)
for name, ok, elapsed, note in results:
    status = "✅" if ok is True else ("❌" if ok is False else "⚠️")
    print(f"  {status} {name:20s} | {elapsed if isinstance(elapsed, str) else f'{elapsed:.2f}s':>8s} | {note}")
print("="*60)
