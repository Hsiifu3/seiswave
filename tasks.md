# SeisWave v3.0 任务清单

## 执行原则
- **Coding Agent 工具**：Claude Code (Opus 4.6) / Codex CLI (GPT-5.2) / Gemini CLI，工匠根据任务特点选用最合适的工具
- **测试优先**：每个功能模块必须配备测试，覆盖主要路径和边界条件，工匠运行测试通过才算完成
- **减少迭代**：宁可多花时间写测试和思考，也不要快速提交有 bug 的代码
- 有依赖关系的 Task 必须按顺序执行

---

## Group 1: Fortran 编译集成（P0，阻塞后续所有计算密集任务）

### Task 1.1: Fortran 编译环境搭建
- **描述**：安装 gfortran + FFTW3，编写 `scripts/build_fortran.sh`，成功编译 `_eqsignal` 模块
- **文件**：`scripts/build_fortran.sh`
- **验收**：运行脚本后在 `seiswave/core/` 下生成 `_eqsignal.*.so`（或 `.dylib`）
- **AC**：AC-3.2
- **预估**：1h

### Task 1.2: Fortran 封装层
- **描述**：新建 `core/fortran_bridge.py`，封装 spectrum_mixed / fit_spectra / adjust_spectra / init_art_wave，自动检测 Fortran 可用性
- **文件**：`seiswave/core/fortran_bridge.py`
- **验收**：`HAS_FORTRAN=True` 时调用 Fortran，`False` 时回退纯 Python，两条路径结果一致（误差 < 1%）
- **依赖**：Task 1.1
- **AC**：AC-3.2
- **预估**：1.5h

### Task 1.3: spectrum.py 接入 Fortran
- **描述**：修改 `Spectra.compute()`，优先调用 `fortran_bridge.spectrum_mixed()`
- **文件**：`seiswave/core/spectrum.py`
- **验收**：反应谱计算速度提升 50x+，结果与纯 Python 一致
- **依赖**：Task 1.2
- **AC**：AC-5.4
- **预估**：0.5h

### Task 1.4: generator.py 接入 Fortran
- **描述**：修改 `WaveGenerator.generate()`，Fortran 路径直接调用 `fitspectrum`/`adjustspectra`
- **文件**：`seiswave/core/generator.py`
- **验收**：50 次迭代 ≤ 15s（Fortran），纯 Python 兜底仍可用
- **依赖**：Task 1.2
- **AC**：AC-3.1, AC-3.2, AC-3.6
- **预估**：1.5h

### Task 1.5: Fortran 集成验证
- **描述**：编写测试脚本，验证 Fortran 加速后的反应谱计算和人工波生成
- **文件**：`tests/test_fortran.py`
- **验收**：所有测试通过，性能指标达标
- **依赖**：Task 1.3, 1.4
- **预估**：1h

---

## Group 2: PEER 数据库 + 天然波选取（P0）

### Task 2.1: PEER 数据库模块
- **描述**：新建 `core/peer_db.py`，实现 AT2 文件名/头部解析、索引构建、延迟加载、方向自动判断
- **文件**：`seiswave/core/peer_db.py`
- **验收**：
  - 扫描 `data/peer_nga/` 识别出 236 条记录、701 个分量
  - 正确解析 RSN、事件名、台站、日期、分量方向、NPTS、DT
  - `get_horizontal()` 返回约 468 条水平分量
  - 索引可序列化到 `_cache/index.json`
- **AC**：AC-2.1, AC-2.2, AC-2.3
- **预估**：2h

### Task 2.2: 反应谱批量预计算 + 缓存
- **描述**：`PeerDatabase.precompute_spectra()` 批量计算 701 条记录的反应谱，存入 npz 缓存
- **文件**：`seiswave/core/peer_db.py`, `scripts/precompute_spectra.py`
- **验收**：
  - Fortran 加速下 701 条 ≤ 60s
  - 缓存文件 `_cache/spectra_z005.npz` 可正确加载
  - 二次启动直接读缓存，≤ 2s
- **依赖**：Task 2.1, Task 1.3（Fortran 加速反应谱）
- **AC**：NFR-1
- **预估**：1.5h

### Task 2.3: 选波引擎重写
- **描述**：重写 `core/selector.py`，实现三步筛选 + 反应谱匹配排序 + 贪心组合
- **文件**：`seiswave/core/selector.py`
- **验收**：
  - 有效持时筛选正确（5%-95% Arias）
  - 主周期点偏差筛选正确（≤ 20%）
  - 最优缩放系数计算正确（最小二乘）
  - 贪心组合输出 N 条最优天然波
  - 平均谱 ≥ 0.80 × 目标谱
- **依赖**：Task 2.1, Task 2.2
- **AC**：AC-2.4, AC-2.5, AC-2.6, AC-2.7
- **预估**：3h

### Task 2.4: 隔震双周期匹配
- **描述**：选波引擎支持隔震设计：同时检查隔震前周期和隔震后周期的反应谱匹配
- **文件**：`seiswave/core/selector.py`
- **验收**：隔震模式下，选出的波同时满足两个周期范围的匹配要求
- **依赖**：Task 2.3
- **AC**：AC-2.5
- **预估**：1h

### Task 2.5: 选波引擎测试
- **描述**：用实际 PEER 数据测试选波流程，验证结果合理性
- **文件**：`tests/test_selector.py`
- **验收**：给定典型参数（7 度、II 类场地、T1=1.0s），能选出 5 条合理的天然波
- **依赖**：Task 2.3
- **预估**：1h

---

## Group 3: 规范谱增强 + 组合输出（P0）

### Task 3.1: 规范谱模块改造
- **描述**：改造 `code_spec.py`：完善 GB/T 51408 隔震谱、新增自定义谱支持（手动输入 + CSV 导入）
- **文件**：`seiswave/core/code_spec.py`
- **验收**：
  - GB50011 四段式谱正确（已有，回归测试）
  - GB/T 51408 三段式谱正确
  - 隔震前后周期参数可传入
  - 自定义谱：接受周期-谱值数组，支持插值
  - CSV 导入：两列格式（周期, Sa）
- **AC**：AC-1.1, AC-1.2, AC-1.3, AC-1.4, AC-1.5
- **预估**：2h

### Task 3.2: 组合输出引擎
- **描述**：新建 `core/combiner.py`，实现天然波+人工波组合、规范校验、导出
- **文件**：`seiswave/core/combiner.py`
- **验收**：
  - 7 条模式：≥5 天然 + ≥2 人工，计算平均谱
  - 3 条模式：≥2 天然 + ≥1 人工，计算包络谱
  - 底部剪力校核：单条 0.65~1.35，平均 ≥ 0.80
  - 导出 AT2 + TXT 格式波形文件
- **依赖**：Task 2.3（选波引擎）, Task 1.4（人工波生成）
- **AC**：AC-4.1, AC-4.2, AC-4.3, AC-4.4, AC-4.5
- **预估**：2.5h

### Task 3.3: 选波报告生成
- **描述**：`WaveCombiner.generate_report()` 生成 HTML 选波报告
- **文件**：`seiswave/core/combiner.py`
- **验收**：报告包含规范参数、筛选过程、每条波信息（RSN/事件/台站/缩放系数/偏差）、反应谱对比图
- **依赖**：Task 3.2
- **AC**：AC-4.6
- **预估**：1.5h

### Task 3.4: 组合输出测试
- **描述**：端到端测试：规范谱 → 选波 → 生成 → 组合 → 导出
- **文件**：`tests/test_combiner.py`
- **验收**：完整流程跑通，输出 7 条波形文件 + 报告
- **依赖**：Task 3.2, 3.3
- **预估**：1h

---

## Group 4: GUI 重构（P1）

### Task 4.1: 主窗口向导式流程
- **描述**：重构 `main_window.py`，工具栏改为四步向导（规范谱→选波→生成→组合），面板随步骤切换
- **文件**：`seiswave/gui/main_window.py`
- **验收**：四个步骤可切换，面板正确显示
- **依赖**：Group 1-3 核心模块完成
- **AC**：AC-1.6
- **预估**：2h

### Task 4.2: 规范谱面板改造
- **描述**：改造 `spec_panel.py`：只保留 GB50011/GB51408/自定义三种，增加隔震前后周期输入、自定义谱输入/导入
- **文件**：`seiswave/gui/panels/spec_panel.py`
- **验收**：
  - 规范选择：抗规/隔规/自定义
  - 隔震模式下显示隔震前后周期输入框
  - 自定义模式下显示周期-谱值表格 + CSV 导入按钮
  - 实时预览反应谱曲线
- **依赖**：Task 3.1, Task 4.1
- **AC**：AC-1.1~AC-1.7
- **预估**：2h

### Task 4.3: 天然波选取面板
- **描述**：重做选波面板：PEER 数据库浏览、筛选条件设置、一键选波、结果列表、反应谱对比图
- **文件**：`seiswave/gui/panels/select_panel.py`
- **验收**：
  - 显示 PEER 数据库记录列表（RSN/事件/台站/PGA/持时）
  - 支持按 RSN/事件名过滤
  - T1/T2/T3 输入 + 筛选条件设置
  - 一键选波，后台线程执行
  - 结果列表 + 反应谱 vs 目标谱对比图
- **依赖**：Task 2.3, Task 4.1
- **AC**：AC-2.6, AC-2.8, AC-2.9
- **预估**：3h

### Task 4.4: 人工波生成面板改造
- **描述**：适配 Fortran 加速，显示迭代进度（当前迭代/最大偏差/均值偏差）
- **文件**：`seiswave/gui/panels/gen_panel.py`
- **验收**：
  - 迭代过程实时显示进度
  - 收敛后显示反应谱对比图
  - 支持多 trial 自动取最优
- **依赖**：Task 1.4, Task 4.1
- **AC**：AC-3.3, AC-3.4, AC-3.5
- **预估**：1.5h

### Task 4.5: 组合输出面板（新增）
- **描述**：新建 `combine_panel.py`：组合模式选择（7/3条）、天然波+人工波汇总、规范校验结果、一键导出
- **文件**：`seiswave/gui/panels/combine_panel.py`
- **验收**：
  - 显示已选天然波 + 已生成人工波列表
  - 组合模式切换（7/3）
  - 显示平均谱/包络谱 vs 目标谱
  - 底部剪力校核结果
  - 一键导出波形 + 报告
- **依赖**：Task 3.2, Task 4.1
- **AC**：AC-4.1~AC-4.6
- **预估**：2.5h

### Task 4.6: Workers 更新
- **描述**：新增/更新后台计算线程：PeerIndexWorker、SpectraPrecomputeWorker、SelectorWorker、CombinerWorker
- **文件**：`seiswave/gui/workers.py`
- **验收**：所有计算在后台线程执行，GUI 不冻结，进度可更新
- **依赖**：Task 4.1
- **AC**：NFR-1
- **预估**：1.5h

---

## Group 5: 信号处理增强（P2）

### Task 5.1: io.py 元数据解析增强
- **描述**：`FileIO.read_at2()` 增加 PEER 元数据提取（RSN/事件/台站/日期/分量），新增 `parse_peer_filename()`
- **文件**：`seiswave/core/io.py`
- **验收**：解析任意 PEER AT2 文件返回完整元数据字典
- **AC**：AC-2.2
- **预估**：1h

### Task 5.2: 信号处理面板增强
- **描述**：信号处理面板增加 Arias 强度、有效持时显示，处理前后对比可视化
- **文件**：`seiswave/gui/panels/signal_panel.py`
- **验收**：所有信号处理功能可用，前后对比图正确
- **AC**：AC-5.1~AC-5.8
- **预估**：1.5h

---

## 执行顺序

```
Group 1 (Fortran):  1.1 → 1.2 → 1.3 + 1.4 (并行) → 1.5
                                    │
Group 2 (PEER+选波): 2.1 ──────→ 2.2 → 2.3 → 2.4 → 2.5
                                              │
Group 3 (规范+组合): 3.1 ──────────────────→ 3.2 → 3.3 → 3.4
                                              │
Group 4 (GUI):       4.1 → 4.2 + 4.3 + 4.4 + 4.5 (并行) → 4.6
                                              │
Group 5 (增强):      5.1 + 5.2 (并行，可随时做)
```

**关键路径**：Task 1.1 → 1.2 → 1.3 → 2.2 → 2.3 → 3.2 → 4.5

## 总工作量预估

| Group | 任务数 | 预估总时长 |
|-------|--------|-----------|
| Group 1: Fortran | 5 | ~5.5h |
| Group 2: PEER+选波 | 5 | ~8.5h |
| Group 3: 规范+组合 | 4 | ~7h |
| Group 4: GUI | 6 | ~12.5h |
| Group 5: 增强 | 2 | ~2.5h |
| **合计** | **22** | **~36h** |
