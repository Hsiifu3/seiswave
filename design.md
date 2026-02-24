# SeisWave v3.0 技术设计

## 1. 架构概览

```
seiswave/
├── core/                    # 核心计算库（纯 Python，无 GUI 依赖）
│   ├── signal.py            # EQSignal 类（已有，小改）
│   ├── spectrum.py          # 反应谱计算（已有，接入 Fortran）
│   ├── code_spec.py         # 规范谱：GB50011 + GB/T51408 + 自定义（改造）
│   ├── selector.py          # 选波引擎（重写）
│   ├── generator.py         # 人工波生成（改造，接入 Fortran）
│   ├── combiner.py          # 🆕 组合输出引擎（5+2 / 2+1）
│   ├── peer_db.py           # 🆕 PEER NGA 数据库管理
│   ├── fortran_bridge.py    # 🆕 Fortran 加速封装层
│   ├── filter.py            # 滤波与基线校正（已有）
│   ├── fft.py               # FFT/PSD（已有）
│   └── io.py                # 文件 I/O（已有，增强元数据解析）
├── gui/                     # PySide6 GUI
│   ├── main_window.py       # 主窗口（向导式流程）
│   ├── panels/
│   │   ├── spec_panel.py    # Step 1: 规范谱设置
│   │   ├── select_panel.py  # Step 2: 天然波选取
│   │   ├── gen_panel.py     # Step 3: 人工波生成
│   │   ├── combine_panel.py # 🆕 Step 4: 组合输出
│   │   └── signal_panel.py  # 工具: 信号处理
│   ├── widgets/             # 自定义控件
│   └── workers.py           # QThread 后台计算
├── data/
│   └── peer_nga/            # 内置 PEER NGA 数据（701 AT2）
└── scripts/
    └── build_fortran.sh     # Fortran 编译脚本
```

## 2. 核心组件设计

### 2.1 规范谱模块 (code_spec.py) — 改造

现有 `CodeSpectrum` 支持 GB50011/EC8/ASCE7，v3 改造：

- 保留 GB50011 抗震谱（四段式），完善隔规谱（GB/T 51408 三段式）
- EC8/ASCE7 保留代码但不在 GUI 暴露
- **新增**：自定义谱支持

```python
class CodeSpectrum:
    # 已有：gb50011(), get_params(), from_params()
    
    @staticmethod
    def gb51408(periods, Tg, alpha_max, zeta=0.05,
                T_iso_before=None, T_iso_after=None):
        """GB/T 51408 隔震设计反应谱（三段式）
        T_iso_before: 隔震前结构周期
        T_iso_after:  隔震后结构周期
        """
        ...
    
    @staticmethod
    def custom(periods, user_periods, user_sa, interpolation='linear'):
        """自定义规范谱
        user_periods: 用户输入的周期点数组
        user_sa: 用户输入的谱加速度值数组
        interpolation: 'linear' | 'log-log'
        """
        ...
    
    @staticmethod
    def from_csv(filepath):
        """从 CSV/TXT 导入自定义谱（两列：周期, Sa）"""
        ...
```

### 2.2 PEER 数据库模块 (peer_db.py) — 新增

管理内置的 701 条 PEER NGA 记录，支持索引、延迟加载、反应谱缓存。

```python
@dataclass
class PeerRecord:
    rsn: int                    # RSN 编号（从文件名解析）
    event: str                  # 事件名（从 AT2 第 2 行）
    station: str                # 台站名（从 AT2 第 2 行）
    date: str                   # 日期（从 AT2 第 2 行）
    component: str              # 分量方向（从 AT2 第 2 行 / 文件名）
    direction: str              # 'H' 水平 / 'V' 竖向（自动判断）
    filepath: str               # AT2 文件路径
    dt: float                   # 时间步长
    npts: int                   # 数据点数
    pga: float                  # PGA (g)
    duration: float             # 总持时 (s)
    eff_duration: float         # 有效持时 (s)，5%-95% Arias
    acc: np.ndarray | None      # 加速度（延迟加载）
    sa: np.ndarray | None       # 反应谱（延迟计算/缓存加载）

class PeerDatabase:
    def __init__(self, data_dir: str):
        self.records: list[PeerRecord] = []
        self._cache_path = os.path.join(data_dir, '_cache')
    
    def build_index(self, progress_cb=None) -> int:
        """扫描 AT2 文件，解析头部元数据，建立索引（不加载波形）"""
        # 解析文件名 → RSN
        # 解析第 2 行 → event, date, station, component
        # 解析第 4 行 → NPTS, DT
        # 判断方向：文件名含 UP/DWN/-UP → 'V'，否则 → 'H'
        ...
    
    def get_horizontal(self) -> list[PeerRecord]:
        """返回所有水平分量记录（约 468 条）"""
        return [r for r in self.records if r.direction == 'H']
    
    def load_waveform(self, record: PeerRecord):
        """延迟加载单条波形"""
        ...
    
    def precompute_spectra(self, periods, zeta=0.05, progress_cb=None):
        """批量预计算反应谱，结果存入 _cache/spectra.npz"""
        ...
    
    def load_spectra_cache(self, zeta=0.05) -> bool:
        """加载反应谱缓存"""
        ...
    
    def filter(self, rsn=None, event=None, station=None,
               pga_range=None, duration_range=None) -> list[PeerRecord]:
        """按条件过滤"""
        ...
```

**缓存设计**：
```
data/peer_nga/_cache/
├── index.json          # 元数据索引（RSN/event/station/...）
└── spectra_z005.npz    # 反应谱缓存 {periods, rsn, sa, pga, direction}
```

### 2.3 选波引擎 (selector.py) — 重写

按中国规范三步筛选 + 反应谱匹配排序。

```python
@dataclass
class SelectionConfig:
    target_sa: np.ndarray           # 目标反应谱
    periods: np.ndarray             # 周期数组
    T_main: list[float]             # 结构主周期 [T1, T2, T3]
    zeta: float = 0.05
    duration_factor: float = 5.0    # 有效持时 ≥ factor × T1
    spectral_tol: float = 0.20      # 主周期点偏差容限
    n_select: int = 5               # 选取天然波数量
    scale_range: tuple = (0.5, 4.0) # PGA 缩放系数范围
    # 隔震设计
    isolation: bool = False
    T_iso_before: float = None      # 隔震前周期
    T_iso_after: float = None       # 隔震后周期
    target_sa_iso: np.ndarray = None  # 隔震谱（如果不同于抗震谱）

@dataclass  
class SelectionResult:
    record: PeerRecord
    scale_factor: float             # PGA 缩放系数
    match_error: float              # 反应谱匹配误差（RMSE）
    deviations: dict                # 各主周期点偏差
    eff_duration: float             # 有效持时
    passed_duration: bool
    passed_spectrum: bool

class WaveSelector:
    def __init__(self, config: SelectionConfig):
        self.config = config
    
    def select(self, database: PeerDatabase, 
               progress_cb=None) -> list[SelectionResult]:
        """自动选波主流程
        1. 从数据库获取水平分量
        2. 有效持时筛选（≥ 5T1）
        3. 反应谱匹配：对每条波求最优缩放系数，计算偏差
        4. 主周期点偏差筛选（≤ tolerance）
        5. 隔震设计时：同时检查隔震前后周期匹配
        6. 按匹配误差排序，贪心选出最优 N 条组合
        """
        ...
    
    def _optimal_scale(self, record_sa, target_sa, period_mask):
        """最小二乘法求最优缩放系数"""
        ...
    
    def _greedy_combination(self, candidates, n):
        """贪心组合：确保 N 条波的平均谱满足规范要求
        - 逐条加入误差最小的波
        - 每加一条检查组合平均谱偏差
        - 确保平均谱 ≥ 0.80 × 目标谱
        """
        ...
```

### 2.4 人工波生成 (generator.py) — 改造

核心改造：接入 Fortran 加速后端。

```python
class WaveGenerator:
    @staticmethod
    def generate(target_sa, periods, n=4096, dt=0.02, zeta=0.05,
                 pga=1.0, tol=0.05, max_iter=50, method='time',
                 n_trials=3, progress_cb=None) -> EQSignal:
        """生成人工波
        method: 'time'（时域法 adjustspectra）| 'freq'（频域法 fitspectra）
        n_trials: 多随机种子取最优
        
        优先调用 Fortran 后端，失败回退纯 Python
        """
        from .fortran_bridge import HAS_FORTRAN
        if HAS_FORTRAN:
            return WaveGenerator._generate_fortran(...)
        else:
            return WaveGenerator._generate_python(...)
    
    @staticmethod
    def _generate_fortran(target_sa, periods, n, dt, zeta, pga,
                          tol, max_iter, method, n_trials, progress_cb):
        """Fortran 加速路径：直接调用 fitspectrum"""
        ...
    
    @staticmethod
    def _generate_python(target_sa, periods, n, dt, zeta, pga,
                         tol, max_iter, method, n_trials, progress_cb):
        """纯 Python 兜底路径（慢）"""
        ...
```

### 2.5 组合输出引擎 (combiner.py) — 新增

按 GB 50011 §5.1.2 要求组合天然波 + 人工波。

```python
@dataclass
class CombineConfig:
    mode: str = '7'                 # '7' 或 '3'
    n_natural: int = 5              # 天然波数量（7模式≥5，3模式≥2）
    n_artificial: int = 2           # 人工波数量（7模式≥2，3模式≥1）
    target_sa: np.ndarray = None    # 目标反应谱
    periods: np.ndarray = None
    # 底部剪力校核
    shear_check: bool = True
    shear_single_range: tuple = (0.65, 1.35)  # 单条波
    shear_mean_min: float = 0.80               # 平均值

@dataclass
class CombineResult:
    natural_waves: list[SelectionResult]    # 选中的天然波
    artificial_waves: list[EQSignal]        # 生成的人工波
    all_waves: list                         # 全部波（天然+人工）
    mean_sa: np.ndarray                     # 平均反应谱
    envelope_sa: np.ndarray                 # 包络反应谱
    shear_ratios: list[float]               # 各波底部剪力比
    mean_shear_ratio: float                 # 平均底部剪力比
    passed: bool                            # 是否满足规范要求

class WaveCombiner:
    def __init__(self, config: CombineConfig):
        self.config = config
    
    def combine(self, natural: list[SelectionResult],
                artificial: list[EQSignal]) -> CombineResult:
        """组合天然波+人工波，校验规范要求
        - 7条模式：取平均值
        - 3条模式：取包络值
        - 底部剪力校核
        """
        ...
    
    def check_shear(self, waves) -> tuple[list[float], float, bool]:
        """底部剪力校核
        单条：0.65~1.35 × CQC
        平均：≥ 0.80 × CQC
        """
        ...
    
    def export(self, result: CombineResult, output_dir: str,
               fmt='at2', report=True):
        """导出所有波形 + 选波报告
        - AT2 + TXT 格式波形文件
        - 选波报告（参数、筛选过程、反应谱对比图）
        """
        ...
    
    def generate_report(self, result: CombineResult, output_dir: str):
        """生成选波报告（HTML）
        包含：规范参数、筛选过程、每条波信息、反应谱对比图
        """
        ...
```

### 2.6 Fortran 加速层 (fortran_bridge.py) — 新增

封装 EQSignal Fortran 库，自动检测可用性。

```python
# 编译方式：f2py（推荐）或 ctypes
# 编译命令见 scripts/build_fortran.sh

try:
    from . import _eqsignal as _f
    HAS_FORTRAN = True
except ImportError:
    HAS_FORTRAN = False

# 封装函数：
# - spectrum_mixed(acc, dt, zeta, periods) → sa
# - fit_spectra(acc, dt, zeta, periods, target_sa, tol, max_iter) → acc
# - adjust_spectra(acc, dt, zeta, periods, target_sa, tol, max_iter) → acc
# - init_art_wave(n, dt, zeta, periods, target_sa) → acc
# 每个函数内部：HAS_FORTRAN ? 调用 _f : 回退纯 Python
```

**编译依赖**：gfortran + FFTW3 + LAPACK（macOS Accelerate）
**备选方案**：如果 f2py 链接 FFTW3 失败，改用 ctypes 调用 libeqs.dylib

## 3. GUI 流程设计

### 向导式四步流程

```
┌─────────────────────────────────────────────────────────┐
│  工具栏: [① 规范谱] [② 选天然波] [③ 生成人工波] [④ 组合输出] │
├──────────────┬──────────────────────────────────────────┤
│  参数面板     │         绘图区域                          │
│  (随步骤切换) │     (反应谱对比 / 时程曲线)               │
│              │                                          │
│  Step 1:     │  规范谱预览                               │
│  烈度/场地/  │                                          │
│  阻尼比/隔震 │                                          │
│  自定义谱    │                                          │
│              │                                          │
│  Step 2:     │  天然波反应谱 vs 目标谱                   │
│  T1/T2/T3   │  选波结果列表                             │
│  筛选条件    │                                          │
│              │                                          │
│  Step 3:     │  人工波迭代过程 / 拟合对比                │
│  生成参数    │                                          │
│              │                                          │
│  Step 4:     │  组合谱对比 / 导出选项                    │
│  组合模式    │                                          │
├──────────────┴──────────────────────────────────────────┤
│  底部: 波形列表表格（RSN/事件/台站/PGA/偏差/状态）        │
└─────────────────────────────────────────────────────────┘
```

## 4. 数据流

```
用户输入规范参数
    │
    ▼
CodeSpectrum.gb50011() / .gb51408() / .custom()
    │
    ▼ target_sa
PeerDatabase.build_index() → 701 条记录索引
PeerDatabase.precompute_spectra() → 反应谱缓存
    │
    ▼
WaveSelector.select(database)
    ├── 有效持时筛选 → 排除不满足的
    ├── 反应谱匹配 + 最优缩放 → 排序
    ├── 隔震双周期检查（如需）
    └── 贪心组合 → 最优 5 条天然波
    │
    ▼ natural_waves
WaveGenerator.generate() × 2
    │ (Fortran 加速)
    ▼ artificial_waves
WaveCombiner.combine(natural, artificial)
    ├── 平均谱 / 包络谱计算
    ├── 底部剪力校核
    └── 导出波形 + 报告
    │
    ▼
输出: 7 条波形文件 + 选波报告
```

## 5. 性能预估

| 操作 | 纯 Python | Fortran 加速 |
|------|-----------|-------------|
| 单条反应谱（200 周期） | ~8s | ~0.05s |
| 701 条批量反应谱 | ~90min | ~35s |
| 人工波生成（50 迭代） | >10min | ~10s |
| 完整选波流程 | 不可用 | ~2min |

## 6. 技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Fortran 集成方式 | f2py（首选）/ ctypes（备选） | f2py 自动处理数组转换，更 Pythonic |
| 反应谱缓存格式 | NumPy npz | 轻量、原生支持、加载快 |
| 选波算法 | 贪心组合 | C(468,5) ≈ 2×10⁹ 穷举不可行 |
| 波形延迟加载 | 索引只存元数据 | 701 条全加载占内存过大 |
| 分量方向判断 | 文件名后缀 | UP/DWN/-UP → 竖向，其余 → 水平 |
| 规范谱范围 | GB50011 + GB/T51408 + 自定义 | 用户明确要求先做中国规范 |
