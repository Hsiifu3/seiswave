import numpy as np
import pytest
from seiswave.core.fortran_bridge import acc2vd


def test_acc2vd_empty_array():
    """acc2vd 应为显式空输入错误抛出稳定的 ValueError。"""
    with pytest.raises(Exception) as exc_info:
        acc2vd(np.array([]), dt=0.01)
    assert isinstance(exc_info.value, ValueError)
    assert str(exc_info.value) == "Input acceleration array is empty"


def test_acc2vd_single_element():
    """acc2vd 应能处理单元素数组"""
    acc = np.array([1.0])
    v, d = acc2vd(acc, dt=0.01)
    assert v.shape == (1,)
    assert d.shape == (1,)
    assert v[0] == 0.0  # 初始速度默认为 0
    assert d[0] == 0.0  # 初始位移默认为 0
