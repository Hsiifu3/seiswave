# SeisWave 重构与实施方案

> 生成日期：2026-02-15
> 状态：方案文档（不涉及代码修改）

---

## 一、现有代码结构分析

### 1.1 核心模块 (`seiswave/core/`)

| 文件 | 职责 | 代码量 | 状态 |
|------|------|--------|------|
| `signal.py` | EQSignal 类：加速度/速度/位移时程管理、积分、基线校正、滤波、重采样、反应谱计算 | ~250行 | ✅ 完善 |
| `spectrum.py` | Spectra 类：Newmark-β / 频域 / 混合法反应谱计算，周期数组生成 | ~220行 | ✅ 完善但慢 |
| `generator.py` | WaveGenerator：人工波生成（频域谱匹配 + 时域调整），包含包络函数、初始波生成、迭代拟合 | ~350行 | ⚠️ 性能瓶颈 |
| `selector.py` | WaveSelector：三步选波（持时→谱偏差→底部剪力），SelectionCriteria/SelectionResult 数据类 | ~200行 | ⚠️ 功能不足 |
| `io.py` | FileIO：AT2/TXT/CSV 读写，EQRecord 数据类，批量加载 | ~250行 | ⚠️ 需扩展 |
| `filter.py` | Filter：多项式去趋势、双线性去趋势、Butterworth/FFT 滤波 | ~180行 | ✅ 完善 |
| `fft.py` | FFT：傅里叶振幅谱、Welch PSD、相位谱 | ~100行 | ✅ 完善 |
| `code_spec.py` | CodeSpectrum：GB 50011 / Eurocode 8 / ASCE 7 设计反应谱 | ~200行 | ✅ 完善 |
| `response.py` | Response：响应计算（未详细分析） | - | - |

### 1.2 GUI 模块 (`seiswave/gui/`)

| 文件 | 职责 | 状态 |
|------|------|------|
| `panels/import_panel.py` | 目录浏览、文件加载、波形预览（PySide6） | ✅ 基本完善 |
| `panels/selector_panel.py` | 周期输入、筛选条件、选波执行（Worker 线程） | ⚠️ 需配合选波引擎重构 |
| `panels/generator_panel.py` | 目标谱设置、生成参数、迭代可视化 | ⚠️ 需配合生成器重构 |
| `workers.py` | QThread Worker 基类及各计算 Worker | ✅ 架构良好 |

### 1.3 已有 Fortran 加速

项目中已存在 `_newmark.so`，说明之前已有部分 Fortran/C 扩展尝试。


### 1.4 关键问题诊断

**性能瓶颈**：`generator.py` 的 `_fit_spectra_freq()` 方法每次迭代需要：
1. 计算完整反应谱（`Spectra.compute()` 遍历 ~200 个周期，每个周期一次 Newmark/FFT）
2. 频域谱匹配调整（FFT → 修改幅值 → IFFT）
3. PGA 约束调整

纯 Python 的 `_newmark_beta()` 对每个周期做子步插值循环（MPR=20），N=4096 点 × 200 周期 = 约 80 万次循环迭代，50 次外层迭代 = 4000 万次，这是卡住的根本原因。

**选波引擎不足**：
- 当前 `WaveSelector` 仅做三步过滤（持时→谱偏差→底部剪力），不支持：
  - PEER NGA 元数据解析（RSN、事件名、台站、分量）
  - 按反应谱匹配度排序选出最优 N 条
  - 天然波+人工波组合策略
  - 按分量方向过滤（水平/竖向）

---

## 二、EQSignal Fortran 函数分析与复用

### 2.1 eqs.f90 核心函数清单

**`basic` 模块（基础工具）**：

| 函数 | 功能 | Python 对应 | 复用价值 |
|------|------|-------------|----------|
| `polyblc` | 多项式基线校正（分段拟合位移后反推加速度） | `Filter.detrend()` | ⭐⭐⭐ 算法更优 |
| `polydetrend` | 多项式去趋势 | `Filter.detrend()` | ⭐⭐ 已有等价实现 |
| `interp` | 线性插值 | `np.interp` | ⭐ 无需复用 |
| `fftfreqs` | FFT 频率数组 | `np.fft.fftfreq` | ⭐ 无需复用 |
| `nextpow2` | 下一个 2 的幂 | 内联实现 | ⭐ 无需复用 |
| `leastsqs` | 最小二乘求解 | `np.linalg.lstsq` | ⭐ 无需复用 |
| `targetdc` | 目标位移基线校正 | 无 | ⭐⭐⭐ 新功能 |

**`eqs` 模块（核心计算）**：

| 函数 | 功能 | Python 对应 | 复用价值 |
|------|------|-------------|----------|
| `rnmk` | Newmark-β 单自由度响应（含子步插值） | `Spectra._newmark_beta()` | ⭐⭐⭐⭐⭐ 性能关键 |
| `rfreq` | 频域法单自由度响应 | `Spectra._freq_domain()` | ⭐⭐⭐⭐ 性能关键 |
| `rmixed` | 混合法（短周期频域+长周期 Newmark） | `Spectra.compute(method="mixed")` | ⭐⭐⭐⭐⭐ 性能关键 |
| `spamixed` | 混合法反应谱（遍历周期数组） | `Spectra.compute()` | ⭐⭐⭐⭐⭐ 最核心 |
| `spanmk` | Newmark 法反应谱 | `Spectra.compute(method="newmark")` | ⭐⭐⭐⭐ |
| `spafreq` | 频域法反应谱 | `Spectra.compute(method="freq")` | ⭐⭐⭐⭐ |
| `fitspectra` | 频域谱匹配迭代 | `WaveGenerator._fit_spectra_freq()` | ⭐⭐⭐⭐⭐ 性能关键 |
| `adjustspectra` | 时域谱匹配迭代（wfunc 基函数法） | `WaveGenerator._fit_spectra_time()` | ⭐⭐⭐⭐⭐ 性能关键 |
| `initArtWave` | 根据目标谱生成初始随机波 | `WaveGenerator._generate_initial()` | ⭐⭐⭐⭐ |
| `wfunc` | 时域调整基函数 | `WaveGenerator._wavelet()` | ⭐⭐⭐⭐ |
| `rsimple` | 简化 SDOF 响应（用于符号判断） | 无直接对应 | ⭐⭐⭐ |
| `adjustpeak` | PGA 约束调整 | `WaveGenerator._adjust_peak()` | ⭐⭐⭐ |
| `adjustbaseline` | 基线校正（生成过程中） | 无 | ⭐⭐⭐ |
| `newmark` | 单周期 Newmark（返回谱值） | 内含于 `Spectra.compute()` | ⭐⭐⭐⭐ |
| `spectrum` | 统一反应谱接口 | `Spectra.compute()` | ⭐⭐⭐⭐ |
| `spectrumavd` | 完整反应谱（加速度+速度+位移+能量） | `Spectra.compute()` | ⭐⭐⭐⭐ |
| `rnmknl` | 非线性 Newmark（滞回模型） | 无 | ⭐⭐ 未来扩展 |
| `spmu` | 等延性反应谱 | 无 | ⭐⭐ 未来扩展 |
| `whiteNoise` | 白噪声生成 | 无 | ⭐⭐ |


### 2.2 性能提升预估

| 计算环节 | 纯 Python 耗时 | Fortran+OpenMP 预估 | 加速比 |
|----------|----------------|---------------------|--------|
| 反应谱计算（200 周期） | ~8s/条 | ~0.05s/条 | ~160x |
| 频域谱匹配（单次迭代） | ~10s | ~0.1s | ~100x |
| 时域谱匹配（单次迭代） | ~15s | ~0.2s | ~75x |
| 完整人工波生成（50 迭代） | >10min（卡住） | ~10s | >60x |
| 批量反应谱（701 条） | ~90min | ~35s | ~150x |

---

## 三、f2py 编译集成方案

### 3.1 编译策略

EQSignal 的 `eqs.f90` 依赖 FFTW3，不能直接用 `f2py` 编译。推荐方案：

**方案 A：f2py + FFTW3 链接（推荐）**

```bash
# 1. 安装 FFTW3
brew install fftw

# 2. 编译 Fortran 模块
cd /Users/yachiyo/Developer/seiswave
f2py -c \
  --f90flags="-fopenmp -O3" \
  -lgomp \
  -I/Users/yachiyo/homebrew/include \
  -L/Users/yachiyo/homebrew/lib \
  -lfftw3 \
  -m _eqsignal \
  /Users/yachiyo/Developer/EQSignal_ref/libeqs/eqs.f90

# 3. 生成 _eqsignal.cpython-3xx-darwin.so
```

**方案 B：ctypes 调用共享库**

```bash
# 编译为共享库
gfortran -shared -fPIC -O3 -fopenmp \
  -I/Users/yachiyo/homebrew/include \
  -L/Users/yachiyo/homebrew/lib \
  -lfftw3 \
  -o libeqs.dylib \
  /Users/yachiyo/Developer/EQSignal_ref/libeqs/eqs.f90
```

然后通过 `ctypes` 调用 `bind(c)` 函数。

**推荐方案 A**，因为：
- f2py 自动处理数组维度和类型转换
- 更 Pythonic 的调用接口
- NumPy 数组直接传递，零拷贝

### 3.2 需要暴露的 Fortran 函数

按优先级排序：

```
# P0 - 必须（解决性能瓶颈）
spectrum        → 统一反应谱计算入口
spectrumavd     → 完整反应谱（含速度/位移/能量谱）
fitspectra      → 频域谱匹配
adjustspectra   → 时域谱匹配
initArtWave     → 初始波生成

# P1 - 重要（提升整体性能）
spamixed        → 混合法反应谱
rmixed          → 混合法单自由度响应
rnmk            → Newmark 单自由度响应
rfreq           → 频域单自由度响应

# P2 - 有用（信号处理增强）
polyblc         → 多项式基线校正
targetdc        → 目标位移基线校正
adjustpeak      → PGA 约束
adjustbaseline  → 基线校正

# P3 - 未来扩展
rnmknl          → 非线性响应
spmu            → 等延性谱
whiteNoise      → 白噪声
```

### 3.3 Python 封装层设计

新建 `seiswave/core/fortran_bindng.py`：

```python
"""
EQSignal Fortran 加速后端

自动检测 Fortran 扩展是否可用，不可用时回退到纯 Python。
"""

import numpy as np

try:
    from . import _eqsignal as _f  # f2py 编译的模块
    HAS_FORTRAN = True
except ImportError:
    HAS_FORTRAN = False

def spectrum_mixed(acc, dt, zeta, periods):
    """混合法反应谱（Fortran 加速）"""
    if HAS_FORTRAN:
        n = len(acc)
        nP = len(periods)
        spa = np.zeros(nP)
        spi = np.zeros(nP, dtype=np.int32)
        _f.spectrum(acc, n, dt, zeta, periods, nP, spa, spi, 3)  # SM=3 mixed
        return spa, spi
    else:
        from .spectrum import Spectra
        sp = Spectra.compute(acc, dt, periods, zeta, method="mixed")
        return sp.sa, np.zeros(len(periods), dtype=np.int32)

def fit_spectra(acc, dt, zeta, periods, target_sa, tol=0.05, max_iter=50):
    """频域谱匹配（Fortran 加速）"""
    if HAS_FORTRAN:
        n = len(acc)
        nP = len(periods)
        result = np.zeros(n)
        _f.fitspectra(acc, n, dt, zeta, periods, nP, target_sa, result, tol, max_iter, 1)
        return result
    else:
        # 回退到纯 Python
        from .generator import WaveGenerator
        return WaveGenerator._fit_spectra_freq_pure(acc, dt, zeta, periods, target_sa, tol, max_iter)

def adjust_spectra(acc, dt, zeta, periods, target_sa, tol=0.05, max_iter=50):
    """时域谱匹配（Fortran 加速）"""
    if HAS_FORTRAN:
        n = len(acc)
        nP = len(periods)
        result = np.zeros(n)
        _f.adjustspectra(acc, n, dt, zeta, periods, nP, target_sa, result, tol, max_iter, 1)
        return result
    else:
        from .generator import WaveGenerator
        return WaveGenerator._fit_spectra_time_pure(acc, dt, zeta, periods, target_sa, tol, max_iter)

def init_art_wave(n, dt, zeta, periods, target_sa):
    """根据目标谱生成初始随机波（Fortran 加速）"""
    if HAS_FORTRAN:
        nP = len(periods)
        result = np.zeros(n)
        _f.initartwave(result, n, dt, zeta, periods, nP, target_sa)
        return result
    else:
        from .generator import WaveGenerator
        return WaveGenerator._generate_initial_pure(n, dt, zeta, periods, target_sa)
```


---

## 四、PEER NGA 天然波集成方案

### 4.1 AT2 文件解析增强

当前 `FileIO.read_at2()` 已能解析 AT2 格式，但缺少元数据提取。需要增强：

**从文件名提取**：`RSN{rsn}_{event}_{station}{component}.AT2`
- RSN 编号（整数）
- 地震事件名
- 台站名
- 分量方向（通过后缀判断：含 UP/DWN/V 为竖向，其余为水平）

**从文件头提取**：
- AT2 文件前 4 行为头信息，第 4 行含 `NPTS` 和 `DT`
- 部分文件头包含事件信息（震级、距离等）

### 4.2 新增数据模型

新建 `seiswave/core/peer_nga.py`：

```python
@dataclass
class PeerRecord:
    """PEER NGA 地震记录"""
    rsn: int                    # RSN 编号
    event: str                  # 地震事件名
    station: str                # 台站名
    component: str              # 分量标识（原始文件名中的）
    direction: str              # 方向分类：'H1', 'H2', 'V'
    filepath: str               # AT2 文件路径
    dt: float                   # 时间步长
    npts: int                   # 数据点数
    pga: float                  # 峰值加速度 (g)
    duration: float             # 持时 (s)
    acc: np.ndarray | None      # 加速度时程（延迟加载）
    spectrum: Spectra | None    # 反应谱（延迟计算）

@dataclass
class PeerEvent:
    """PEER NGA 地震事件（包含同一事件的所有记录）"""
    event_name: str
    records: list[PeerRecord]

    def get_horizontal_pairs(self) -> list[tuple[PeerRecord, PeerRecord]]:
        """获取水平分量对"""
        ...

class PeerDatabase:
    """PEER NGA 数据库管理器"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.records: dict[int, list[PeerRecord]] = {}  # RSN -> records
        self._index_built = False

    def build_index(self, progress_callback=None) -> int:
        """扫描目录，建立索引（不加载波形数据）"""
        ...

    def load_record(self, record: PeerRecord) -> np.ndarray:
        """延迟加载单条记录的波形数据"""
        ...

    def filter(self, rsn_range=None, events=None, direction=None,
               pga_range=None, duration_range=None) -> list[PeerRecord]:
        """按条件过滤记录"""
        ...

    def save_index(self, filepath: str):
        """保存索引到 JSON/pickle，避免每次重新扫描"""
        ...

    def load_index(self, filepath: str) -> bool:
        """加载已有索引"""
        ...
```

### 4.3 选波引擎重构

重构 `seiswave/core/selector.py`，新增基于反应谱匹配的自动选波：

```python
@dataclass
class SpectrumMatchCriteria:
    """反应谱匹配选波条件"""
    target_spectrum: np.ndarray     # 目标反应谱值
    periods: np.ndarray             # 周期数组
    zeta: float = 0.05              # 阻尼比
    n_select: int = 7               # 选取数量
    n_natural: int = 5              # 天然波数量（剩余为人工波）
    period_range: tuple = (0.1, 6.0)  # 匹配周期范围
    tolerance: float = 0.3          # 单条波允许的最大偏差
    mean_tolerance: float = 0.15    # 平均谱允许的最大偏差
    scale_range: tuple = (0.5, 2.0) # 允许的缩放系数范围
    direction: str = 'H'            # 'H' 水平 / 'V' 竖向

class SpectrumMatcher:
    """反应谱匹配选波引擎"""

    def __init__(self, criteria: SpectrumMatchCriteria):
        self.criteria = criteria

    def compute_match_score(self, record_spectrum: np.ndarray,
                            target: np.ndarray,
                            period_mask: np.ndarray) -> tuple[float, float]:
        """
        计算单条波的匹配度评分

        返回：(最优缩放系数, 匹配误差)
        匹配误差 = 周期范围内 |Sa_record * scale - Sa_target| / Sa_target 的均方根
        """
        ...

    def rank_records(self, database: PeerDatabase,
                     progress_callback=None) -> list[tuple[PeerRecord, float, float]]:
        """
        对所有记录计算匹配度并排序

        返回：[(record, scale_factor, match_error), ...] 按 match_error 升序
        """
        ...

    def select_optimal(self, database: PeerDatabase,
                       progress_callback=None) -> SelectionResult:
        """
        自动选出最优 N 条天然波

        算法：
        1. 计算所有记录的反应谱（利用 Fortran 加速）
        2. 对每条记录求最优缩放系数（最小二乘法）
        3. 按匹配误差排序
        4. 贪心选择：依次选入误差最小的波，检查组合后的平均谱偏差
        5. 确保平均谱在目标谱的 ±tolerance 范围内

        GB 50011 要求：
        - 7 条波时取平均值，3 条波时取包络值
        - 每条波的反应谱在统计意义上与目标谱相容
        - 平均谱不低于目标谱的 0.65 倍（多遇）或 0.80 倍（罕遇）
        """
        ...

    def _greedy_combination(self, ranked: list, n: int) -> list:
        """贪心组合选择：确保组合后平均谱满足规范要求"""
        ...
```

### 4.4 批量反应谱预计算

701 条记录的反应谱预计算是选波的前提。设计缓存机制：

```
data/peer_nga/
├── *.AT2, *.DT2, *.VT2          # 原始数据
├── _cache/
│   ├── index.json                # 文件索引（RSN、事件、分量、PGA、持时）
│   ├── spectra_z005.npz          # 阻尼比 0.05 的反应谱缓存
│   └── spectra_z010.npz          # 阻尼比 0.10 的反应谱缓存（隔震用）
```

缓存格式（NumPy npz）：
```python
{
    'periods': np.ndarray,          # (n_periods,) 周期数组
    'rsn': np.ndarray,              # (n_records,) RSN 编号
    'sa': np.ndarray,               # (n_records, n_periods) 反应谱矩阵
    'pga': np.ndarray,              # (n_records,) PGA
    'direction': list[str],         # (n_records,) 方向
}
```

这样选波时只需加载 npz 文件（~几 MB），无需重新计算反应谱。


---

## 五、EQSignal 信号处理功能复用分析

### 5.1 已有 Python 实现 vs Fortran 实现对比

| 功能 | Python 实现 | Fortran 实现 | 差异 | 建议 |
|------|-------------|-------------|------|------|
| 多项式去趋势 | `Filter.detrend()` | `polydetrend` | 等价 | 保留 Python |
| 双线性去趋势 | `Filter.bilinear_detrend()` | 无直接对应 | Python 独有 | 保留 Python |
| 多项式基线校正 | 无 | `polyblc`（分段拟合位移→反推加速度） | Fortran 更优 | **新增 Python 封装** |
| 目标位移校正 | 无 | `targetdc`（指定位移零点→校正加速度） | Fortran 独有 | **新增 Python 封装** |
| Butterworth 滤波 | `Filter.butterworth()` | 无 | Python 独有（scipy） | 保留 Python |
| FFT 滤波 | `Filter.fft_filter()` | 无 | Python 独有 | 保留 Python |
| 积分（acc→vel→disp） | `EQSignal.integrate()` | `ratacc2vd` | 等价（梯形法） | 保留 Python |
| 重采样 | `EQSignal.resample()` | `interp` | Python 用 scipy | 保留 Python |
| 傅里叶振幅谱 | `FFT.amplitude_spectrum()` | FFT 内部使用 | 等价 | 保留 Python |
| Welch PSD | `FFT.welch_psd()` | 无 | Python 独有 | 保留 Python |

### 5.2 需要从 Fortran 新增的功能

1. **`polyblc` - 分段多项式基线校正**
   - 比简单去趋势更精确：先积分得位移，对位移做分段多项式拟合，再二次微分回加速度
   - 适用于强震记录的长周期漂移校正
   - 建议封装到 `Filter.poly_baseline_correction()`

2. **`targetdc` - 目标位移基线校正**
   - 指定若干时间点的目标位移值（通常为零），通过最小二乘拟合校正加速度
   - 适用于已知最终位移应为零的场景
   - 建议封装到 `Filter.target_displacement_correction()`

3. **`adjustpeak` + `adjustbaseline` - 生成过程中的约束调整**
   - 人工波生成迭代中保持 PGA 不变、基线不漂移
   - 已在 `generator.py` 中有简化实现，Fortran 版更鲁棒
   - 建议在 `fortran_binding.py` 中封装

---

## 六、文件修改清单

### 6.1 新增文件

| 文件 | 用途 | 优先级 |
|------|------|--------|
| `seiswave/core/fortran_binding.py` | Fortran 加速后端封装（f2py） | P0 |
| `seiswave/core/peer_nga.py` | PEER NGA 数据库管理（索引、加载、缓存） | P0 |
| `seiswave/core/matcher.py` | 反应谱匹配选波引擎 | P0 |
| `seiswave/gui/panels/peer_panel.py` | PEER NGA 浏览/过滤面板 | P1 |
| `scripts/build_fortran.sh` | Fortran 编译脚本 | P0 |
| `scripts/precompute_spectra.py` | 批量预计算反应谱脚本 | P1 |
| `data/peer_nga/_cache/` | 反应谱缓存目录 | P1 |

### 6.2 修改文件

| 文件 | 修改内容 | 优先级 |
|------|----------|--------|
| `seiswave/core/spectrum.py` | `Spectra.compute()` 增加 Fortran 后端调用分支 | P0 |
| `seiswave/core/generator.py` | `WaveGenerator.generate()` 使用 Fortran 后端的 `fitspectra`/`adjustspectra`/`initArtWave` | P0 |
| `seiswave/core/selector.py` | 重构选波逻辑：增加 `SpectrumMatcher`，支持 PEER NGA 数据源 | P0 |
| `seiswave/core/io.py` | `FileIO.read_at2()` 增加元数据提取；新增 `parse_peer_filename()` | P1 |
| `seiswave/core/filter.py` | 新增 `poly_baseline_correction()`、`target_displacement_correction()` | P2 |
| `seiswave/core/signal.py` | `EQSignal` 增加 `peer_record` 属性关联 PEER 元数据 | P1 |
| `seiswave/core/__init__.py` | 导出新增模块 | P0 |
| `seiswave/gui/panels/selector_panel.py` | 适配新选波引擎，增加 PEER NGA 数据源选择 | P1 |
| `seiswave/gui/panels/generator_panel.py` | 适配 Fortran 加速后的生成器 | P1 |
| `seiswave/gui/panels/import_panel.py` | 增加 PEER NGA 批量导入入口 | P1 |
| `seiswave/gui/workers.py` | 新增 `PeerIndexWorker`、`SpectraPrecomputeWorker`、`MatcherWorker` | P1 |
| `setup.py` / `pyproject.toml` | 添加 Fortran 编译配置 | P0 |


---

## 七、实施优先级与工作量预估

### Phase 0：Fortran 编译与集成（预估 2-3 天）

| 步骤 | 内容 | 预估 |
|------|------|------|
| 0.1 | 安装 FFTW3，编写 `build_fortran.sh` 编译脚本 | 0.5 天 |
| 0.2 | f2py 编译 `eqs.f90`，解决 FFTW3 链接问题 | 0.5 天 |
| 0.3 | 编写 `fortran_binding.py`，封装核心函数 | 0.5 天 |
| 0.4 | 修改 `spectrum.py`，增加 Fortran 后端分支 | 0.5 天 |
| 0.5 | 修改 `generator.py`，使用 Fortran 后端 | 0.5 天 |
| 0.6 | 验证：人工波生成 50 次迭代 < 15s | 0.5 天 |

**交付物**：人工波生成性能从"卡住"提升到 ~10s 完成。

### Phase 1：PEER NGA 数据集成（预估 3-4 天）

| 步骤 | 内容 | 预估 |
|------|------|------|
| 1.1 | 编写 `peer_nga.py`：文件名解析、索引构建、延迟加载 | 1 天 |
| 1.2 | 编写 `scripts/precompute_spectra.py`：批量预计算反应谱 | 0.5 天 |
| 1.3 | 编写 `matcher.py`：反应谱匹配评分、最优缩放、贪心组合 | 1.5 天 |
| 1.4 | 修改 `io.py`：增加 PEER 文件名解析 | 0.5 天 |
| 1.5 | 运行预计算：701 条 × 200 周期（Fortran 加速后 ~35s） | 0.5 天 |

**交付物**：命令行可用的自动选波引擎，输入目标谱参数，输出最优 N 条天然波。

### Phase 2：选波引擎完善与 GUI 集成（预估 3-4 天）

| 步骤 | 内容 | 预估 |
|------|------|------|
| 2.1 | 重构 `selector.py`：整合 `SpectrumMatcher`，支持天然波+人工波组合 | 1 天 |
| 2.2 | 新增 `peer_panel.py`：PEER NGA 浏览/过滤 GUI | 1 天 |
| 2.3 | 修改 `selector_panel.py`：适配新选波引擎 | 0.5 天 |
| 2.4 | 修改 `generator_panel.py`：适配 Fortran 加速 | 0.5 天 |
| 2.5 | 新增 Workers：`PeerIndexWorker`、`MatcherWorker` | 0.5 天 |
| 2.6 | 集成测试：完整流程（导入→选波→生成→导出） | 0.5 天 |

**交付物**：GUI 可用的完整选波+生成流程。

### Phase 3：信号处理增强（预估 1-2 天）

| 步骤 | 内容 | 预估 |
|------|------|------|
| 3.1 | `filter.py` 新增 `polyblc`、`targetdc` 封装 | 0.5 天 |
| 3.2 | `signal.py` 增加 PEER 元数据关联 | 0.5 天 |
| 3.3 | GUI 信号处理面板增加新功能入口 | 0.5 天 |

**交付物**：完整的信号处理工具链。

### 总计：9-13 天

---

## 八、技术风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| f2py 编译 FFTW3 链接失败 | 阻塞 Phase 0 | 备选方案 B（ctypes），或用 scipy.fft 替换 FFTW |
| eqs.f90 中 `para` 全局变量（非线性模块） | f2py 封装困难 | 仅封装线性部分（`bind(c)` 函数），非线性模块暂不集成 |
| PEER AT2 文件格式不一致 | 解析失败 | 增加容错处理，跳过无法解析的文件 |
| 701 条预计算内存占用 | 内存不足 | 分批计算，结果直接写入 npz |
| macOS arm64 Fortran 编译兼容性 | 编译失败 | 使用 Homebrew gfortran，确认 arm64 支持 |

---

## 九、关键设计决策

1. **Fortran 后端为可选依赖**：通过 `HAS_FORTRAN` 标志自动回退到纯 Python，确保无 Fortran 环境也能运行（只是慢）。

2. **反应谱缓存为 npz 格式**：比 HDF5 轻量，NumPy 原生支持，加载速度快。

3. **选波算法采用贪心策略**：先按单条匹配度排序，再逐条加入检查组合效果。比穷举组合（C(701,7) ≈ 10^15）可行得多。

4. **延迟加载波形数据**：索引只存元数据和预计算谱值，波形数据按需加载，避免 701 条全部驻留内存。

5. **分量方向自动识别**：通过文件名后缀判断（UP/DWN/V → 竖向，其余 → 水平），不依赖外部元数据文件。

6. **保留现有 `_newmark.so`**：已有的 Newmark 加速模块继续使用，新的 Fortran 后端作为补充。

