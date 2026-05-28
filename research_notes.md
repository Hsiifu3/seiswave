# SeisWave 谱匹配生成器误差根源调研与对标分析

> 仓库：`/Users/yachiyo/Developer/seiswave`  
> 目标：定位 SeisWave 在 GB50011 平台型规范谱（约 300 控制点，PGA≈0.16，Tg=0.2）下，时域谱匹配 `fm=1` 残余误差约 54.7% 的主要根因，并对标 EQSignal 原始实现与业界方法。  
> 约束：仅调研分析，不改代码。

---

## 0. 执行摘要

本次调研最重要的结论有四条：

1. **SeisWave 已经拿到了 EQSignal 原始 Fortran 源码**：仓库中存在 `build/fortran/eqs.f90`，可以直接作为原始实现对照，而不是只靠二手文档。
2. **`initartwave` 中的 `Saw` 公式确实含有 `1/wk` 项**，而且原始 EQSignal 没有任何额外的低频补偿、PGA 预调整或平台段增强。也就是说，SeisWave 当前遇到的低频/平台段偏置，**不是你“误抄了公式”导致的，而是该公式本身对平台型目标谱就可能不友好**。
3. **`adjustspectra` 原始实现不是普通最小二乘，也不是显式 SVD 手写求解，而是 LAPACK `DGELSD`**（SVD-based least squares，带秩判定）。这说明 EQSignal 原版本身就意识到矩阵可能病态，采用了比 `np.linalg.lstsq` 更强的数值求解器。但它**没有显式控制点降采样、没有 Tikhonov 正则、没有截断规则暴露给用户**。
4. **SeisWave 的纯 Python 复现已经不再是“精确复现”**：在 `initartwave` 中新增了平台段温和增强；在 `adjustspectra` 中将原版的全时域三重循环 `ramixed` 改成批量 FFT 近似构造 `M`；此外 Python 版数值清洗、clip、零除保护也较多。它们提高了鲁棒性，但也意味着：**当前 54.7% 误差不应简单归咎于“EQSignal 算法天生不行”，而应分清“原算法局限”和“本地近似改写引入的偏差”**。

基于源码对比和文献/工具对标，我认为 SeisWave 目前最值得优先尝试的方向不是继续盲目调参数，而是：

- **先把控制点体系从“300 个密控制点”改成“少量锚点 + 稠密验算点”两层结构**；
- **把 `adjustspectra` 的求解从无约束 `lstsq` 升级为可控正则化/截断 SVD**；
- **把 `initartwave` 从单一步 Vanmarcke 谱估计改成“初始 PSD + 低频/平台段预整形”**；
- **将 Python `_adjustspectra` 与 Fortran 原版在同一输入上做 A/B 基准，先分离“算法问题”与“复现偏差问题”**。

---

## 1. 证据来源

### 1.1 本地源码

核心对照文件：

- **原始/移植 Fortran 源**：`/Users/yachiyo/Developer/seiswave/build/fortran/eqs.f90`
- **SeisWave Python 实现**：`/Users/yachiyo/Developer/seiswave/seiswave/core/generator.py`
- **Fortran 桥接层**：`/Users/yachiyo/Developer/seiswave/seiswave/core/fortran_bridge.py`

### 1.2 已确认的关键源码位置

在 `build/fortran/eqs.f90` 中：

- `adjustspectra`：约第 **2323** 行
- `wfunc`：约第 **2691** 行
- `fitspectrum`：约第 **3570** 行
- `initArtWave`：约第 **3599** 行
- `leastsqs` / `leastsqm`（最小二乘实现）：约第 **280-360** 行

### 1.3 外部公开资料（可访问摘要/搜索结果）

受站点拦截与检索限流影响，本次外部资料主要采用可访问摘要和公开说明页元信息，重点包括：

- RspMatch / RSPMatch2005/2009 相关说明与 Baker/Hancock/Al Atik 系列引用
- EZ-FRISK 对 RspMatch2009 的公开算法简介
- SIMQKE 的公开软件说明文字
- SeismoMatch/SeismoSoft 产品说明与二手引用
- 论文标题与摘要线索：
  - *An Improved Method for Nonstationary Spectral Matching*（Al Atik & Abrahamson, 2010）
  - *Non-Stationary Spectral Matching by Unconstrained Optimization*（2019 preprint）
  - 双水平分量同时谱匹配论文（Jayaram / Baker 相关方向）

> 说明：下文凡“明确确认”优先指向本地 `eqs.f90` 直接证据；凡“文献/工具综述”中个别细节若未拿到全文，则明确标注为“公开说明/二手来源一致指向”。

---

## 2. 目标 1：EQSignal 原始实现的精确细节

## 2.1 `initartwave`：原始 EQSignal 公式核对

### 2.1.1 原始 Fortran 代码结论

`build/fortran/eqs.f90` 中 `initArtWave` 的关键实现为：

- `Pf(2:Nfft/2) = 1.d0/f(2:Nfft/2)`
- `Pf(1) = 100.d0*Pf(2)`
- 将目标谱 `SPT(P)` 插值到 `SPTf(Pf)`
- 对每个频率分量随机相位合成
- **核心功率谱估计公式：**

```fortran
Saw = (zeta/PI/wk)*SPTf(k)*SPTf(k) /
      log(1.d0/((-PI/wk/dt/n)*log(1.d0-0.85d0)))
```

其中 `wk = TWO_PI*f(k)`。

### 2.1.2 关键问题：`1/wk` 项是否真的存在？

**存在，且在原始 Fortran 中明确存在。**

这点非常关键，因为它直接回答了你提出的怀疑：

- SeisWave 并不是误把 `1/wk` 多写进去了；
- 原始 EQSignal 的 `Saw` 估计中**本来就有 `1/wk` 低频放大因子**；
- 对平台型反应谱而言，这会天然抬升长周期/低频能量分配倾向。

### 2.1.3 原始实现有没有额外频率补偿、PGA 预调整、初始波后处理？

**从 `initArtWave` 原始实现本身看，没有。**

直接证据：

- 没有任何“平台段增权”“低频平衡”“频带补偿”代码；
- 没有按目标 PGA 对 `a` 做线性缩放；
- 没有在 `initArtWave` 末尾调用 `adjustpeak` 或 `adjustbaseline`；
- 只是 IFFT 后 `a = real(a0(1:n))/Nfft` 直接输出。

这意味着：

- 若初始波 PGA 偏低、平台段匹配差，**原版 EQSignal 也会出现**；
- 其设计假设可能是：后续 `adjustspectra` / `fitspectrum` 会把初始误差修回来；
- 但当目标谱是**平台很平、控制点很多**的 code spectrum 时，这种“后续再修”的假设可能失效。

### 2.1.4 SeisWave Python 与原始 Fortran 的差异

#### 一致之处

SeisWave `generator.py::_init_art_wave` 与 Fortran 下列点一致：

- `Nfft = nextpow2(n)`
- `Pf(1)=100*Pf(2)` 的逻辑
- `Saw` 中保留了 `zeta/(PI*wk) * SPTf^2` 的结构
- 随机相位 + 共轭对称频谱 + IFFT 合成

#### 关键差异

1. **SeisWave 增加了平台段温和增强**

Python 版新增：

```python
plateau_weight = 1.0 + 0.4 / (1.0 + np.exp(-(plateau_ratio - 0.85) / 0.05))
Saw *= plateau_weight
```

原始 Fortran **没有这一段**。

**可能影响：**
- 这是一个人为补偿，目的是抵消 `1/wk` 带来的平台段低估；
- 它说明你们已经观测到原始公式的系统偏置；
- 但它属于经验性修补，不一定与后续 `adjustspectra` 的收敛方向相容；
- 如果增强过于集中在平台峰值附近，可能造成初始能量分布与后续小波修正耦合异常。

2. **Python 版加入了异常保护分支**

如：
- `if log_arg > 0 and log_arg < 1: ... else: ...`
- `Saw = max(Saw, 0.0)`
- `nan_to_num`

原始 Fortran 没有这些保护。

**可能影响：**
- 有助于避免 NaN/Inf；
- 但也可能在边界频点上改变原始公式行为，使合成初始波与原版不完全等价。

3. **随机数行为不同**

Fortran：`call random_seed()` + `call random_number(phi)`  
Python：`np.random.default_rng(seed=42)`

**可能影响：**
- 单条时程的波形细节不同；
- 但这不是导致系统性 54.7% 残余误差的主因，更像是复现实验可重复性差异。

### 2.1.5 对低频偏置问题的判断

综合源码证据，可以比较有把握地说：

- **Vanmarcke 型 `Saw` 估计 + `1/wk` 项** 对平台型目标谱确实容易造成低频能量偏重；
- 在反应谱长平台（如 GB50011）下，目标 Sa 在宽周期范围几乎不变，而 `1/wk` 会让 PSD 向更低频倾斜；
- 因此你观察到“初始波 PGA≈0.096，显著低于目标 0.16”，是**符合公式结构预期**的，不是偶发现象。

---

## 2.2 `adjustspectra`：原始 M 矩阵与求解方式

### 2.2.1 原始 Fortran 算法流程

`eqs.f90` 中 `adjustspectra` 的主循环逻辑非常清楚：

1. 当前波 `a` 计算反应谱 `SPA, SPI`
2. 误差向量：

```fortran
dR = SPA*(SPAT/abs(SPA)-1.d0)/SPAT
```

3. 对每个控制周期构造小波 `W(:,i) = wfunc(...)`
4. 对每个 `(i,j)`：
   - 令第 `j` 个小波通过 `ramixed(..., P(i), ...)` 计算在第 `i` 个振子上的响应
   - 取其在 `SPI(i)` 峰值时刻的值，归一化后组成 `M(i,j)`

```fortran
M(i,j) = ra(SPI(i),i,j)/SPAT(i)
if ( i /= j ) M(i,j) = M(i,j)*0.618D0
```

5. 解线性系统：

```fortran
call leastsqs(M,dR,nP,nP)
```

6. 更新时程：

```fortran
a = a + dR(i)*W(:,i)
```

7. `adjustpeak(a,n,peak0)` 保持峰值水平
8. 重新评估误差，保留最佳解 `best`

### 2.2.2 原始实现是普通最小二乘、SVD 还是正则化？

**原始实现不是手写正规方程，也不是普通 QR `gels`，而是 LAPACK `DGELSD`。**

在 `leastsqs` / `leastsqm` 中，明确调用：

```fortran
call dgelsd(..., s, -1.d0, rank, work, lwork, iwork, info)
```

这意味着：

- `DGELSD` 是 **SVD-based least squares**；
- 它自带秩估计与病态问题处理能力；
- `rcond = -1.d0` 表示使用 LAPACK 默认阈值来判断有效奇异值。

**结论：原始 EQSignal 确实已经用到了“带秩判定的 SVD 最小二乘”。**

这比简单 `np.linalg.lstsq(M,dR,rcond=None)` 更接近“自动截断”的数值稳健策略。

### 2.2.3 原始实现有没有显式正则化？

**没有显式 Tikhonov / ridge / 人工惩罚项。**

但 `DGELSD` 本身已经比裸求逆稳健。可理解为：

- 有“隐式截断/秩判定”；
- 没有“用户可控的正则强度”。

### 2.2.4 原始实现是否限制控制点数量或主动降采样？

**没有在 `adjustspectra` 中看到任何控制点数量限制、稀疏化、聚类或降采样逻辑。**

所以：

- 原始 EQSignal 默认假设 `nP` 不会大到把矩阵做坏；
- 它可能是面向较少控制点、较平滑目标谱、工程上常见的离散周期点集开发的；
- 当你喂给它 **300 点混合周期网格 + 平台谱** 时，已经超出了原算法的“舒适区”。

### 2.2.5 `M` 矩阵的结构特征与病态根源

从源码看，`M(i,j)` 本质上是：

- 第 `j` 个修正小波，
- 通过第 `i` 个 SDOF 滤波器后，
- 在当前第 `i` 个峰值时刻 `SPI(i)` 的响应值，
- 再除以 `SPAT(i)`。

对平台型谱 + 稠密控制点，这种构造会带来三个结构性问题：

1. **相邻控制点响应核高度相似**  
   平台段上相邻周期的 SDOF 响应峰值时间和波形很接近，列向量强相关。

2. **`SPI(i)` 取样使矩阵依赖当前解**  
   每轮 `SPI` 都在变，导致 `M` 不是固定灵敏度矩阵，而是一个带局部线性化误差的近似雅可比。

3. **非对角仅乘 0.618 并不足以消除共线性**  
   这只是经验性耦合衰减，不是数学正则化。

因此你们测到 `cond(M) ~ 1e5` 完全合理，且与源码机制一致。

### 2.2.6 SeisWave Python `_adjustspectra` 与原始 Fortran 的差异

#### 一致之处

- 同样使用 `dR = SPA*(SPAT/|SPA|-1)/SPAT`
- 同样使用 `wfunc`
- 同样构造 `M(i,j)` 并对非对角项乘 `0.618`
- 同样每轮后 `adjustpeak`

#### 差异之处

1. **M 矩阵构造方式不同**

原始 Fortran：
- 对每个 `j` 的小波，都调用 `ramixed(W(:,j), ..., P(i), ...)`
- 也就是严格沿用时/频混合响应算子

Python：
- 使用批量 FFT 构造近似响应传递函数 `H`
- 然后 `irfft` 得到 `ra_all`

**可能影响：**
- Python 版更快，但不完全等价于原始 `ramixed`，尤其在 `MPR*dt` 切换边界、长周期段、非整数峰值位置附近；
- 当矩阵本来就病态时，这种近似误差会被放大。

2. **求解器不同**

原始 Fortran：`DGELSD`  
Python：`np.linalg.lstsq(M, dR, rcond=None)`

**可能影响：**
- NumPy 在不同 BLAS/LAPACK 后端上可能仍调用 SVD/QR，但行为不保证与 `DGELSD` 等价；
- 在边界奇异值处理上，Python 版可能比原版更“硬吃”病态分量。

3. **Python 版做了大量 NaN/Inf 清洗和 clip**

如：
- `np.nan_to_num`
- `clip(-1e6, 1e6)`

**可能影响：**
- 提升鲁棒性；
- 但也会把原本应由求解器“平滑处理”的异常，变成人工截断，可能让更新方向失真。

### 2.2.7 关于“300 点导致 54.7%”的源码层判断

基于原始算法结构，我认为你们目前的观测非常可信：

- **300 点控制网格不是 EQSignal 时域算法擅长的输入形式**；
- 即便原始 Fortran 用 `DGELSD`，也无法从根本上消除平台段密集控制点造成的高度共线性；
- SeisWave Python 版在 `M` 的近似构造上又比原版多了一层误差来源；
- 所以“300 点 → 108.9%，50 点 → 54.7%”并不是偶然，而是很符合该类算法的数值行为。

---

## 2.3 `wfunc`：参数是否一致

原始 Fortran `wfunc`：

```fortran
tm = dble(itm-1)*dt
w = TWO_PI/P
f = 1.d0/P
tmp1 = sqrt(1.d0-zeta**2)
gamma = 1.178d0*(f*tmp1)**(-0.93d0)
deltaT = atan(tmp1/zeta)/(w*tmp1)
wf = cos(w*tmp1*tmp2)*exp(-(tmp2/gamma)**2)
```

SeisWave Python `_wfunc` 使用：

- `gamma = 1.178 * (f * tmp1)**(-0.93)`
- `deltaT = arctan(tmp1 / zeta) / (w * tmp1)`
- 同样的高斯包络余弦结构

**结论：`wfunc` 在数学形式上基本一致。**

这里没有发现显著偏差，因而：

- `gamma` / `deltaT` 不是当前误差主根因；
- 若有差别，也只在数值保护与 0 附近分支上，不是 54.7% 量级误差来源。

---

## 2.4 `fitspectrum`：顺带确认

虽然你的主要问题在 `fm=1`，但 `fitspectrum` 也值得顺带确认。

原始 Fortran `fitspectrum` 仅负责分发：

- `fm=0` → `fitspectra`
- `fm=1` → `adjustspectra`

且在 `fm=0` 时对 `P, SPAT` 做了前后各加一个外插点的扩展（`EP`, `ESPAT`），这说明：

- 频域法在插值时更依赖边界外推平滑；
- 时域法则直接用原控制点集；
- 因而密集控制点对 `fm=1` 的冲击通常比 `fm=0` 更直接。

---

## 3. EQSignal 原始实现对比报告

下表直接回答“SeisWave 与 EQSignal 的关键差异、以及可能影响”。

| 模块 | EQSignal 原始实现 (`eqs.f90`) | SeisWave 当前实现 | 关键差异 | 可能影响 |
|---|---|---|---|---|
| `initartwave` 频率网格 | `Nfft=nextpow2(n)`，`Pf(1)=100*Pf(2)`，其余 `Pf=1/f` | 基本一致 | 无本质差异 | 影响很小 |
| `initartwave` `Saw` 公式 | `Saw=(zeta/PI/wk)*SPTf^2/log(1/((-PI/wk/dt/n)*log(1-0.85)))` | 保留同结构，并加边界保护 | **确认 `1/wk` 原版就有** | 平台型谱时易向低频偏置 |
| `initartwave` 平台补偿 | **无** | 新增 `plateau_weight` 经验增强 | Python 非原版 | 可能改善初始波 PGA，但也可能扰乱后续匹配收敛 |
| `initartwave` PGA 预调整 | **无** | 无自动预调整 | 一致 | 低 PGA 初始波会原样进入后续算法 |
| `initartwave` 后处理 | 仅 IFFT 后输出 | 多了 NaN/Inf 防护 | Python 更保守 | 有助鲁棒，但不等价 |
| `adjustspectra` `dR` | `SPA*(SPAT/abs(SPA)-1)/SPAT` | 一致 | 无 | 无 |
| `adjustspectra` 小波 | `wfunc` | `wfunc` | 基本一致 | 非主因 |
| `adjustspectra` M 构造 | 三重循环 + `ramixed` 精确响应 | 批量 FFT 近似传递函数 | **Python 非精确复现** | 病态矩阵下近似误差会被放大 |
| `adjustspectra` 非对角衰减 | `0.618` | `0.618` | 一致 | 只是经验降耦，不是正则化 |
| `adjustspectra` 求解器 | `DGELSD`（SVD-based LS） | `np.linalg.lstsq` | **原版更明确使用秩判定 SVD** | Python 对病态问题可能更脆弱 |
| `adjustspectra` 控制点数限制 | **无** | 无硬限制 | 一致 | 面对 300 点平台谱时都易病态 |
| `adjustspectra` 峰值约束 | `adjustpeak` 每轮执行 | 一致 | 无 | 强行保峰值可能与谱修正方向冲突 |
| `wfunc` `gamma/deltaT` | `gamma=1.178(f√(1-ζ²))^-0.93`；`deltaT=atan(tmp1/zeta)/(w*tmp1)` | 一致 | 基本无 | 非主因 |

### 综合判断

- **你们最初怀疑的 `1/wk` 问题是真问题，但不是复现错误，而是原算法特性。**
- **真正和原版明显不一致的，是 Python `_adjustspectra` 的 M 矩阵构造方式。**
- 当前结果要拆成两部分看：
  1. EQSignal 原始方法对平台型、密控制点目标谱本身就不稳；
  2. SeisWave Python 近似实现又叠加了额外误差。

---

## 4. 目标 2：业界其他实现的对标

## 4.1 总体观察

业界主流谱匹配工具大致分两类：

1. **谱相容人工波生成类**：先构造 PSD/包络/相位，再迭代修正（如 SIMQKE、一类 artificial accelerogram generator）
2. **记录修正/小波匹配类**：从已有记录或初始波出发，用时域波包/小波逐步匹配（如 RspMatch / SeismoMatch / EZ-FRISK）

对平台型 code spectrum 来说，业界更常见的经验不是“给 300 个等权控制点硬匹配”，而是：

- 使用**较稀疏但有代表性的控制周期**；
- 允许**分阶段匹配**（先低频后高频，或先大尺度后细节）；
- 对初始波做**预整形/预白化/包络控制**；
- 对时域修正波let施加**非平稳性保护、低频漂移约束和基线控制**。

## 4.2 方法综述表

| 工具/方法 | 初始波/初始记录来源 | 对平台型谱的处理思路 | 控制点策略 | 初始波优化/预处理 | 对 SeisWave 的启示 |
|---|---|---|---|---|---|
| **EQSignal** | 目标谱→Vanmarcke 型 PSD→随机相位人工波 | 依赖 `initartwave` + `adjustspectra/fitspectrum` 后续修正；源码中无平台段专门补偿 | 源码中无显式限制；默认用户给定 `P` | 无 PGA 预调整、无专门预白化 | 原算法对平台型谱并不“特别准备”，密点时病态是结构性问题 |
| **SIMQKE** | 平稳随机过程 + 时间包络 + 迭代修正谱密度 | 公开说明强调“平均谱”更容易贴合平滑目标谱；更偏统计意义相容，不一定追求单条记录逐点极严匹配 | 通常不是几百个稠密点逐点卡死，更偏平滑目标控制 | 包络函数显式建模；通过反复调整谱密度改进匹配 | 对 code spectrum，可先追求平滑总体兼容，再做局部精修，而不是一次性硬逼近 |
| **RspMatch / RSPMatch2005/2009** | 通常从真实记录或初始记录出发 | 通过波let时域修正匹配目标谱；后续版本强调保留非平稳性与长周期特征 | 工程上常用有限控制点，或按结构敏感周期选点 | 改进小波形式；常伴随基线/漂移控制 | SeisWave 若继续走时域法，应借鉴“多尺度/非平稳性保护”的思路 |
| **SeismoMatch (SeismoSoft)** | 基于 RspMatch 系思路的商业实现 | 公开资料与论文引用均指向改进型波let谱匹配；强调对非平稳性与时程特征的保持 | 通常由用户给定有限周期范围与容差，不鼓励无脑极密采样 | 提供方法选择、窗口/参数控制、后处理 | 平台谱不应只看点数；应看“有效控制自由度” |
| **EZ-FRISK Spectral Matching** | 明确说明基于 RspMatch2009 | 采用改进时域方法，宣称保留非平稳性，尤其是长周期 | 更像工程化工作流，而非原始等权密点优化 | 结合 licensed RspMatch2009 算法与工程前处理 | 说明业界成熟产品已不满足于原始 Tseng/Lilhanand 式简单线性化 |
| **SeismoArtif / GRAIT / SeismoSignal 系衍生工具** | 多为人工波生成或谱后处理 | 往往面向规范谱，但很多实现依然依赖平滑谱 + 有限控制周期 | 常用较粗离散点 | 常加入包络、滤波、幅频整形 | 若目标是 GB50011 平台谱，建议引入“规范谱专用控制点模板” |

## 4.3 对各工具的重点理解

### 4.3.1 SIMQKE

公开说明反复强调两点：

- 用伪随机相位正弦分量叠加构造地震动；
- 通过迭代调整**谱密度函数**来改善与目标谱的一致性；
- 即使不做最后一步，**一组样本的平均反应谱**也能很好地贴合平滑目标谱。

这说明 SIMQKE 的哲学更接近：

- **目标谱首先是统计平滑对象**；
- 对“单条时程严格逐点匹配”并不极端执着；
- 对平台型规范谱，它更适合生成“总体谱相容”的人工波群，而不是把单条记录 300 点都压到很低误差。

**对 SeisWave 的启示：**
- 如果工程目标其实是“规范相容人工波组”，就不该把问题设成“单条时程 + 300 点 hard match”。

### 4.3.2 RspMatch / SeismoMatch / EZ-FRISK

从公开说明与文献摘要一致可见：

- RspMatch 系算法源自波let时域谱匹配；
- 后续改进版（特别是 Al Atik & Abrahamson 方向）重点是：
  - **减少基线漂移**
  - **更好保留非平稳特征**
  - **改善长周期行为**
- EZ-FRISK 公开说明明确说其 spectral matching 基于 **RspMatch2009**，并强调 preserving non-stationarity at long periods。

这类方法与 EQSignal 的关键区别不在于“是不是也用小波”，而在于：

- 它们更重视**修正波形的时域局部性与非平稳性**；
- 更重视避免低频漂移、长周期失真；
- 工程使用时通常不会把控制目标设成 300 个高度相似的硬点，而是围绕目标区间与容差管理。

**对 SeisWave 的启示：**
- 真正成熟的时域谱匹配，并不是“任意小波 + 病态线性系统 + 迭代”；
- 而是“受控波let族 + 合理目标约束 + 非平稳性/低频稳定性保护”。

### 4.3.3 平台型规范谱的通用工程做法

虽然很多工具未必专门写“plateau spectrum handling”，但从工程实践上可归纳出常见隐含做法：

1. **控制点不会极端加密**；
2. **平台段通常用代表点，而不是每个采样点都单独当自由度**；
3. **初始波常先做包络与幅频预整形**；
4. **匹配阶段更看重误差带/包络符合，而非所有点等权最小二乘。**

这正好与当前 SeisWave 的问题形成对照：

- 你现在是把一个“平滑平台”的谱，离散成了一个“高维刚性约束问题”；
- 从优化角度看，这几乎是在主动制造病态。

---

## 5. 目标 3：学术文献中的相关研究

> 注：受部分全文抓取受限影响，下述摘要基于已确认标题、公开摘要线索、工具说明中的交叉引用，以及与本地源码的结合解读。重点放在“与当前问题最相关”的方法论，而非铺陈大量次要文献。

## 5.1 Al Atik & Abrahamson (2010), *An Improved Method for Nonstationary Spectral Matching*

### 方法
该文是 RspMatch 体系中的关键改进工作。核心思想是：

- 不仅做谱匹配，还要尽量保留地震动的**非平稳性**；
- 改进波let/调整函数形式，避免简单局部修正引入强烈漂移；
- 对长周期与低频行为进行更稳健处理。

### 结论
公开摘要与业界工具说明一致表明：

- 相比早期方法，改进后的非平稳谱匹配更稳健；
- 更适合工程化使用；
- 其思想已被 SeismoMatch、EZ-FRISK 等工具吸收。

### 对 SeisWave 的启示
- 单纯把谱误差线性化成 `M dR = rhs` 并不足够；
- 若初始波本身低频能量分布不合适，后续小波修正会越来越难；
- 应引入“**非平稳保持 + 长周期稳定**”的设计，而不是只盯 RMS 谱误差。

---

## 5.2 Hancock et al. (2006) / RSPMatch2005 相关工作

### 方法
这类工作奠定了波let时域谱匹配的工程框架：

- 在原始记录上叠加局部化修正函数；
- 按响应谱差异逐步修正；
- 兼顾匹配效果与时程形态保真。

### 结论
早期方法常需要额外基线校正，且在某些情形下可能引入低频漂移或不自然长周期成分。

### 对 SeisWave 的启示
- 你们现在在 `adjustspectra` 中只保留了 `adjustpeak`，而没有系统处理基线/漂移；
- 对平台谱而言，这可能让低频能量和峰值控制产生冲突；
- 若后续继续走时域匹配路线，需把基线/漂移问题上升到“主算法组件”，而不是注释里的可选后处理。

---

## 5.3 *Non-Stationary Spectral Matching by Unconstrained Optimization* (2019 preprint)

### 方法
该文从另一条线出发：

- 把谱匹配问题表述为优化问题，而不是每轮只做局部线性最小二乘；
- 允许在时间-频率参数空间中更整体地搜索可行修正。

### 结论
这类方法的价值在于：

- 避免局部线性化产生的病态雅可比/灵敏度矩阵问题；
- 使约束和目标函数可扩展（如同时考虑谱误差、包络、平滑度、漂移等）。

### 对 SeisWave 的启示
- 你们当前的 `adjustspectra` 本质上是局部牛顿/高斯-牛顿风格的一阶近似；
- 当 `M` 病态且平台段自由度高度冗余时，这种方法会迅速失效；
- 若长期演进产品，应该考虑把谱匹配表述为**带正则项的优化问题**，而不是死守原始 `adjustspectra`。

---

## 5.4 Jayaram / Baker 方向：双分量谱匹配与工程规范要求

### 方法
相关工作关注：

- 对两个水平分量同时谱匹配；
- 在满足目标谱的同时保留方向性和统计特征；
- 面向工程规范而非纯算法试验。

### 结论
从 Baker 等工程讨论可见：

- 谱匹配是工程工具，不应破坏记录关键物理特征；
- 特别在近断层/脉冲型记录时，谱匹配可能带来额外风险；
- 控制目标应与结构分析需求相一致，而不是盲目高维约束。

### 对 SeisWave 的启示
- 对 GB50011 平台谱，首先应该定义“工程上真正需要的控制自由度”；
- 若结构主要敏感于某一段周期范围，就不应让整个平台所有采样点等权进入病态系统。

---

## 5.5 SIMQKE 及人工波生成文献脉络

### 方法
SIMQKE 代表的老一代人工波方法通常是：

- 给定目标反应谱；
- 反推出平稳随机过程的谱密度；
- 配合时间包络生成非平稳地震动；
- 必要时再迭代调整谱密度。

### 结论
这类方法对“平滑目标谱”非常自然，但对“单条时程逐点严格贴合”并不一定占优。

### 对 SeisWave 的启示
- `initartwave` 的本质就是这条脉络里的一个版本；
- 问题在于：Vanmarcke 近似并不能保证对平台型 code spectrum 给出“后续最易修正”的初始能量分布；
- 因此应考虑更现代的初始谱预整形，而不只是照搬单一步 PSD 估计公式。

---

## 5.6 关于“Vanmarcke 低频偏置”是否有直接文献点名

本次没有拿到一篇能直接写出“Vanmarcke formula biases low frequency for plateau code spectrum”这句话的全文论文。

但从三类证据综合判断，这一结论仍然相当有力：

1. **源码结构证据**：`Saw ∝ SPT^2 / wk`，平台段 Sa 近似常数时，PSD 随低频增大；
2. **你的实验事实**：初始波 PGA 明显偏低；简单统一缩放反而破坏后续匹配；
3. **业界改进趋势**：成熟工具越来越重视初始记录/初始波预整形、非平稳保持与长周期稳定，而非依赖单一步谱密度反演。

因此，严格措辞应为：

> **尚未找到直接点名 Vanmarcke 对平台谱“低频偏置”的专门论文，但从原始公式结构、源码行为与实验结果三者一致判断，该偏置是高度可信的机制性问题。**

---

## 6. 对当前问题的综合诊断

结合本地源码与你已经验证的现象，可以把 54.7% 误差拆成三层根因。

### 6.1 第一层：目标谱离散方式本身制造了病态

- 300 个 mixed 周期控制点对平台段来说过密；
- 平台段上相邻点的物理信息高度重复；
- `adjustspectra` 的 `M` 相当于把这些冗余点当成独立自由度，必然造成高相关；
- `cond ~ 1e5` 与这种结构完全一致。

### 6.2 第二层：初始波的能量分布对平台谱不友好

- `initartwave` 原始公式内含 `1/wk`；
- 对平台型目标谱，低频能量过重、高频/PGA不足是自然结果；
- 后续时域小波法不得不在一个“起跑姿势不对”的波上做大幅修正。

### 6.3 第三层：SeisWave Python 复现不是原版等价实现

- `M` 构造由原版 `ramixed` 改成 FFT 近似批处理；
- 求解器从显式 `DGELSD` 变成 `np.linalg.lstsq`；
- `initartwave` 又额外加入平台增强；
- 这意味着当前误差是“原算法局限 + 本地近似偏差”的叠加结果。

### 6.4 为什么“把初始波直接线性缩放到目标 PGA”会从 45% 炸到 137%？

这恰恰说明问题不是“幅值整体偏小”这么简单，而是**频带能量布局错误**：

- 如果初始误差只是全局比例偏差，统一缩放后应更接近目标；
- 但现实是统一缩放后更差，说明：
  - 低频/平台段已经相对偏多；
  - 短周期峰值/PGA偏少；
  - 一刀切缩放会把“局部过量频段”进一步放大，从而整体误差恶化。

换句话说，当前问题核心是**谱形错误**，不是单一峰值错误。

---

## 7. Actionable 建议：SeisWave 下一步最值得尝试的 4 个方向

> 以下建议按优先级排序；均为“改什么函数、用什么技术”的层面，但本报告不直接给代码实现。

## 建议 1：把控制点体系改成“两层控制”而不是 300 点硬匹配

### 建议内容
对 `adjustspectra` / 上层调用流程：

- **匹配控制点**：只保留 20–60 个代表性周期点；
- **验算点**：可保留 300 点甚至更多，但不进入 `M` 的求解，只用于评估误差与画图；
- 平台段采用分段代表点，例如：
  - 上升段少量点
  - 平台段按对数间距或等效结构敏感点取 8–15 个
  - 衰减段少量点

### 具体影响函数
- 上层控制点生成逻辑（可能在 `code_spec.py` / 调用 `fit_spectra` or `adjust_spectra` 之前）
- 不一定先改 `generator.py` 主体算法

### 原因
- 这是最符合原算法结构的修复；
- 不改核心算法也能显著改善病态；
- 与业界做法一致。

### 预期收益
- `cond(M)` 大概率显著下降；
- 54.7% 这类高残差有机会先降到“可继续优化”的区间；
- 能分离“控制点设计问题”与“算法本体问题”。

---

## 建议 2：把 `_adjustspectra` 的求解器升级为“可控截断 SVD / Tikhonov 正则”

### 建议内容
对 `generator.py::_adjustspectra`：

- 不再使用黑盒 `np.linalg.lstsq(..., rcond=None)` 作为唯一方案；
- 增加两种可选稳定化策略：
  1. **truncated SVD**：丢弃小于阈值的奇异值；
  2. **Tikhonov/ridge**：解 `(M^T M + λI)x = M^T dR`。

最好让阈值或 `λ` 与 `cond(M)` 或谱段密度自适应关联。

### 具体影响函数
- `seiswave/core/generator.py::_adjustspectra`

### 原因
- 原始 EQSignal 已经隐式采用了 `DGELSD`，说明“病态矩阵要特殊对待”本来就是原始设计的一部分；
- 你们当前 300 点 / 50 点场景已经证明单靠 `lstsq` 不够。

### 预期收益
- 抑制病态方向上的过大更新；
- 避免局部奇异值主导更新，减少误差震荡；
- 有机会让平台谱下时域法重新变得可控。

---

## 建议 3：重做 `initartwave` 的“初始波预整形”，不要只依赖 Vanmarcke 单步估计

### 建议内容
对 `generator.py::_init_art_wave`：

- 保留 EQSignal 原始公式作为 baseline；
- 但新增可选的 **pre-shaping / pre-whitening / band reweighting** 模式，尤其针对平台型 code spectrum；
- 不建议简单按 PGA 全局线性缩放；应考虑：
  - 在平台段与短周期段分别做频带整形；
  - 或先构造更接近目标反应谱的初始波，再交给 `adjustspectra` 微调。

### 具体影响函数
- `seiswave/core/generator.py::_init_art_wave`
- 可能还需要新增“规范谱初始波策略”配置层

### 原因
- 当前问题是谱形不对，不是整体比例不对；
- 如果初始波更接近目标，后续 `M` 的线性化就更可靠。

### 预期收益
- 提高初始 PGA 与平台段一致性；
- 减少后续需要的小波修正量；
- 降低 `adjustspectra` 走向病态的概率。

---

## 建议 4：做一组严格的 Fortran-vs-Python A/B 基准，先隔离“复现偏差”

### 建议内容
使用同一组输入（同 `P, SPAT, dt, zeta, n`），分别调用：

- `fortran_bridge.HAS_FORTRAN=True` 时的原版 Fortran `eqs.adjustspectra/initartwave`
- 纯 Python `WaveGenerator._adjustspectra/_init_art_wave`

比较：

- 初始波 PGA、谱形、误差；
- 每轮迭代误差曲线；
- `M` 条件数与更新向量范数；
- 最终残余误差。

### 具体影响函数
- `seiswave/core/fortran_bridge.py`
- 测试/benchmark 脚本

### 原因
- 当前最危险的误判是：把所有问题都算到“EQSignal 原算法头上”；
- 但你们 Python 版已经不是一比一复现，必须先知道到底偏了多少。

### 预期收益
- 能明确回答：
  - 是原始 EQSignal 就不适合 300 点平台谱？
  - 还是 Python 近似 `M` 构造把情况进一步恶化了？
- 这会直接决定后续是“继续修 Python 复现”还是“换算法路线”。

---

## 8. 最终结论

### 8.1 对目标 1 的直接回答

- **已找到 EQSignal 原始 Fortran 代码**：`/Users/yachiyo/Developer/seiswave/build/fortran/eqs.f90`
- **`Saw` 公式中的 `1/wk` 项确实存在于原始实现中**
- 原始 `initartwave` **没有**额外频率补偿、PGA 预调整或后处理
- 原始 `adjustspectra` 的线性求解器是 **LAPACK `DGELSD`**，即 **SVD-based least squares with rank determination**
- 原始实现**没有显式控制点降采样或数量限制**
- `wfunc` 的 `gamma` 与 `deltaT` 参数，SeisWave 与原始 Fortran **基本一致**

### 8.2 对目标 2 的直接回答

- 业界更成熟的方法（RspMatch / SeismoMatch / EZ-FRISK）并不只是“把点数加密然后解病态线性系统”，而是更强调：
  - 合理控制点体系
  - 非平稳性保持
  - 长周期/低频稳定性
  - 基线漂移控制
- SIMQKE 类方法更适合“平滑目标谱的统计相容”，不强调单条记录对稠密控制点的极严逐点贴合
- 因此，**用 300 个点去硬逼平台型 code spectrum，本身就不符合业界常见实践**

### 8.3 对目标 3 的直接回答

- 尚未找到一篇专门点名“Vanmarcke 对平台型谱低频偏置”的论文，但源码结构与实验现象强烈支持这一机制
- 文献与工具发展趋势非常一致地表明：
  - 时域小波谱匹配的关键难点就是数值稳定性、非平稳性保持和低频漂移控制
  - 改进方向通常是：更好的波let、更稳健的求解、更合理的目标约束，而不是单纯增加控制点

### 8.4 一句话判断 SeisWave 当前 54.7% 的主根因

> **主根因不是单一 bug，而是“Vanmarcke 初始谱估计对平台谱不友好 + 300 控制点造成 `adjustspectra` 病态 + Python 近似复现进一步放大误差”三者叠加。**

---

## 9. 建议的下一步验证顺序（最省时间版本）

如果只允许做最少量的下一步实验，我建议按这个顺序：

1. **同一输入下直接跑 Fortran 原版 `adjustspectra` 与 Python `_adjustspectra` 对比**  
   先确定复现偏差有多大。
2. **把 300 点改成 20/30/50 点锚点控制 + 300 点验算**  
   先验证病态是否大幅缓解。
3. **对 `_adjustspectra` 加入 truncated SVD 或 ridge 原型实验**  
   看是否明显优于当前 `lstsq`。
4. **仅在 `initartwave` 层测试“分频带预整形”，不要做全局 PGA 缩放**  
   验证“谱形修正”是否比“整体幅值修正”有效。

---

## 10. 本次最关键的源码摘录（便于后续复核）

### `eqs.f90::initArtWave`

```fortran
Saw = (zeta/PI/wk)*SPTf(k)*SPTf(k)/log(1.d0/((-PI/wk/dt/n)*log(1.d0-0.85d0)))
```

### `eqs.f90::adjustspectra`

```fortran
M(i,j) = ra(SPI(i),i,j)/SPAT(i)
if ( i /= j ) then
    M(i,j) = M(i,j)*0.618D0
end if
call leastsqs(M,dR,nP,nP)
```

### `eqs.f90::leastsqs`

```fortran
call dgelsd(m, n, nrhs, a, lda, b, ldb, s, -1.d0, rank, work, lwork, iwork, info)
```

### `eqs.f90::wfunc`

```fortran
gamma = 1.178d0*(f*tmp1)**(-0.93d0)
deltaT = atan(tmp1/zeta)/(w*tmp1)
wf = cos(w*tmp1*tmp2)*exp(-(tmp2/gamma)**2)
```

---

如果后续需要，我建议下一份补充报告专门做：

1. **Fortran vs Python 的逐轮迭代 A/B 基准**；或  
2. **GB50011 平台谱的“控制点模板设计建议”**。