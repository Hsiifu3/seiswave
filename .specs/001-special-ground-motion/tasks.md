# [Feature-001] SeisWave 特殊地震动生成功能 — 任务列表

## 并行组 1（基础设施，可先执行）

### Task 1: 包络参数预设模块 [P]
- **描述**: 创建 `seiswave/core/envelope_presets.py`，定义 FF/NF/NFP 三类地震动的包络参数预设
- **文件**: `seiswave/core/envelope_presets.py`
- **验收标准**:
  - AC-1.1: 定义 `FarFieldEnvelope`、`NearFieldEnvelope`、`PulseEnvelope` 三个类或字典
  - AC-1.2: 参数基于文献经验值（FF: t₁=2-5s, t₂=15-40s; NF: t₁=0.5-2s, t₂=10-25s; NFP: t₁=0.2-1s, t₂=5-15s）
  - AC-1.3: 包含可调节接口（用户可覆盖参数）
  - AC-1.4: 单元测试验证包络形状正确
- **复杂度**: 简单
- **状态**: ✅ 已完成

### Task 2: 简化 GMPE 目标谱接口 [P]
- **描述**: 创建 `seiswave/core/gmpe.py`，提供简化版 Abrahamson et al. (2014) GMPE 目标谱计算
- **文件**: `seiswave/core/gmpe.py`
- **验收标准**:
  - AC-2.1: 输入 Mw, R, Vs30，输出周期-Sa 数组
  - AC-2.2: 覆盖常用周期范围 0.01s - 10s
  - AC-2.3: 区分 FF/NF 的近场/远场参数调整
  - AC-2.4: 有预设的标准参数集（如 FEMA P695 典型场景）
  - AC-2.5: 用户可输入自定义目标谱替代 GMPE
- **复杂度**: 中等
- **状态**: ✅ 已完成

## 并行组 2（脉冲核心，依赖组 1 完成）

### Task 3: 脉冲参数计算模块 [P]
- **描述**: 创建 `seiswave/core/pulse.py` 中的 `PulseCalculator`，基于 Mavroeidis & Papageorgiou (2003) 经验公式计算脉冲参数
- **文件**: `seiswave/core/pulse.py`（PulseCalculator 部分）
- **验收标准**:
  - AC-3.1: 输入 Mw，输出 Tp（`ln(Tp) = -6.68 + 1.15 Mw`）
  - AC-3.2: 输入 Mw, R, 断层类型，输出脉冲幅值 A（基于统计经验公式）
  - AC-3.3: 输出相位 φ（0 或 π/2）
  - AC-3.4: 输出脉冲起始时间 t₀（默认居中）
  - AC-3.5: 参数可用户覆盖
  - AC-3.6: 小震（Mw < 5.5）时返回 None 或异常提示
- **复杂度**: 中等
- **依赖**: Task 1
- **状态**: ✅ 已完成

### Task 4: MP 脉冲小波生成模块 [P]
- **描述**: 实现 `PulseWavelet`，生成 Mavroeidis & Papageorgiou (2003) 解析脉冲速度/加速度时程
- **文件**: `seiswave/core/pulse.py`（PulseWavelet 部分）
- **验收标准**:
  - AC-4.1: 实现公式 `v(t) = (A/2)[1+cos(2π(t-t₀)/Tp)]cos(2π(t-t₀)/Tp+φ)`
  - AC-4.2: 有效区间：t₀ - Tp/2 ≤ t ≤ t₀ + Tp/2，区间外为 0
  - AC-4.3: 速度时程求导得加速度时程
  - AC-4.4: 输出与文献图件形状一致（验证图）
  - AC-4.5: 单元测试：不同 φ 值产生对称/单向脉冲
- **复杂度**: 中等
- **依赖**: Task 3
- **状态**: ✅ 已完成

### Task 5: 残余谱分解与生成模块 [P]
- **描述**: 实现 `ResidualSpectrum`，从总目标谱中扣除脉冲分量，生成残余加速度
- **文件**: `seiswave/core/residual.py`
- **验收标准**:
  - AC-5.1: 输入总目标谱 S_a^total，计算脉冲反应谱 S_a^pulse
  - AC-5.2: 残余目标谱：`S_a^res = √(S_a^total² - S_a^pulse²)`
  - AC-5.3: 用现有谱匹配引擎生成残余加速度
  - AC-5.4: 处理 S_a^pulse ≥ S_a^total 的异常（缩放脉冲至 0.8×total）
  - AC-5.5: 残余分量本身无显著脉冲特征（Baker 识别为 false）
- **复杂度**: 中等
- **依赖**: Task 2, Task 4
- **状态**: ✅ 已完成

## 顺序组 3（集成与验证）

### Task 6: NFP 合成引擎集成
- **描述**: 实现 `NearFieldPulseGenerator`，整合脉冲分量 + 残余分量 + 叠加验证
- **文件**: `seiswave/core/generator.py`（新增 NearFieldPulseGenerator）
- **验收标准**:
  - AC-6.1: 输入 GroundMotionParams，输出完整加速度时程
  - AC-6.2: 输出包含脉冲速度时程和残余速度时程（方便查看）
  - AC-6.3: 叠加后总反应谱与目标谱误差 < 5%
  - AC-6.4: Baker (2007) 脉冲识别指标 > 0.85
  - AC-6.5: PGV > 100 cm/s（典型大震近场）
  - AC-6.6: 脉冲周期 Tp 符合震级经验关系
- **复杂度**: 复杂
- **依赖**: Task 3, Task 4, Task 5
- **状态**: ✅ 已完成

### Task 7: FF/NF 生成器集成
- **描述**: 实现 `FarFieldGenerator` 和 `NearFieldNoPulseGenerator`
- **文件**: `seiswave/core/generator.py`
- **验收标准**:
  - AC-7.1: FF 生成器：应用远场包络 + GMPE 目标谱 + 谱匹配
  - AC-7.2: NF 生成器：应用近场包络 + GMPE 目标谱 + 谱匹配
  - AC-7.3: 两者反应谱误差 < 5%
  - AC-7.4: FF 速度时程 Baker 识别为 false
  - AC-7.5: NF 速度时程 Baker 识别为 false
  - AC-7.6: 持时特征符合预期范围
- **复杂度**: 中等
- **依赖**: Task 1, Task 2
- **状态**: ✅ 已完成

### Task 8: 统一入口与类型分发
- **描述**: 扩展 `WaveGenerator.generate()`，支持 `type="FF|NF|NFP"` 参数分发
- **文件**: `seiswave/core/generator.py`
- **验收标准**:
  - AC-8.1: `generate(type="FF", **params)` 调用 FarFieldGenerator
  - AC-8.2: `generate(type="NF", **params)` 调用 NearFieldNoPulseGenerator
  - AC-8.3: `generate(type="NFP", **params)` 调用 NearFieldPulseGenerator
  - AC-8.4: 默认行为不变（type=None 时走现有通用谱匹配）
  - AC-8.5: 向后兼容：现有调用方式不受影响
- **复杂度**: 中等
- **依赖**: Task 6, Task 7
- **状态**: ✅ 已完成
- **测试**: 13/13 通过（tests/test_wave_generator_dispatch.py）

## 顺序组 4（UI 与验证）

### Task 9: GUI 地震动类型选择
- **描述**: 在 SeisWave GUI 中新增地震动类型下拉菜单和参数面板
- **文件**: `seiswave/gui/main_window.py`, `seiswave/gui/panels/generator_panel.py`, `seiswave/gui/workers.py`
- **验收标准**:
  - AC-9.1: 下拉菜单：一般人工波 / 远场 FF / 近场无脉冲 NF / 近场脉冲 NFP ✅
  - AC-9.2: 选择不同类型时动态显示/隐藏参数输入（如 NFP 显示断层类型）✅
  - AC-9.3: 生成后显示反应谱对比图 ✅
  - AC-9.4: NFP 生成后额外显示脉冲识别结果和脉冲参数 ✅
- **复杂度**: 中等
- **依赖**: Task 8
- **状态**: ✅ 已完成
- **测试**: 15/15 通过（tests/test_gui_generator_panel.py）

### Task 10: 最终验证与文档补全
- **描述**: 完成全项目回归测试，补全 Feature-001 文档（README.md），更新状态标记
- **文件**: `.specs/001-special-ground-motion/README.md`, `STATUS.md`, `tasks.md`
- **验收标准**:
  - AC-10.1: 三类地震动生成示例代码已写入 README.md ✅
  - AC-10.2: 关键参数推荐值已记录 ✅
  - AC-10.3: 已知限制和注意事项已记录 ✅
  - AC-10.4: 全项目回归测试 310/310 通过 ✅
  - AC-10.5: STATUS.md 中 Feature-001 标记为 100% 完成 ✅
- **复杂度**: 简单
- **依赖**: Task 6, Task 7, Task 8, Task 9
- **状态**: ✅ 已完成
- **测试**: 310/310 通过

## 验证计划

- [ ] 编译/构建通过（Python + Fortran/C）
- [ ] 现有测试全部通过（无回归）
- [ ] 新增模块单元测试覆盖率 > 80%
- [ ] FF/NF/NFP 各生成 10 条样本，人工检查反应谱和时程形状
- [ ] NFP 样本通过 Baker (2007) 脉冲识别验证
- [ ] 与 FEMA P695 真实记录统计特征对比（均值、标准差、谱形状）
- [ ] 文档更新：README + API 文档 + 使用示例

## 任务依赖图

```
Task 1 (包络预设) ──┬──→ Task 3 (脉冲参数) ──→ Task 4 (脉冲小波) ──┐
                    │                                           │
Task 2 (GMPE) ──────┴────────────────────────→ Task 5 (残余谱) ──┼──→ Task 6 (NFP集成)
                                                                │
                                                               Task 8 (统一入口)
                                                                │
                                                               Task 9 (GUI)
                                                                │
                                                               Task 10 (验证)

Task 1 ──→ Task 7 (FF/NF生成)
Task 2 ──→ Task 7
```
