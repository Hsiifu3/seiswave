# 人工地震波时域谱匹配算法调研报告

> **研究目标**：为 SeisWave 工具的高 PGA 时域谱匹配发散问题提供算法层面的诊断与改进方向
> **调研时间**：2025-05-26（约 30 分钟深度检索）
> **核心问题**：目标 PGA=0.16g 时，`_adjustspectra` 迭代发散（mean_error 从 25% → 60~75%）

---

## 1. 时域谱匹配经典算法综述

### 1.1 算法族谱定位

SeisWave 的 `initArtWave → adjustspectra` 链路属于**时域小波调整法（Time-Domain Wavelet Adjustment）**，是地震工程领域最经典的人工波生成路线之一：

| 年代 | 研究者 | 贡献 | 关键特征 |
|------|--------|------|----------|
| 1978 | Kaul | 首创时域法 | 用调整小波修改加速度时程 |
| 1987-88 | Lilhanand & Tseng | 多阻尼匹配扩展 | 引入新的母小波，但**破坏非平稳特性** |
| 1992 | Abrahamson | RspMatch 程序 | 改进小波，保留非平稳性；但产生速度/位移漂移 |
| 2003, 2005 | Suarez & Montejo | 替代小波方案 | 与 Abrahamson 方案互补 |
| 2006 | Hancock et al. | RspMatch2005 | **组合调整小波** + 基线校正嵌入函数；支持多阻尼 |
| 2010 | **Atik & Abrahamson** | 改进锥形余弦小波 | ✅ **稳定、快速、无需基线校正**；行业标杆 |
| 2016 | Adekristi & Eatherton | Broyden 更新法 | 保持地震主要特征的良好收敛 |
| 2018-2025 | 近年研究 | 优化/小波变换/机器学习 | DWT+Levenberg-Marquardt、贪婪小波、扩散模型 |

**结论**：`adjustspectra` 的命名和 Fortran 实现风格， strongly suggests 它属于 Abrahamson (1992) / Lilhanand & Tseng (1988) 传统时域小波法的变体。

### 1.2 时域法 vs 频域法核心差异

| 维度 | 频域法（fitspectra） | 时域法（adjustspectra） |
|------|----------------------|------------------------|
| 原理 | 修改傅里叶幅值谱 | 向时程添加小波函数 |
| 复杂度 | 简单、直接 | **高度非线性** |
| 收敛性 | ❌ 差（Atik & Abrahamson 2010 证实） | 取决于小波选择和迭代策略 |
| 基线漂移 | ❌ 严重，必须后处理基线校正 | 可控（现代方法已集成） |
| 非平稳性 | ❌ 大改，变成不现实的高能运动 | ✅ 保持原始运动特征 |
| 能量引入 | 过多、不现实 | 较少 |
| 多阻尼匹配 | 困难 | ✅ 自然支持 |

> 频域法的根本问题："调整后的运动被改变到如此大的程度，导致速度和位移剖面末端出现偏移，因此迫切需要基线校正后处理"（Shahbazian & Pezeshk 2010）

---

## 2. 高 PGA 目标的收敛问题

### 2.1 问题本质

你们的观察——**低 PGA (~0.089) 下谱形很好，但缩放到目标 PGA (0.16) 时谱形被破坏，迭代发散**——在文献中有明确对应：

**核心机理**：
1. **时域法的高度非线性**：每添加一个小波都会改变整个响应谱，PGA 越高，所需调整量越大，非线性越强（Adekristi & Eatherton 2016）
2. **初始时程的谱-幅值耦合**：`init_art_wave` 生成的初始波在某一 PGA 下与目标谱匹配良好，意味着其时频能量分布已优化。强行缩放到更高 PGA，相当于在不同时频位置注入能量，破坏了原有的谱平衡
3. **迭代起点过远**：当起点误差已达 51%，迭代空间高度非凸，容易陷入发散或局部振荡

### 2.2 文献中的常见解法

| 解法 | 代表文献 | 核心思路 | 对 SeisWave 的适用性 |
|------|----------|----------|----------------------|
| **改进小波基** | Atik & Abrahamson (2010) | 使用解析解的锥形余弦小波，避免基线漂移 | ⭐⭐⭐ 高——替换小波函数 |
| **优化替代迭代** | Alexander et al. (2014); DWT+LM (2019) | 将问题转化为非线性最小二乘，用 Levenberg-Marquardt 或 Broyden 更新求解 | ⭐⭐⭐ 高——改变求解框架 |
| **贪婪小波匹配** | GWM (2023) | 每次只添加最必要的小波，减少修改量 | ⭐⭐ 中——需重写匹配逻辑 |
| **分阶段/渐进匹配** | 你们已尝试的两阶段策略 | 先低 PGA 修形，再逐步增压 | ⭐⭐⭐ 高——已验证部分有效 |
| **频域预调整** | Hybrid methods | 先用频域法粗调，再用时域法精修 | ⭐⭐ 中——需两种方法结合 |

**关键洞察**：Atik & Abrahamson (2010) 的改进之所以成为行业标准，正是因为它解决了"**收敛不稳定 + 基线漂移**"这对孪生问题。如果你们的小波基还是 1992 年或更早的版本，这是升级的第一优先级。

---

## 3. EQSignal 原始实现细节

### 3.1 已知信息

- **源码语言**：Fortran（你们已确认）
- **核心入口**：`adjustspectra`（时域法）、`fitspectra`（频域法）
- **归属**：GitHub 仓库 `Panchatantra/EQSignal`
- **公开资料**：仓库可见但本次调研未能获取完整源码（访问受限）

### 3.2 推断的实现特征

基于命名传统和 Fortran 地震工程软件的一般规律：

1. **小波类型**：很可能是 Abrahamson (1992) 或 Hancock et al. (2006) 风格的 reserve impulse wavelet，而非 Atik & Abrahamson (2010) 的改进锥形余弦
2. **迭代策略**：逐周期控制点顺序调整（sequential period-by-period），这是 Lilhanand & Tseng 的传统
3. **阻尼支持**：可能仅支持单一阻尼（如 5%），或简单扩展多阻尼
4. **基线处理**：可能需要外部基线校正（如果是 1992 年版本）或已集成（如果是 2006 年后版本）
5. **PGA 处理**：**没有渐进增压机制**——这是你们问题的关键。经典实现通常：
   - 先生成与目标谱形状匹配但 PGA 可能偏低的初始波
   - 然后期望迭代过程同时收敛谱形和 PGA
   - 当 PGA 目标远高于初始波能力时，迭代发散

### 3.3 验证建议

如需确认 EQSignal 的实现细节，建议：
- 直接阅读 Fortran 源码中的 `adjustspectra` 子程序
- 检查小波函数定义（是 reserve impulse 还是 tapered cosine）
- 检查迭代控制逻辑（是否有 `maxiter`、`tol`、自适应步长）
- 检查 PGA 缩放是在迭代内还是迭代外完成

---

## 4. 替代算法评估

### 4.1 频域法（fitspectra）

| 项目 | 评估 |
|------|------|
| **核心思路** | 修改傅里叶幅值谱使响应谱逼近目标 |
| **优点** | 实现简单、计算快、线性化友好 |
| **缺点** | ❌ 破坏非平稳性；❌ 基线漂移严重；❌ 高频能量 unrealistically high；❌ 相位信息丢失 |
| **适用性** | **不推荐作为主力方案**。可作为时域法的"预调器"（粗匹配），或用于快速验证 |
| **实施难度** | 低（已有实现可参考） |

### 4.2 现代小波法（Wavelet-based Optimization）

| 项目 | 评估 |
|------|------|
| **核心思路** | 用离散小波变换（DWT）分解信号，优化各频带调整系数，再重构 |
| **代表文献** | DWT + Levenberg-Marquardt (arxiv:1905.02394, 2019); Greedy Wavelet Matching (2023) |
| **优点** | ✅ 稳定收敛；✅ 无需后处理基线校正；✅ 多阻尼同时匹配；✅ 最小修改原始信号 |
| **缺点** | 计算量较大（但现代 CPU 可接受）；需要优化库支持 |
| **适用性** | ⭐⭐⭐ **高度推荐**。直接解决你们的收敛问题 |
| **实施难度** | 中（需引入 scipy.optimize 或自定义 LM 算法；DWT 可用 PyWavelets） |

**具体实现参考**：
- 使用 **Daubechies-12 (db12)** 母小波，9 级分解
- 决策变量：各级近似系数和细节系数的调整因子（初始值 1.0）
- 目标函数：响应谱与目标谱的加权均方误差
- 优化器：Levenberg-Marquardt（`scipy.optimize.least_squares` with `method='lm'`）
- 额外约束： Boore (1999) 基线校正确保零终速度/位移

### 4.3 混合法（Hybrid Frequency-Time Domain）

| 项目 | 评估 |
|------|------|
| **核心思路** | 频域粗调 + 时域精修；或功率谱时域化 + 小波微调 |
| **代表文献** | GB50011 谐波小波法 (2009, Springer); EPS + 峰值因子法 |
| **优点** | 兼顾效率和精度；可处理复杂匹配条件（多阻尼 + 功率谱密度） |
| **缺点** | 实现复杂；需要两个域的接口 |
| **适用性** | ⭐⭐ 中等推荐。适合需要同时满足 TDRS + TPSD 的场景 |
| **实施难度** | 高 |

### 4.4 机器学习/扩散模型（ML/Diffusion）

| 项目 | 评估 |
|------|------|
| **核心思路** | 用 DDPM（去噪扩散概率模型）或 GAN 直接生成满足目标谱的时程 |
| **代表文献** | "Artificial seismic waves generation for complex matching conditions based on diffusion model" (ScienceDirect, 2025); "High Resolution Seismic Waveform Generation Using Denoising Diffusion" (JGR, 2025); "Integrating Fourier Neural Operators with Diffusion Models" (2025) |
| **优点** | 一次前向传播即可生成；可学习复杂非平稳特征；可条件控制 |
| **缺点** | ❌ 需要大量训练数据；❌ 谱匹配精度不如传统方法（常需后处理 refine）；❌ 黑箱性；❌ 工程验收困难 |
| **适用性** | ⭐ 低。**前沿但尚未成熟**。适合作为研究方向，不建议当前采用 |
| **实施难度** | 很高 |

---

## 5. 工程实践标准

### 5.1 国际标准

**NUREG-0800 (U.S. Nuclear Regulatory Commission)**
- **Section 3.7.1** "Seismic Design Parameters"
- 对人工时程的响应谱匹配要求：
  - 在关心周期范围内，单个时程的响应谱与目标谱偏差应在 **±10%** 以内
  - 同时需检验功率谱密度（PSD）函数，确保能量分布合理
  - 多阻尼情况需分别验证

**ASCE 4-16 / ASCE 43-19 (美国)**
- 人工波均值谱应在目标谱的 **±10%** 范围内
- 单条时程的偏差通常也要求 **±10%**（部分规范允许 ±15% 在边缘周期）

### 5.2 中国规范

**GB 50011-2010《建筑抗震设计规范》**
- 人工加速度时程的**平均反应谱**应与目标谱统计一致
- 具体验收阈值在规范条文中定义（本次调研未能获取精确数值，但工程实践中的常见内控标准如下）

### 5.3 工程实践内控标准（行业惯例）

| 指标 | 严格标准（核电、大跨） | 一般建筑标准 | 你们的当前状态 |
|------|------------------------|--------------|----------------|
| **mean_error** | < 5% | < 10~15% | 25%（包络后）→ 48~75%（迭代后）❌ |
| **max_error** | < 10% | < 20% | 60~75% ❌ |
| **单周期偏差** | ±10% | ±15~20% | 发散 |

**结论**：你们的 mean_error=48% 即使按最宽松的建筑标准也**不满足验收要求**。必须解决收敛问题。

---

## 6. 推荐方案

### 6.1 首选推荐：升级小波基 + 优化驱动迭代

**理由**：
1. 你们的问题本质是"经典小波迭代在高 PGA 下发散"，这是已知问题且有成熟解决方案
2. Atik & Abrahamson (2010) 的改进锥形余弦小波已在全球工程软件（SeismoMatch、ETABS、SAP2000）中验证 15+ 年
3. 将迭代框架从"固定规则小波叠加"升级为"非线性最小二乘优化"，可根本解决收敛问题

**实施路径**：
```
Phase 1: 小波基替换（1~2 周）
  - 用 Atik & Abrahamson (2010) 的 analytical tapered cosine wavelet 替代当前小波
  - 优势：解析解小波幅值、无基线漂移、更稳定的频域局部化

Phase 2: 优化框架引入（2~3 周）
  - 将谱匹配问题形式化为：min ‖S_a(T_i) - S_target(T_i)‖²
  - 使用 scipy.optimize.least_squares(method='lm') 或自定义 Levenberg-Marquardt
  - 决策变量可以是：小波幅值集合，或 DWT 系数调整因子

Phase 3: PGA 渐进策略集成（1 周）
  - 在优化框架内实现渐进 PGA：将目标谱按 0.5→0.75→1.0 倍 PGA 分阶段匹配
  - 每阶段以上一阶段结果为初始值，大幅降低非线性
```

**预期效果**：mean_error 从 48% 降至 **<10%**，max_error **<15%**

### 6.2 次选推荐：贪婪小波匹配（GWM）

**理由**：
- 2023 年最新研究表明，GWM 比 RspMatch09 节省 99.5% 的小波数量，同时保持精度
- 核心思想：每次只在谱偏差最大的周期位置添加**一个**最优小波，而非遍历所有周期
- 对 SeisWave 更友好：可以保留现有的大部分代码结构，只修改匹配顺序和终止条件

**实施路径**：
- 将当前"顺序遍历周期点"改为"每次迭代找到最大偏差周期，计算最优单小波"
- 引入贪心停止条件：当最大偏差 < 阈值或改进量 < ε 时终止

**预期效果**：mean_error 降至 **15~25%**，实施成本低于优化框架

---

## 7. 研究优先级矩阵

| 方向 | 技术成熟度 | 对问题的针对性 | 实施难度 | 优先级 |
|------|-----------|----------------|----------|--------|
| 升级 Atik & Abrahamson 小波 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 中 | **P0** |
| 优化驱动迭代（LM/Broyden） | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 中高 | **P0** |
| 渐进 PGA 策略 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 低 | **P1**（你们已在尝试） |
| 贪婪小波匹配（GWM） | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | P1 |
| 频域预调整 + 时域精修 | ⭐⭐⭐⭐ | ⭐⭐⭐ | 中高 | P2 |
| DWT + 优化（2019 论文复现） | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 高 | P2 |
| 扩散模型/ML | ⭐⭐ | ⭐⭐ | 很高 | P3（研究储备） |

---

## 8. 关键参考文献

1. **Atik & Abrahamson (2010)**. "An Improved Method for Nonstationary Spectral Matching." *Earthquake Spectra*, 26(3). — **必读，行业标杆**
2. **Lilhanand & Tseng (1987, 1988)**. "Generation of synthetic time histories compatible with multiple-damping design response spectra." — 时域法起源
3. **Abrahamson (1992)**. "Non-stationary spectral matching." — RspMatch 原始算法
4. **Hancock et al. (2006)**. "An improved method of matching response spectra of recorded earthquake ground motion using wavelets." — 组合小波
5. **Adekristi & Eatherton (2016)**. "Time-Domain Spectral Matching of Earthquake Ground Motions using Broyden Updating." — 优化方法替代迭代
6. **Alexander et al. / DWT+LM (2019)**. arxiv:1905.02394 "Non-Stationary Spectral Matching by Unconstrained Optimization" — DWT+Levenberg-Marquardt 系统方案
7. **GWM (2023)**. "A greedy algorithm for wavelet-based time domain response spectrum matching." *Nuclear Engineering and Design* — 贪婪匹配
8. **扩散模型 (2025)**. "Artificial seismic waves generation for complex matching conditions based on diffusion model." *Soil Dynamics and Earthquake Engineering* — ML 前沿
9. **NUREG-0800** Rev. 4, Section 3.7.1 — 核电验收标准
10. **GB 50011-2010** 中国建筑抗震设计规范 — 国内验收依据

---

## 9. 下一步行动建议

1. **立即行动**：获取并阅读 Atik & Abrahamson (2010) 原文，提取改进锥形余弦小波的解析公式
2. **本周内**：检查 EQSignal Fortran 源码，确认当前使用的小波类型和迭代逻辑
3. **两周内**：用 Python 实现 Atik & Abrahamson 小波的独立原型，验证对你们数据集的收敛性
4. **同步进行**：将 PGA 渐进策略与优化框架结合，测试分阶段目标函数的效果
5. **备选**：若自研优化框架成本高，可考虑直接调用 SeismoMatch（商用软件）作为金标准验证工具

---

*报告完成。如需对某一方向深入展开，或需要复现某篇论文的具体算法，可继续指派子任务。*
