# Changelog

## [2.0.0] - 2026-02-12

基于 EQSignal C++ 库完全重写。Complete rewrite based on EQSignal C++ library.

### 核心库 / Core Library

#### 新增 / Added
- `core/signal.py` — EQSignal 核心类：加速度→速度→位移积分（a2vd）、PGA/持时/有效持时属性、归一化/缩放、手动裁剪与自动 Arias 裁剪、重采样
- `core/spectrum.py` — Spectra 反应谱计算：Newmark-β 平均加速度法、频域法、混合法，支持对数/线性/混合周期分布
- `core/code_spec.py` — CodeSpectrum 规范反应谱：GB 50011 四段式抗震谱 + 三段式隔震谱，含完整参数表（烈度×分组×场地→Tg、α_max），阻尼调整系数 η₁/η₂/γ
- `core/filter.py` — Filter 滤波与基线校正：多项式去趋势（1~6阶）、双线性去趋势（移植 EQSignal bilinearDetrend）、Butterworth 带通/低通/高通、FFT 滤波
- `core/fft.py` — FFT 频域分析：傅里叶振幅谱、Welch 功率谱密度、相位谱
- `core/generator.py` — WaveGenerator 人工波生成：移植 C++ fitSP 迭代谱拟合算法（白噪声+包络→反应谱计算→频域比值调整→收敛判断）
- `core/selector.py` — WaveSelector 选波引擎：三步筛选（有效持时→主周期偏差→底部剪力校核），支持 SDOF Newmark 和 MDOF 时程分析
- `core/response.py` — Response 结构响应分析
- `core/io.py` — FileIO 文件读写：AT2 新旧格式、TXT 单列/双列、CSV、批量加载

#### 验证 / Verification
- 29 项单元测试全部通过，覆盖 IO/Signal/Spectrum/CodeSpec/Filter/FFT/Generator/Selector
- Newmark-β 经 SDOF 阶跃响应验证
- CodeSpectrum 经 MATLAB alpha_standspectrum.m 交叉验证

### GUI 桌面应用 / GUI Desktop Application

#### 新增 / Added
- PySide6 主窗口框架：菜单栏、工具栏、StackedWidget 面板切换、状态栏
- 深色/浅色双主题切换
- 规范谱面板：GB 50011 参数选择、实时预览、CSV 导出
- 数据导入面板：目录选择、格式选择、批量加载、WaveTable 列表、时程预览
- 选波面板：周期输入、筛选参数、后台执行、结果表格、反应谱对比图
- 人工波生成面板：目标谱选择、参数设置、后台生成、拟合对比图
- 信号处理面板：去趋势、滤波、处理前后对比图
- 导出报告面板：时程/反应谱数据导出、图片导出、选波报告生成
- PlotWidget 嵌入 Matplotlib Canvas 带工具栏
- BaseWorker 后台计算线程基础设施

### 项目 / Project

#### 变更 / Changed
- Python 最低版本要求提升至 3.10
- 依赖更新：NumPy >= 1.22, SciPy >= 1.8, Matplotlib >= 3.5
- PySide6 >= 6.5 作为 GUI 可选依赖
- 项目结构重组为 `core/`（纯计算）+ `gui/`（桌面应用）

## [0.1.0] - 初始版本

- 基础地震信号处理功能
