# spectrum_mixed

- Kind: function
- Source: [fortran_bridge.py](../sources/c34fbe4c.md)

## Notes

混合法反应谱计算（短周期频域 + 长周期 Newmark）

Parameters
----------
acc : 加速度时程
dt : 时间步长 (s)
zeta : 阻尼比
periods : 周期数组 (s)

Returns
-------
(sa, spi) : 带符号加速度反应谱, 峰值位置索引(1-based)
