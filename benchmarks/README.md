# SeisWave 性能基准测试

本目录包含 SeisWave 核心库的性能基准测试，用于追踪关键路径的耗时变化。

## 目录结构

```
benchmarks/
├── README.md              # 本文件
├── results/               # JSON 结果输出
│   └── baseline_YYYYMMDD_HHMMSS.json
└── tests/
    └── benchmarks/
        └── test_baseline.py   # 基准脚本
```

## 运行方式

### 直接运行（推荐）

```bash
cd /Users/yachiyo/Developer/seiswave
python tests/benchmarks/test_baseline.py
```

### 通过 pytest（可选）

```bash
cd /Users/yachiyo/Developer/seiswave
pytest tests/benchmarks/test_baseline.py -v -s
```

> 注：本脚本使用标准库 `timeit` + `time.perf_counter()`，**不依赖** `pytest-benchmark`。

## 基准覆盖范围

| 组别 | 测试项 | 数据规模 | 说明 |
|------|--------|----------|------|
| **fft** | `FFT.amplitude_spectrum` | n=4096/32768/262144 | FFT 频谱分析 |
| | `FFT.welch_psd` | 同上 | Welch 功率谱密度 |
| | `FFT.phase_spectrum` | 同上 | 相位谱 |
| **spectra** | `Spectra.compute(newmark)` | n=8192, periods=50/200/800 | Newmark-β 反应谱 |
| | `Spectra.compute(freq)` | 同上 | 频域法反应谱 |
| | `Spectra.compute(mixed)` | 同上 | 混合法反应谱 |
| **fitspectra** | `WaveGenerator._fitspectra` | n=2048/4096/8192, max_iter=10/20/30 | 频域谱匹配核心迭代 |
| **special_generators** | `FarFieldGenerator.generate` | n=2048/4096, max_iter=5/10 | FF 特殊地震动生成 |
| | `NearFieldNoPulseGenerator.generate` | 同上 | NF 特殊地震动生成 |
| **io** | `FileIO.read_at2` | n=2048/16384/65536 | AT2 格式读取 |
| | `FileIO.read_txt` | 同上 | 文本格式读取 |

## 结果解读

### JSON 格式

每个结果条目包含：

```json
{
  "name": "FFT.amplitude_spectrum",
  "group": "fft",
  "size_label": "large",
  "params": {"n": 262144, "dt": 0.01},
  "runs": 3,
  "times": [0.012345, 0.012100, 0.012500],
  "mean": 0.012315,
  "min": 0.012100,
  "max": 0.012500,
  "stdev": 0.000205
}
```

### 关键指标

- **mean**：多次运行的平均耗时，最稳定的参考值
- **min/max**：最好/最坏情况，可发现间歇性抖动
- **stdev**：标准差，反映稳定性；若 stdev/mean > 20%，说明该路径对输入敏感或存在竞争
- **size_label**：small / medium / large 三档，用于观察复杂度增长是否呈线性

### 性能回归判断

建议每次重大变更后重新运行基准，对比 `mean` 值：

1. 同一台机器、相近负载下对比
2. 关注 **relative change** = (new_mean - old_mean) / old_mean
3. 阈值建议：
   - `> +30%`：需立即排查
   - `+10% ~ +30%`：记录并追踪
   - `< +10%`：正常波动

## 维护建议

- 运行前关闭其他 CPU 密集型程序
- 每次运行脚本会自动生成新的 JSON 文件，旧文件保留用于对比
- 建议在 CI 中固定 `numpy` 版本，避免因 BLAS 后端变化导致基线漂移
- 新增核心算法时，优先在此添加基准条目
