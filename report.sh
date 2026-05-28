#!/usr/bin/env bash
# SeisWave 频率域谱匹配算法 + 特殊地震动生成器验收报告脚本
# 用法: ./report.sh

set -euo pipefail

PROJECT="/Users/yachiyo/Developer/seiswave"
cd "$PROJECT"

echo "========================================"
echo "  频率域谱匹配算法 + 生成器统一验收报告"
echo "========================================"
echo ""

# 1. 修改文件
echo "--- 1. 修改文件 ---"
git diff --stat seiswave/core/generator.py tests/test_ff_nf_generators.py || true
echo ""

# 2. 核心验收测试：CodeSpectrum
echo "--- 2. 核心验收测试：频域法 fm=0（CodeSpectrum） ---"
python3 -c "
import numpy as np
from seiswave.core.generator import WaveGenerator
from seiswave.core.spectrum import Spectra
from seiswave.core.code_spec import CodeSpectrum

cs = CodeSpectrum()
periods = np.logspace(-1, 1, 100)
target_sa = cs.from_params(periods=periods, intensity=8, group=2, site_class='II', level='frequent', zeta=0.05)
params = cs.get_params(8, 2, 'II', 'frequent')

sig = WaveGenerator.generate(
    target_spectrum=target_sa, periods=periods, n=4096, dt=0.02,
    zeta=0.05, pga=params['alpha_max'], tol=0.05, max_iter=50, fm=0,
)

gen_spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method='mixed')
valid = target_sa > 1e-6
rel_err = (gen_spec.sa[valid] - target_sa[valid]) / target_sa[valid]
max_err = np.max(np.abs(rel_err))
rms_err = np.sqrt(np.mean(rel_err**2))

print(f'✅ 频域法 fm=0: 最大误差={max_err:.2%}, RMS={rms_err:.2%}, PGA={np.max(np.abs(sig.acc)):.4f}g')
assert max_err < 0.05, f'最大误差 {max_err:.1%} > 5%'
assert rms_err < 0.02, f'RMS误差 {rms_err:.1%} > 2%'
"
echo ""

# 3. 特殊地震动生成器验收测试：FF
echo "--- 3. 特殊地震动生成器验收：FarField (fm=0) ---"
python3 -c "
from seiswave.core.generator import create_ground_motion, WaveGenerator
from seiswave.core.gmpe import GMPEAdapter, FaultType, MotionType
from seiswave.core.spectrum import Spectra

Mw, R, Vs30 = 7.0, 50.0, 760
periods, target_sa = GMPEAdapter.compute_spectrum(
    Mw=Mw, R=R, Vs30=Vs30,
    fault_type=FaultType.STRIKE_SLIP,
    motion_type=MotionType.FAR_FIELD,
)

sig = create_ground_motion('FF', Mw=Mw, R=R, Vs30=Vs30, fault_type='strike_slip', dt=0.02, n=2000)
spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method='mixed')
fit = WaveGenerator.fit_error(spec.sa, target_sa)

print(f'✅ FF 生成器 fm=0: fit_mean={fit[\"mean_error\"]:.2%}, fit_max={fit[\"max_error\"]:.2%}, PGA={sig.pga:.4f}g')
assert fit['mean_error'] < 0.05, f'fit_mean {fit[\"mean_error\"]:.2%} > 5%'
"
echo ""

# 5. UI 布局验证
echo "--- 5. UI 布局验证 ---"
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/Developer/seiswave'))
from PySide6.QtWidgets import QApplication
from seiswave.gui.panels.generator_panel import GeneratorPanel
import numpy as np
from seiswave.core.code_spec import CodeSpectrum

app = QApplication.instance() or QApplication(sys.argv)
gp = GeneratorPanel(dark=False)
gp.show()
cs = CodeSpectrum()
periods = np.logspace(-1, 1, 50)
sa = cs.from_params(periods, 8, 2, 'II', 'frequent', 0.05)
gp.set_code_spectrum(periods, sa)

assert gp._center_panel.width() >= 500, '中间区域宽度不足 500px'
assert gp._left_panel.width() <= 320, '左栏宽度超过 320px'
assert gp._right_panel.width() <= 280, '右栏宽度超过 280px'
assert gp._bottom_bar.height() <= 40, '底部栏高度超过 40px'

# 切换 NFP，验证右栏脉冲参数卡片显示
gp._param_form.set_type(3)
app.processEvents()
assert gp._right_panel._nfp_card.isVisible(), 'NFP 时脉冲参数卡片应显示'

print('✅ UI 布局验证通过: 左栏≤320px 中间≥500px 右栏≤280px 底部≤40px NFP卡片正常')
"
echo ""

# 6. 全量回归测试
echo "--- 6. 全量回归测试 ---"
python3 -m pytest tests/ -q --tb=short

echo ""
echo "========================================"
echo "  验收完成"
echo "========================================"

