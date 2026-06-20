# SeisWave 工作台重构 — 实现计划(交 codex 执行)

**依据**: `docs/superpowers/specs/2026-06-20-seiswave-redesign-design.md`
**日期**: 2026-06-21　**分支建议**: 从当前 `feature/generator-rewrite` 新开 `feature/workbench`
**执行者**: codex(开发 + 测试)

---

## 0. 给 codex 的前置约定

- **解释器**: 本机 `.venv` 是空的。用 **`/usr/bin/python3`**(已装 numpy 2.0.2 / scipy / PySide6 6.10.2)。运行需 `export PYTHONPATH=/Users/yachiyo/Developer/seiswave:$PYTHONPATH`。
- **GUI 测试**: 设 `QT_QPA_PLATFORM=offscreen`。
- **不动 core 算法**: `seiswave/core/*` 的数值逻辑(谱匹配、ChinaGMPE、NFP、selector、combiner)保持不变;现有 152+ core/gmpe/ff_nf 测试必须持续全绿。本计划只新增 GUI + 薄服务层,并把若干算法**抽出薄封装**供独立调用。
- **每个 Phase 自带测试,必须绿后再进下一 Phase**。每 Phase 一个提交。
- **风格**: 跟随现有代码(中文注释、PySide6、snake_case)。GUI 新代码放 `seiswave/gui/workbench/`。
- **退役**: 旧向导面板在最后一期统一退役;此前保留以便对照。

---

## Phase 1 — 数据与服务层(纯逻辑,先单测)

**目标**: 建立贯穿全应用的共享数据模型与服务,无 GUI 依赖,可独立单测。

**新建文件**
- `seiswave/core/signal_pool.py`
- `seiswave/core/target_spectrum.py`
- `seiswave/gui/fonts.py`

**关键接口**

```python
# signal_pool.py
@dataclass
class SignalRecord:
    acc: np.ndarray; dt: float
    name: str; kind: str            # 'natural'|'artificial:general|FF|NF|NFP'|'processed'
    meta: dict = field(default_factory=dict)   # rsn/source/scale/Mw/R/fault/near_field_factor/spectrum_source...
    parent_id: str | None = None    # provenance
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    def vel(self) -> np.ndarray: ...   # 惰性: 由 EQSignal.a2vd 缓存 (g·s)
    def disp(self) -> np.ndarray: ...
    def spectrum(self, periods, zeta=0.05): ...  # 缓存 Spectra.compute

class SignalPool(QObject):           # Qt 单例服务
    signals_changed = Signal()
    selection_changed = Signal()
    def add(self, rec: SignalRecord) -> str: ...
    def remove(self, id: str): ...
    def get(self, id) -> SignalRecord: ...
    def all(self) -> list[SignalRecord]: ...
    def set_selection(self, ids: list[str]): ...
    def selection(self) -> list[SignalRecord]: ...
    def derive(self, parent: SignalRecord, acc, name_suffix, kind='processed') -> SignalRecord: ...  # 存回池,记 provenance
```

```python
# target_spectrum.py
class TargetSpectrumService(QObject):
    target_changed = Signal()
    # 三源
    def set_code(self, code='GB50011', **params): ...   # 复用 CodeSpectrum
    def set_from_record(self, rec: SignalRecord): ...
    def set_custom(self, periods, sa): ...              # 含从两列文件导入
    def periods(self) -> np.ndarray: ...
    def sa(self) -> np.ndarray: ...
    def describe(self) -> str: ...
    # 注: GMPE 不在此处; 属人工波生成的特殊波情景谱
```

```python
# fonts.py
def cjk_font() -> str:   # 'SimSun'(win) / 'Songti SC'(darwin) / 回退
def setup_matplotlib_fonts(): ...   # rcParams: [Times New Roman, <cjk_font>]
def qt_font() -> QFont: ...
```

**步骤**
1. 实现 SignalRecord(惰性 vel/disp 复用 `EQSignal(acc,dt).a2vd()`;spectrum 复用 `Spectra.compute`)。
2. 实现 SignalPool(增删/选中/derive/信号)。
3. 实现 TargetSpectrumService(三源 + 自定义文件解析)。
4. 实现 fonts.py(按 `sys.platform` 选字体 + 回退;matplotlib rcParams)。

**测试**(新增 `tests/test_signal_pool.py`, `tests/test_target_spectrum.py`, `tests/test_fonts.py`)
- SignalРecordVel/disp 与 `EQSignal.a2vd` 一致;spectrum 缓存命中。
- Pool 增删/选中触发信号;derive 记录 parent_id 且不改原信号。
- TargetSpectrum 三源切换发 target_changed;自定义文件往返。
- fonts: darwin 返回 'Songti SC'、其它平台逻辑分支可单测(monkeypatch sys.platform)。

**验收**: 上述单测全绿;core 既有测试不受影响。

---

## Phase 2 — 工作台主壳(三栏 + 中央多图 + 项目)

**目标**: 立起工作台外壳,信号库↔中央预览联动跑通(暂不接全部工具)。

**新建** `seiswave/gui/workbench/`
- `app_window.py`(QMainWindow:顶部工具栏 + 三栏 QSplitter + 底部状态/进度 + 菜单:项目 新建/打开/保存)
- `signal_pool_panel.py`(左:信号库列表,显示 kind/来源,多选 → pool.set_selection;[导入][自动选波][生成] 入口按钮)
- `preview_panel.py`(中:a/v/d 三联时程 + 反应谱(结果 vs 目标,三联对数图/多阻尼选项)+ 拟合记分卡子组件)
- `tool_dock.py`(右:工具参数容器,按当前工具切换内容)
- `scorecard.py`(记分卡:均值误差%/PGA/PGV/PGD/Arias/显著持时,从选中信号 + 目标谱算)
- `project_io.py`(项目存/开:序列化 pool + target + 当前状态为 .json/.npz)

**步骤**
1. app_window 组装三栏 + 工具栏占位 + 接 SignalPool/TargetSpectrumService 单例。
2. signal_pool_panel ↔ pool 双向(选中→中央刷新)。
3. preview_panel:选中变化 → 画 a/v/d + 谱 vs 目标 + 记分卡。复用 `widgets/plot_widget`(改用 fonts.setup)。
4. project_io:存/开往返。

**测试**(`tests/test_workbench_shell.py`, offscreen)
- 主窗口构建无异常;选中信号 → preview 三联图与谱被绘制(检查 axes/line 数);记分卡数值正确。
- 项目存→开往返,pool/target 还原。

**验收**: 离屏测试绿;能手动启动看到三栏 + 选中预览。

---

## Phase 3 — 逐个移植工具(先"看与导",再"算与生成")

**目标**: 把 8 个独立工具接进右侧工具容器,各对"选中信号/目标谱"操作,结果存回池。

**顺序与要点**(每个工具 = `gui/workbench/tools/<name>_tool.py`,薄封装现有 core)
1. **反应谱工具**: 选中信号 → Sa/Sv/Sd,推到 preview。(复用 Spectra)
2. **快捷出图**: a/v/d/谱 → PNG/PDF/SVG(fonts 已配)。(从 preview 复用绘制)
3. **数据导出**: acc/vel/disp/谱 → CSV/TXT/AT2;批量结果表 → CSV。(复用 io)
4. **导入**: PEER 目录/AT2/TXT → pool。(复用 io.FileIO/peer_db)
5. **自动选波(一键全自动)**: 目标谱 + 条件(Mw/R/Vs30/数量/缩放区间/容差)→ `WaveSelector` 谱型匹配排序+缩放 → 最优 N 条入 pool;来源 = PEER 库 / 本地导入候选 / 其它格式。结果给批量记分表。
6. **人工波生成**: 一般/FF/NF/NFP;目标谱来源用 TargetSpectrumService;**特殊波**额外露出"情景谱(第五代区划 GMPE)"开关 + 分区/椭圆轴(复用本会话已实现逻辑,标注"情景/危险性谱")。生成的波入 pool,带 near_field_factor/spectrum_source/pulse 元数据。NFP 沿用已修的快速路径 + 引导提示。
7. **谱拟合/调整(独立)**: 把 `generator._adjustspectra_atik`(带 line-search)抽成 `core/spectral_match.py::match_to_target(acc, dt, periods, target_sa, ...)`;人工波生成内部改调它;新"谱拟合工具"可对**任一选中信号**拟合到目标谱 → 存回 pool。
8. **基线校正 / 滤波**: 选中信号 → `EQSignal.baseline_correction` / `Filter` → derive 存回 pool。

**测试**(`tests/test_workbench_tools.py`, offscreen + 逻辑)
- 每工具: 给定选中信号/目标谱 → 产出正确(谱匹配 RMSE 阈值;导出文件落盘且可回读;选波返回 N 条且谱型匹配;生成 4 型 PGA/谱合理;基线/滤波改变信号且 provenance 记录)。
- `core/spectral_match.py` 抽出后:人工波生成结果与抽出前一致(回归);独立拟合任一天然波到目标谱 RMSE<阈值。

**验收**: 端到端 导入→选波→生成→谱拟合→基线→出图→导出 跑通;core 既有测试仍全绿。

---

## Phase 4 — 跨平台与打包

**目标**: Mac/Windows 双平台可运行可打包。

**步骤**
1. fonts 回退在缺字体平台验证(monkeypatch + 真机)。
2. `build.spec` 补 Windows 配置(图标/数据/隐藏导入);各出一份 PyInstaller 产物。
3. `requirements.txt` 校准;Mac/Windows 启动脚本(`run.sh`/`run.bat`)。
4. 路径/换行统一 `pathlib`。

**测试**: 两平台启动冒烟 + 字体回退用例;打包产物能启动到主窗口。

**验收**: Windows 与 macOS 均能启动并出图(中文宋体 + 英文 Times)。

---

## Phase 5 — 退役旧向导 + 全量回归

**步骤**
1. 移除旧向导:`gui/main_window.py`(向导版)+ step 面板(`generator_panel`/`selector_panel`/`combine_panel`/`spectrum_sidebar`/`param_form` 等),逻辑已并入工作台工具。删除 `gui.bak`/`gui_backup_*`。
2. 入口 `__main__.py` 指向 `gui/workbench/app_window`。
3. 清理无用 import/测试;更新 README。

**测试**: 全量 `pytest tests/`(core 全绿 + 新 GUI 测试全绿);端到端脚本;两平台启动。

**验收**: 旧向导彻底移除,工作台为唯一入口,全测试绿。

---

## 风险与缓解

- **谱拟合抽出回归**: 抽 `spectral_match` 后人工波结果须与抽出前逐项一致 → 加黄金值回归测试。
- **selector 一键全自动质量**: 复用现有 WaveSelector,先保证不回归;自动化封装只做编排,不改算法。
- **GUI 体量**: 工具按上面顺序逐个落,每个独立可测,避免大爆炸式重写。
- **字体跨平台**: fonts.py 单点封装 + 回退链,杜绝写死。

## 交接清单(codex 开始前确认)
- [ ] 新分支 `feature/workbench`
- [ ] `/usr/bin/python3` + PYTHONPATH 可跑现有 `pytest tests/test_china_gmpe.py` 等
- [ ] 阅读 spec 与本计划;按 Phase 顺序、逐 Phase 提交、逐 Phase 测试绿
