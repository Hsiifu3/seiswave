# [Feature-001] SeisWave 特殊地震动生成功能 — 实现计划

## 架构概览

在现有 `WaveGenerator` 基础上，新增 **三层架构**：

```
WaveGenerator
├── generate(type="FF|NF|NFP", **params)     ← 统一入口
│   ├── FarFieldGenerator.generate()           ← FF 专用
│   ├── NearFieldNoPulseGenerator.generate()  ← NF 专用
│   └── NearFieldPulseGenerator.generate()     ← NFP 专用
│       ├── PulseCalculator.compute_params()   ← 脉冲参数计算
│       ├── PulseWavelet.generate()            ← MP 模型脉冲
│       ├── ResidualSpectrum.compute()         ← 残余谱分解
│       └── WaveCombiner.add()                 ← 脉冲+残余叠加
└── 现有谱匹配引擎（adjustspectra/fitspectra） ← 复用
```

## 组件设计

### 1. GroundMotionType (枚举/常量)
- `FF = "far_field"`
- `NF = "near_field_no_pulse"`
- `NFP = "near_field_pulse"`

### 2. GroundMotionParams (数据类)
- 震级 Mw
- 断层距 R (km)
- 场地 Vs30 (m/s)
- 断层类型 (strike-slip, normal, reverse)
- 方位角 (可选)
- 目标 PGA / PGV (可选，默认由 GMPE 计算)

### 3. FarFieldGenerator
- **职责**：远场地震动生成
- **接口**：`generate(params) -> EQSignal`
- **依赖**：
  - 现有 `WaveGenerator.generate()`
  - 远场包络参数预设
  - 远场 GMPE 目标谱
- **实现**：
  1. 用 Abrahamson et al. (2014) GMPE 计算目标谱
  2. 调用现有谱匹配引擎
  3. 应用远场包络（t₁=2-5s, t₂=15-40s）

### 4. NearFieldNoPulseGenerator
- **职责**：近场无脉冲地震动生成
- **接口**：`generate(params) -> EQSignal`
- **实现**：
  1. 用近场 GMPE 计算目标谱（R < 10km）
  2. 调用现有谱匹配引擎
  3. 应用近场包络（t₁=0.5-2s, t₂=10-25s）

### 5. NearFieldPulseGenerator (核心新增)
- **职责**：近场脉冲地震动生成
- **接口**：`generate(params) -> EQSignal`
- **子组件**：

#### 5a. PulseCalculator
- 输入：Mw, R, 断层类型
- 输出：脉冲参数 (Tp, A, φ, t₀)
- 公式：
  - `ln(Tp) = -6.68 + 1.15 Mw` (Mavroeidis & Papageorgiou, 2003)
  - `A = f(Mw, R, 断层类型)` (经验公式)
  - `φ = 0` 或 `π/2` (对称或单向)
  - `t₀ = T/4` (脉冲居中，T=总持时)

#### 5b. PulseWavelet
- 输入：脉冲参数
- 输出：脉冲速度时程 v_pulse(t)
- 公式：
  ```
  v_pulse(t) = (A/2) × [1 + cos(2π(t-t₀)/Tp)] × cos(2π(t-t₀)/Tp + φ)
  ```
  有效区间：t₀ - Tp/2 ≤ t ≤ t₀ + Tp/2
- 输出：求导得脉冲加速度 a_pulse(t)

#### 5c. ResidualSpectrum
- 输入：总目标谱 S_a^total，脉冲反应谱 S_a^pulse
- 输出：残余目标谱 S_a^residual
- 公式：`S_a^res = √(S_a^total² - S_a^pulse²)`

#### 5d. WaveCombiner
- 输入：a_pulse(t), a_residual(t)
- 输出：a_total(t) = a_pulse(t) + a_residual(t)
- 后处理：峰值裁剪、基线校正

### 6. PulseValidator
- **职责**：验证合成地震动是否符合脉冲特征
- **接口**：`validate(acc, dt) -> PulseMetrics`
- **方法**：
  - Baker (2007) 脉冲识别算法
  - 计算 PGV、脉冲周期 Tp、脉冲幅值
  - 返回置信度指标

### 7. GMPEAdapter
- **职责**：提供 GMPE 目标谱计算
- **接口**：`compute_spectrum(Mw, R, Vs30, type) -> (periods, Sa)`
- **实现**：
  - 短期：简化版 Abrahamson et al. (2014) 关键周期点插值
  - 中期：完整 NGA-West2 GMPE 接口

## 数据流

```
用户输入 (Mw, R, type)
    ↓
GroundMotionParams 解析
    ↓
[type == FF]  → FarFieldGenerator → GMPEAdapter → 目标谱 → 谱匹配 → 包络 → EQSignal
[type == NF]  → NearFieldNoPulseGenerator → GMPEAdapter → 目标谱 → 谱匹配 → 包络 → EQSignal
[type == NFP] → NearFieldPulseGenerator
    ↓
PulseCalculator (Tp, A, φ, t₀)
    ↓
PulseWavelet → v_pulse(t) → a_pulse(t)
    ↓
计算脉冲反应谱 S_a^pulse
    ↓
ResidualSpectrum: S_a^res = √(S_a^total² - S_a^pulse²)
    ↓
谱匹配引擎 → a_residual(t)
    ↓
WaveCombiner: a_total = a_pulse + a_residual
    ↓
PulseValidator 验证
    ↓
EQSignal 输出 (acc, vel, disp + 验证报告)
```

## 技术决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 脉冲模型 | MP 2003 / Kalkan 2006 / 自定义 | MP 2003 | 最广泛引用、数学简洁、工程实用 |
| 残余分量生成 | 频域减法 / 时域滤波 | 频域减法 | 能量守恒、与现有谱匹配兼容 |
| 脉冲参数来源 | 经验公式 / 统计拟合 / 用户输入 | 经验公式 + 用户微调 | 自动为主、手动为辅 |
| 总目标谱来源 | GMPE / 设计谱 / 用户输入 | GMPE 为主 | 最符合 FEMA P695 要求 |

## 错误处理

| 场景 | 策略 |
|------|------|
| 脉冲参数计算异常（如 Mw < 5.5） | 提示"脉冲模型不适用于小震"，回退到 NF 模式 |
| 残余谱为负（S_a^pulse > S_a^total） | 提示"脉冲能量超限"，缩放脉冲幅值使 S_a^pulse < 0.8 S_a^total |
| 谱匹配不收敛 | 增加迭代次数、放宽容差、或返回最佳 effort 结果 |
| Baker 识别验证不通过 | 提示"合成结果可能不含显著脉冲"，建议调整参数重试 |

## 影响范围

### 需要修改的文件
- `seiswave/core/generator.py` — 新增 GroundMotionType 分支和三个 Generator 类
- `seiswave/core/signal.py` — 可能需扩展 EQSignal 支持脉冲验证元数据
- `seiswave/gui/main_window.py` — 新增地震动类型选择 UI

### 新增文件
- `seiswave/core/pulse.py` — PulseCalculator, PulseWavelet, PulseValidator
- `seiswave/core/residual.py` — ResidualSpectrum
- `seiswave/core/gmpe.py` — GMPEAdapter（简化版）
- `seiswave/core/envelope_presets.py` — FF/NF/NFP 包络参数预设

### 潜在回归点
- 现有 `WaveGenerator.generate()` 的默认行为不能变
- 现有谱匹配引擎的精度和性能不能降
- Fortran/C 加速路径必须继续可用
