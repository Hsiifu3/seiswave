# adjust_spectra

- Kind: function
- Source: [fortran_bridge.py](../sources/c34fbe4c.md)

## Notes

时域小波叠加谱匹配（fm=1，默认）

Parameters
----------
acc : 初始加速度时程
dt : 时间步长
zeta : 阻尼比
periods : 控制周期数组
target : 目标反应谱值
tol : 收敛容差
max_iter : 最大迭代次数
kpb : 峰值约束 (1=启用)

Returns
-------
调整后的加速度时程
