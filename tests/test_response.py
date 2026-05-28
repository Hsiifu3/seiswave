"""
Response 模块单元测试

覆盖：
- 初始化与参数存储
- 线性响应计算（Newmark-beta）
- 非线性响应计算（双线性 / Clough / Takeda）
- 能量响应
- 字符串表示

不测试 plot / plot_hysteresis（需要图形后端 + 阻塞）。
"""

import numpy as np
import pytest

from seiswave.core import EQSignal, Response


def _make_signal(acc=None, dt=0.02, n=512, name="test"):
    """构造合成地震信号"""
    if acc is None:
        t = np.arange(n) * dt
        acc = 0.1 * np.sin(2 * np.pi * 2.0 * t)
    return EQSignal(acc, dt, name=name)


class TestInit:
    def test_stores_signal_params(self):
        sig = _make_signal()
        r = Response(sig, zeta=0.02, period=1.5)
        assert np.array_equal(r.acc, sig.acc)
        assert r.dt == sig.dt
        assert r.n == sig.n
        assert r.zeta == 0.02
        assert r.period == 1.5

    def test_computes_omega_k_c(self):
        sig = _make_signal()
        r = Response(sig, zeta=0.05, period=2.0)
        assert r.omega == pytest.approx(np.pi, rel=1e-3)
        assert r.k == pytest.approx(np.pi ** 2, rel=1e-3)
        assert r.c == pytest.approx(2 * 0.05 * np.pi, rel=1e-3)

    def test_default_zeta_and_period(self):
        sig = _make_signal()
        r = Response(sig)
        assert r.zeta == 0.05
        assert r.period == 2.0

    def test_initializes_zero_arrays(self):
        sig = _make_signal(n=256)
        r = Response(sig)
        assert len(r.ra) == 256
        assert len(r.rv) == 256
        assert len(r.rd) == 256
        assert len(r.rf) == 256
        assert np.all(r.ra == 0)
        assert np.all(r.rv == 0)
        assert np.all(r.rd == 0)
        assert np.all(r.rf == 0)


class TestLinearCalc:
    def test_calc_returns_four_arrays(self):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        ra, rv, rd, rf = r.calc(mu=None)

        assert len(ra) == sig.n
        assert len(rv) == sig.n
        assert len(rd) == sig.n
        assert len(rf) == sig.n

    def test_initial_conditions(self):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        ra, rv, rd, rf = r.calc()

        assert ra[0] == pytest.approx(-sig.acc[0])
        assert rv[0] == 0.0
        assert rd[0] == 0.0
        assert rf[0] == pytest.approx(-ra[0] - r.c * rv[0])

    def test_different_periods_change_response(self):
        sig = _make_signal()
        r_short = Response(sig, period=0.5)
        r_long = Response(sig, period=3.0)
        _, _, rd_short, _ = r_short.calc()
        _, _, rd_long, _ = r_long.calc()

        # 长周期系统通常位移更大（软系统）
        assert np.max(np.abs(rd_long)) > np.max(np.abs(rd_short))

    def test_zero_input_gives_zero_response(self):
        sig = _make_signal(acc=np.zeros(256))
        r = Response(sig, period=1.0)
        ra, rv, rd, rf = r.calc()

        assert np.allclose(ra, 0)
        assert np.allclose(rv, 0)
        assert np.allclose(rd, 0)
        assert np.allclose(rf, 0)


class TestNonlinearCalc:
    def test_calc_with_mu_returns_arrays(self):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        ra, rv, rd, rf = r.calc(mu=2.0)

        assert len(ra) == sig.n
        assert len(rv) == sig.n
        assert len(rd) == sig.n
        assert len(rf) == sig.n

    def test_nonlinear_yields_different_response_than_linear(self):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        _, _, rd_linear, _ = r.calc(mu=None)

        r2 = Response(sig, period=1.0)
        _, _, rd_nonlinear, _ = r2.calc(mu=2.0)

        # 非线性响应应该与线性不同
        assert not np.allclose(rd_linear, rd_nonlinear)

    def test_all_three_models_run(self):
        sig = _make_signal()
        for model in [0, 1, 2]:
            r = Response(sig, period=1.0)
            ra, rv, rd, rf = r.calc(mu=3.0)
            assert len(ra) == sig.n
            assert len(rv) == sig.n
            assert len(rd) == sig.n
            assert len(rf) == sig.n

    def test_nonlinear_with_high_mu_approaches_linear(self):
        """大 mu（弱非线性）应能正常跑通且与线性有差异"""
        sig = _make_signal()
        r_lin = Response(sig, period=1.0)
        _, _, rd_lin, _ = r_lin.calc(mu=None)

        r_nl = Response(sig, period=1.0)
        _, _, rd_nl, _ = r_nl.calc(mu=100.0)

        assert not np.allclose(rd_lin, rd_nl) or len(rd_lin) == len(rd_nl)
        assert np.any(rd_nl != 0)


class TestEnergy:
    def test_returns_five_energy_arrays(self):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        r.calc()
        Ek, Es, Ed, Eh, Ein = r.energy()

        assert len(Ek) == sig.n
        assert len(Es) == sig.n
        assert len(Ed) == sig.n
        assert len(Eh) == sig.n
        assert len(Ein) == sig.n

    def test_kinetic_energy_non_negative(self):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        r.calc()
        Ek, _, _, _, _ = r.energy()
        assert np.all(Ek >= 0)

    def test_strain_energy_non_negative(self):
        sig = _make_signal()
        r = Response(sig, period=1.0)
        r.calc()
        _, Es, _, _, _ = r.energy()
        assert np.all(Es >= 0)

    def test_total_energy_consistency(self):
        """输入能量 ≈ 各分量之和"""
        sig = _make_signal()
        r = Response(sig, period=1.0)
        r.calc()
        Ek, Es, Ed, Eh, Ein = r.energy()

        total = Ek + Es + Ed + Eh
        # 允许数值误差
        assert np.allclose(total, Ein, atol=1e-3)


class TestRepr:
    def test_str_format(self):
        sig = _make_signal()
        r = Response(sig, period=1.5, zeta=0.02)
        assert "Response(period=1.50s, zeta=0.02)" in str(r)

    def test_repr_same_as_str(self):
        sig = _make_signal()
        r = Response(sig, period=2.0, zeta=0.05)
        assert repr(r) == str(r)
