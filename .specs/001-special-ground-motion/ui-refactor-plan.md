# GeneratorPanel 渐进重构计划（方案 A）

## 问题
当前 `generator_panel.py` 562 行一个类，违反单一职责：
- UI 布局构建
- 类型切换状态管理
- 一般人工波生成逻辑
- 特殊地震动生成逻辑
- 结果文本格式化
- matplotlib 绘图（反应谱 + 时程 + NFP 双 Y 轴）

## 目标
拆成 4 个独立组件，保持向后兼容，不破坏现有测试。

## 拆分方案

### 1. `ParamFormWidget` — 参数输入面板（~150 行）
职责：所有 QSpinBox/QComboBox 的创建、取值、显隐控制
- `_type_combo`：地震动类型
- `_mw_spin`, `_r_spin`, `_vs30_spin`：震源参数
- `_fault_combo`：断层类型（NFP 专用）
- `_npts_spin`, `_dt_spin`, `_pga_spin`, `_zeta_spin`：通用生成参数
- `_tol_spin`, `_maxiter_spin`, `_trials_spin`：迭代控制
- 方法：`get_params()` 返回字典、`set_type(type_code)` 切换显隐、`reset_defaults()`

### 2. `ProgressWidget` — 进度与信息展示（~80 行）
职责：进度条 + 状态文本 + 结果信息
- `_progress_bar`, `_progress_label`, `_info_label`
- 方法：`start()`, `update(pct, text)`, `finish(info_lines)`, `error(msg)`

### 3. `ResultPresenter` — 结果绘图与文本格式化（~200 行）
职责：所有 matplotlib 绘图 + 文本格式化，不耦合生成逻辑
- `present_general(signal, trial_spectra, best_idx, code_periods, code_sa)`
- `present_special(signal, gm_type, code_periods, code_sa)`
- NFP 脉冲参数文本框、双 Y 轴脉冲速度图
- 方法内部调用 PlotWidget/SpectrumPlot，不直接操作 ax

### 4. `GeneratorController` — 生成逻辑编排（~150 行）
职责：根据类型分发到正确 Worker，连接信号
- `run_general(param_form, code_sa, code_periods)` → MultiTrialGeneratorWorker
- `run_special(param_form, gm_type)` → SpecialGroundMotionWorker
- 信号连接：progress → progress_widget, finished → result_presenter, error → progress_widget

### 5. `GeneratorPanel` — 剩余：组合与协调（~80 行）
职责：用 QHBoxLayout 把上面 4 个组件拼起来，保留公共接口
- `set_code_spectrum(periods, sa)` → 传给 result_presenter
- `get_generated()` → 返回 result_presenter 的当前结果
- `wave_generated = Signal(object)` 保留

## 验收标准
- [ ] 新文件 `param_form.py`, `progress_widget.py`, `result_presenter.py`, `generator_controller.py` 创建
- [ ] `generator_panel.py` 精简到 ~100 行以内
- [ ] `tests/test_gui_generator_panel.py` 现有 15 个测试全部通过
- [ ] 新增测试：各组件独立单元测试（至少 10 个）
- [ ] 手动验证：启动 GUI，FF/NF/NFP 各生成一次，结果展示正常
- [ ] STATUS.md 和 report.sh 更新
