# SeisWave 重构设计文档 — 工作台架构

**日期**: 2026-06-20　**状态**: 设计定稿待审　**后续**: 经 writing-plans 产出实现计划,交 codex 开发测试

---

## 1. Context(为什么重构)

SeisWave 的初衷是**基于规范自动选波**(选天然地震波 + 生成人工波,人工波含一般/FF/NF/NFP)。但当前实现偏离了初衷:

- **死板的三步向导**(step1 规范谱 → step2 选波 → step3 生成/组合)强制线性顺序,板块间不能自由互通数据;
- **功能做得太大**:一个"生成人工波"内部捆了初始波合成 + adjust_peak + 谱迭代 + 基线;"选波/组合"各塞了多步。用户无法单独用"基线校正""谱拟合"等小功能;
- 时程只看加速度,缺速度/位移;出图/数据提取不便;中文字体未按平台适配。

调研了成熟同类软件(Seismosoft 的 SeismoSignal/Match/Select/Artif、PEER NGA、ViewWave、EZ-FRISK):**没有一个用死板向导做主壳**,全部是"共享数据列表 + 中央绘图 + 独立工具"。本设计据此把 SeisWave 重构为**工作台(Workbench)**架构。

**目标产出**:一个非线性、模块化、数据互通的工作台——共享信号库 + 一组单一职责的独立工具 + 常驻 a/v/d 与反应谱预览 + 拟合记分卡 + 处处可出图/导数据,Mac/Windows 双平台。

---

## 2. 核心架构

### 2.1 数据模型(共享层)

**`SignalRecord`**(信号库中的一条信号,贯穿全应用的核心对象)
- `acc/vel/disp`: numpy 时程(由 EQSignal.a2vd 派生,速度/位移惰性计算缓存)
- `dt, n, name, kind`(natural / artificial-一般|FF|NF|NFP / processed)
- `meta`: 来源(RSN/文件/生成参数)、缩放系数、断层/Mw/R(若天然)、近场系数/spectrum_source(若人工)
- `provenance`: 派生链(如"RSN1234 · 基线校正后"记录其父信号 + 操作)
- `spectrum`(缓存的反应谱)

**`SignalPool`**(共享数据池,单例服务)
- 增删查信号;发"signals_changed""selection_changed"信号(Qt signal);当前选中信号集
- 所有工具的输入 = 选中信号;输出 = 新 `SignalRecord` 存回池(不就地破坏原信号,保留 provenance)

**`TargetSpectrumService`**(全局目标谱,三源通用组件——Seismosoft 套件统一惯例)
1. **规范设计谱**: GB50011 / GB/T51408(隔震)— 由设防烈度·场地·分组·水准查表(复用 `CodeSpectrum`)
2. **从记录算**: 取信号库任一信号的反应谱作目标
3. **自定义**: 导入两列(T, Sa)文件 / 手输
- 发"target_changed";被选波/谱拟合/校核/出图统一引用
- **注**: GMPE(第五代区划/俞言祥)**不在此处**作通用目标谱;仅在"人工波生成·特殊波"工具内作可选**情景谱**源,UI 明确标注"情景/危险性谱,非规范设计谱"

### 2.2 工具(独立、单一职责,对"选中信号"操作)

复用现有 core 模块,但每个拆成能单独使用的工具(不再捆成大流程):

| 工具 | 职责 | 复用 core |
|---|---|---|
| 📥 导入 | 读 PEER/AT2/TXT/本地目录 → 信号库 | `io.FileIO`, `peer_db` |
| 🤖 自动选波 | **一键全自动**:目标谱+条件→候选库谱型匹配排序+缩放→最优 N 条 | `selector.WaveSelector` |
| ⚙ 人工波生成 | 一般/FF/NF/NFP;特殊波此处接 GMPE 情景谱 | `generator.*` |
| 📐 基线校正 | 选任一信号→校正→存回库 | `signal.baseline_correction`, `filter` |
| 〰 滤波 | 带通/高通 | `filter.Filter` |
| 🎚 谱拟合/调整 | 把任一信号匹配到目标谱(独立,不再捆在生成里) | `generator._adjustspectra*` 抽出 |
| 📈 反应谱 | 算任一信号 Sa/Sv/Sd(可三联对数图/多阻尼) | `spectrum.Spectra` |
| 🧩 组合校核 | 组装最终波组(如5天然+2人工)并按规范校核 | `combiner.Combiner` |

> **谱拟合独立化**是关键重构:把现 `WaveGenerator` 里的谱匹配迭代(`_adjustspectra_atik` + line-search)抽成可对**任意信号**调用的独立服务,人工波生成内部复用它,但用户也能单独"拿一条天然波拟合到目标谱"。

### 2.3 出图与导出(处处可用)

- **快捷出图**: 选中信号一键出 a/v/d 时程 / 反应谱(结果 vs 目标)/ 三联对数图。字体**按平台自动**:中文 `SimSun`(Win)/`Songti SC`(Mac),英文 `Times New Roman`(两平台都有)。导出 PNG/PDF/SVG
- **数据导出**: acc/vel/disp/反应谱 → CSV/TXT/AT2,一键提取;批量结果表(每条信号:来源/缩放/RMSE/PGA/PGV/PGD/持时)→ CSV
- **拟合记分卡**: 中央预览旁常驻数值(均值误差%、PGA/PGV/PGD、Arias、显著持时)——成熟软件可信度的关键

---

## 3. UI 布局(工作台 v2,已用户定稿)

```
┌─ 顶部工具栏: [导入][自动选波][人工波生成][基线][滤波][谱拟合][反应谱][组合校核] ‖ 🎯目标谱:[规范/从记录/自定义] ─┐
├──────────────┬─────────────────────────────────────────┬──────────────────────────┤
│ 📚 信号库     │ 中央(焦点,常驻多图):                    │ ⚙ 上下文:当前工具参数     │
│ (共享脊柱)    │   加速度 a(t)                            │   (随工具变;特殊波→GMPE)  │
│ · 天然 …      │   速度   v(t)                            │   [▶ 运行]                 │
│ · 人工 …      │   位移   d(t)                            │ ──────────                │
│ · 处理后 …    │   反应谱:结果 vs 目标(三联/多阻尼)       │ 🖼 快捷出图  💾 导出数据   │
│ [导入][选波]  │   ┌ 📊 拟合记分卡(均值误差/PGA/PGV/…)┐   │   (字体按平台自动)        │
│ [生成]        │   └──────────────────────────────────┘   │                            │
├──────────────┴─────────────────────────────────────────┴──────────────────────────┤
│ 底部: 进度/日志 │ 项目: 新建/打开/保存(可暂停续跑批量,Seismosoft 模型)                │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **左**: 信号库列表(载入一次,工具读写同一池)
- **中**: 常驻 a/v/d 三联时程 + 反应谱 + 拟合记分卡(焦点最大)
- **右**: 当前工具的参数 + 运行 + 出图/导出
- 工具非线性,随时切换、对选中信号操作;**项目存/开**

---

## 4. 跨平台(Mac + Windows)

- **框架**: PySide6/Qt 本身跨平台,沿用
- **字体**: 启动时按 `sys.platform` 选中文字体(`SimSun`/`Songti SC`),英文 `Times New Roman`;封装成 `gui/fonts.py`,matplotlib `rcParams` 与 Qt 控件统一调用,避免现 `plot_widget` 写死 `Songti SC`(Win 无此字体)
- **打包**: PyInstaller 各出一份(`build.spec` 已有,补 Windows 配置);数据目录/换行用 `os.path`/`pathlib`
- **解释器**: 文档说明依赖(numpy/scipy/PySide6/numba),提供 `requirements.txt` 与各平台启动脚本

---

## 5. 复用 vs 新建

- **大量复用 core**: `EQSignal`(已有 a2vd/baseline_correction)、`Spectra`、`WaveGenerator`/`Far/NearField*`、`WaveSelector`、`Combiner`、`Filter`、`CodeSpectrum`、`gmpe.ChinaGMPEAdapter`、`io`、`peer_db`、`residual`、`pulse` —— **核心算法基本不动**(本会话刚修好的谱匹配/中国GMPE/NFP 全保留)
- **新建(主要是 GUI + 薄服务层)**: `SignalPool`、`TargetSpectrumService`、`gui/workbench/`(主壳 + 信号库面板 + 中央多图面板 + 右侧工具面板 + 各工具子面板)、`gui/fonts.py`、谱拟合独立服务(从 generator 抽出薄封装)
- **退役**: 现 `gui/` 的向导式 `main_window` + step 面板(`generator_panel`/`selector_panel`/`combine_panel`/`spectrum_sidebar` 等)→ 重组为工作台面板。旧 `gui.bak`/`gui_backup_*` 删除

---

## 6. 测试策略(交 codex 执行)

- **core 不回归**: 现有 152+ 项 core/gmpe/ff_nf 测试保持全绿(算法未动)
- **新服务单测**: `SignalPool`(增删/选中/provenance)、`TargetSpectrumService`(三源切换/事件)、谱拟合独立服务、字体平台选择
- **GUI 离屏测试**(`QT_QPA_PLATFORM=offscreen`): 工作台构建、工具切换、选中→中央多图刷新、出图/导出落盘、记分卡数值
- **跨平台冒烟**: Mac/Windows 各启动 + 字体回退验证
- **端到端**: 导入→自动选波→生成人工波→谱拟合→组合校核→出图导出 全链路

---

## 7. 建议实现分期(供 writing-plans 细化)

1. **数据与服务层**: SignalRecord/SignalPool/TargetSpectrumService + fonts.py(纯逻辑,可先单测)
2. **工作台主壳**: 三栏布局 + 信号库面板 + 中央多图面板(a/v/d+谱+记分卡)+ 右侧工具容器 + 项目存开
3. **逐个移植工具**: 导入→反应谱→出图/导出(先打通"看与导")→自动选波→人工波生成→基线/滤波/谱拟合→组合校核
4. **跨平台与打包**: 字体回退、PyInstaller 双平台、启动脚本
5. **退役旧向导 + 全测试绿**

---

## 8. 非目标(YAGNI)

- 不做云端/账号/协作;不做 PSHA 危险性分析(EZ-FRISK 级);不引入 ribbon;不做插件系统。GMPE 只保留已实现的第五代区划(俞言祥),不扩 NGA-West2/SDEE。
